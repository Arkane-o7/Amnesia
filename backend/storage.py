"""Auditable lifecycle transitions, scoped slots, aliases, and portable backups."""
import json
import sqlite3
from .extraction import iso, key, parse_time, scope_for

FACT_COLUMNS = "id,workspace_id,subject_id,subject,relation,object_id,value,valid_from,valid_until,observed_at,evidence,event_id,confidence,status,superseded_by,scope,intent,original_valid_until"


class Storage:
    def migrate(self):
        columns = {r["name"] for r in self.rows("PRAGMA table_info(facts)")}
        fresh = "scope" not in columns
        for name, spec in [("scope", "TEXT NOT NULL DEFAULT ''"), ("intent", "TEXT NOT NULL DEFAULT 'assert'"), ("original_valid_until", "TEXT")]:
            if name not in columns:
                self.db.execute("ALTER TABLE facts ADD COLUMN %s %s" % (name, spec))
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS fact_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,fact_id TEXT NOT NULL REFERENCES facts(id),workspace_id TEXT NOT NULL REFERENCES workspaces(id),status TEXT NOT NULL,valid_until TEXT,superseded_by TEXT,observed_at TEXT NOT NULL,reason TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS history_fact ON fact_history(fact_id,observed_at);
        CREATE TABLE IF NOT EXISTS entity_aliases(workspace_id TEXT NOT NULL REFERENCES workspaces(id),alias TEXT NOT NULL,entity_id TEXT NOT NULL REFERENCES entities(id),evidence TEXT NOT NULL,PRIMARY KEY(workspace_id,alias));
        CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
        """)
        if fresh:
            for fact in self.rows("SELECT * FROM facts ORDER BY rowid"):
                scope = scope_for(fact["relation"], fact["value"])
                own = self.rows("SELECT * FROM decisions WHERE fact_id=? ORDER BY rowid", (fact["id"],))
                tombstone = bool(own and own[0]["label"] == "SUPERSEDES" and fact["valid_until"] == fact["valid_from"])
                intent = "cancel" if tombstone else "uncertain" if fact["confidence"] < .7 else "assert"
                initial = "invalid" if tombstone else "unresolved" if intent == "uncertain" or own and own[0]["label"] == "CONTRADICTS" else "active"
                original_until = fact["valid_until"] if fact["status"] in ("active", "unresolved") else None
                self.db.execute("UPDATE facts SET scope=?,intent=?,original_valid_until=? WHERE id=?", (scope, intent, original_until, fact["id"]))
                self.history(fact["id"], fact["workspace_id"], initial, original_until, None, fact["observed_at"], "Migrated original evidence from v0.1.")
                transitions = self.rows("SELECT * FROM decisions WHERE existing_id=? ORDER BY created_at,rowid", (fact["id"],))
                for transition in transitions:
                    if transition["label"] == "CONTRADICTS":
                        self.history(fact["id"], fact["workspace_id"], "unresolved", original_until, None, transition["created_at"], transition["reason"])
                if fact["status"] in ("superseded", "invalid") and not tombstone:
                    self.history(fact["id"], fact["workspace_id"], fact["status"], fact["valid_until"], fact["superseded_by"], fact["valid_until"] or fact["observed_at"], "Migrated recorded replacement from v0.1.")
        if not self.rows("SELECT version FROM schema_meta"):
            self.db.execute("INSERT INTO schema_meta VALUES (2)")
        if self.rows("SELECT version FROM schema_meta")[0]["version"] < 3:
            for fact in self.rows("SELECT id,relation,value,scope FROM facts WHERE relation='owns'"):
                self.db.execute("UPDATE facts SET scope=? WHERE id=?", (scope_for(fact["relation"], fact["value"], fact["scope"]), fact["id"]))
            self.db.execute("UPDATE schema_meta SET version=3")
        self.db.commit()

    def history(self, fid, wid, status, until, replaced_by, observed_at, reason):
        self.db.execute("INSERT INTO fact_history(fact_id,workspace_id,status,valid_until,superseded_by,observed_at,reason) VALUES (?,?,?,?,?,?,?)", (fid, wid, status, until, replaced_by, observed_at, reason))

    def transition(self, fact, status, observed_at, reason, valid_until=None, replaced_by=None, close=False):
        until = valid_until if close else fact.get("valid_until")
        self.db.execute("UPDATE facts SET status=?,valid_until=?,superseded_by=? WHERE id=?", (status, until, replaced_by, fact["id"]))
        self.history(fact["id"], fact["workspace_id"], status, until, replaced_by, observed_at, reason)

    def put_fact(self, fid, wid, sid, a, observed_at, event_id, status):
        object_id = self.entity(wid, a["value"])
        subject = self.rows("SELECT name FROM entities WHERE id=?", (sid,))[0]["name"]
        valid_from = a.get("valid_from") or observed_at
        until = observed_at if a["intent"] == "cancel" and status == "invalid" else a.get("valid_until")
        values = (fid, wid, sid, subject, a["relation"], object_id, a["value"], valid_from, until, observed_at, a["evidence"], event_id, a["confidence"], status, None, scope_for(a["relation"], a["value"], a.get("scope", "")), a["intent"], a.get("valid_until"))
        self.db.execute("INSERT INTO facts (%s) VALUES (%s)" % (FACT_COLUMNS, ",".join("?" for _ in values)), values)
        self.history(fid, wid, status, until, None, observed_at, "Initial evidence.")

    def register_alias(self, wid, alias, canonical, evidence):
        if key(alias) == key(canonical):
            return
        entity_id = self.entity(wid, canonical)
        existing = self.rows("SELECT id FROM entities WHERE workspace_id=? AND canonical=?", (wid, key(alias)))
        if existing and existing[0]["id"] != entity_id:
            raise ValueError("Both alias names already exist as separate entities. Clarify them in a new workspace before merging.")
        found = self.rows("SELECT entity_id FROM entity_aliases WHERE workspace_id=? AND alias=?", (wid, key(alias)))
        if found and found[0]["entity_id"] != entity_id:
            raise ValueError("This alias already refers to another entity.")
        self.db.execute("INSERT OR REPLACE INTO entity_aliases VALUES (?,?,?,?)", (wid, key(alias), entity_id, evidence))

    def resolve_conflict(self, wid, sid, fid, evidence):
        from .memory import uid
        self.require_workspace(wid)
        fact = next((f for f in self.facts(wid) if f["id"] == fid), None)
        if not fact or fact["status"] != "unresolved":
            raise ValueError("Select an unresolved memory to confirm.")
        if not self.rows("SELECT id FROM sessions WHERE id=? AND workspace_id=?", (sid, wid)):
            raise ValueError("Invalid session.")
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 2000:
            raise ValueError("Write a short confirmation to preserve the evidence.")
        now, eid = iso(parse_time()), uid()
        reason = "The user explicitly confirmed this value and resolved the scoped conflict."
        with self.db:
            self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (eid, wid, sid, "user", evidence, now, "{}"))
            for old in self.facts(wid):
                if old["subject_id"] == fact["subject_id"] and old["relation"] == fact["relation"] and old["scope"] == fact["scope"] and old["status"] == "unresolved":
                    self.transition(old, "active" if old["id"] == fid else "invalid", now, reason, now, fid if old["id"] != fid else None, close=old["id"] != fid)
            self.db.execute("INSERT INTO fact_evidence VALUES (?,?)", (fid, eid))
            decision = {"label": "UPDATES", "reason": reason, "fact_id": fid, "existing_id": None, "subject": fact["subject"], "relation": fact["relation"], "value": fact["value"], "scope": fact["scope"]}
            self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)", (uid(), wid, eid, fid, None, "UPDATES", reason, now))
            self.db.execute("UPDATE events SET result=? WHERE id=?", (json.dumps({"assertions": 1, "decisions": [decision], "unsupported": [], "provider": "user confirmation", "latency_ms": 0}), eid))
        return {"event_id": eid, "decision": decision}

    def export_workspace(self, wid):
        state = self.state(wid)
        state.update(format="amnesia.workspace", schema_version=2, aliases=self.rows("SELECT * FROM entity_aliases WHERE workspace_id=?", (wid,)), evidence_links=self.rows("SELECT fe.* FROM fact_evidence fe JOIN facts f ON f.id=fe.fact_id WHERE f.workspace_id=?", (wid,)), history=self.rows("SELECT * FROM fact_history WHERE workspace_id=? ORDER BY seq", (wid,)))
        return state

    def import_workspace(self, payload, name=None):
        from .memory import uid
        if not isinstance(payload, dict) or payload.get("format") != "amnesia.workspace" or payload.get("schema_version") != 2:
            raise ValueError("Choose a version 2 Amnesia workspace export.")
        required = ("workspace", "sessions", "facts", "entities", "events", "decisions", "history", "evidence_links", "aliases")
        if not all(k in payload for k in required) or any(not isinstance(payload[k], list) for k in required if k != "workspace"):
            raise ValueError("The export is incomplete.")
        if len(payload["events"]) > 20000 or len(payload["facts"]) > 30000:
            raise ValueError("The workspace exceeds this local import limit.")
        ids = {row["id"]: uid() for table in ("sessions", "facts", "entities", "events", "decisions") for row in payload[table]}
        if len(ids) != sum(len(payload[t]) for t in ("sessions", "facts", "entities", "events", "decisions")):
            raise ValueError("The export contains duplicate identifiers.")
        wid, now = uid(), iso(parse_time())
        remap = lambda value: ids[value] if value is not None else None
        def rewrite(value):
            if isinstance(value, dict):
                return {k: rewrite(v) for k, v in value.items()}
            if isinstance(value, list):
                return [rewrite(v) for v in value]
            return ids.get(value, value) if isinstance(value, str) else value
        try:
            with self.db:
                self.db.execute("PRAGMA defer_foreign_keys=ON")
                self.db.execute("INSERT INTO workspaces VALUES (?,?,?)", (wid, (name or payload["workspace"]["name"] + " (imported)")[:100], now))
                for s in payload["sessions"]:
                    self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (remap(s["id"]), wid, s["name"], iso(parse_time(s["created_at"]))))
                for e in payload["entities"]:
                    self.db.execute("INSERT INTO entities VALUES (?,?,?,?)", (remap(e["id"]), wid, e["name"], key(e["name"])))
                for e in payload["events"]:
                    if e["role"] not in ("user", "query"):
                        raise ValueError("Unknown event role in import.")
                    self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (remap(e["id"]), wid, remap(e["session_id"]), e["role"], e["text"], iso(parse_time(e["observed_at"])), json.dumps(rewrite(e["result"]))))
                for f in payload["facts"]:
                    values = [f.get(k) for k in FACT_COLUMNS.split(",")]
                    for index in (0, 2, 5, 11, 14):
                        values[index] = remap(values[index])
                    values[1] = wid
                    values[15] = scope_for(f["relation"], f["value"], f.get("scope", ""))
                    if f["confidence"] < 0 or f["confidence"] > 1 or not f["relation"]:
                        raise ValueError("Invalid imported assertion.")
                    self.db.execute("INSERT INTO facts (%s) VALUES (%s)" % (FACT_COLUMNS, ",".join("?" for _ in values)), values)
                for d in payload["decisions"]:
                    self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)", (remap(d["id"]), wid, remap(d["event_id"]), remap(d["fact_id"]), remap(d["existing_id"]), d["label"], d["reason"], d["created_at"]))
                for h in payload["history"]:
                    self.history(remap(h["fact_id"]), wid, h["status"], h["valid_until"], remap(h["superseded_by"]), h["observed_at"], h["reason"])
                for link in payload["evidence_links"]:
                    self.db.execute("INSERT INTO fact_evidence VALUES (?,?)", (remap(link["fact_id"]), remap(link["event_id"])))
                for alias in payload["aliases"]:
                    self.db.execute("INSERT INTO entity_aliases VALUES (?,?,?,?)", (wid, alias["alias"], remap(alias["entity_id"]), alias["evidence"]))
        except (KeyError, TypeError, sqlite3.IntegrityError) as exc:
            raise ValueError("The workspace has invalid or missing references. Nothing was imported.") from exc
        return wid
