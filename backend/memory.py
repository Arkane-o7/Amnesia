"""SQLite temporal graph, conservative reconciliation and explainable retrieval."""
import json
import hashlib
import math
import re
import sqlite3
import time
import uuid
from collections import Counter
from datetime import timedelta
from .extraction import RELATIONS, SINGLE, extract_local, extract_llm, extract_ai, iso, key, parse_time, scope_for
from .providers import dense_similarities, grounded_answer
from .storage import Storage
from .retrieval import dense_scores, personalized_pagerank, answer_ai


def uid():
    return uuid.uuid4().hex[:16]


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),name TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),session_id TEXT NOT NULL REFERENCES sessions(id),role TEXT NOT NULL,text TEXT NOT NULL,observed_at TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),name TEXT NOT NULL,canonical TEXT NOT NULL,UNIQUE(workspace_id,canonical));
CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),subject_id TEXT NOT NULL REFERENCES entities(id),subject TEXT NOT NULL,relation TEXT NOT NULL,object_id TEXT NOT NULL REFERENCES entities(id),value TEXT NOT NULL,valid_from TEXT NOT NULL,valid_until TEXT,observed_at TEXT NOT NULL,evidence TEXT NOT NULL,event_id TEXT NOT NULL REFERENCES events(id),confidence REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','superseded','invalid','unresolved')),superseded_by TEXT REFERENCES facts(id));
CREATE TABLE IF NOT EXISTS fact_evidence(fact_id TEXT NOT NULL REFERENCES facts(id),event_id TEXT NOT NULL REFERENCES events(id),PRIMARY KEY(fact_id,event_id));
CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),event_id TEXT NOT NULL REFERENCES events(id),fact_id TEXT REFERENCES facts(id),existing_id TEXT REFERENCES facts(id),label TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS facts_scope ON facts(workspace_id,subject_id,relation);
CREATE INDEX IF NOT EXISTS events_workspace ON events(workspace_id,observed_at);
CREATE TABLE IF NOT EXISTS embedding_cache(model TEXT NOT NULL,digest TEXT NOT NULL,vector TEXT NOT NULL,PRIMARY KEY(model,digest));
CREATE TABLE IF NOT EXISTS ingest_receipts(workspace_id TEXT NOT NULL REFERENCES workspaces(id),request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(workspace_id,request_id));
"""


class Memory(Storage):
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(str(path), timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.migrate()

    def close(self):
        self.db.close()

    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def require_workspace(self, wid):
        if not self.rows("SELECT id FROM workspaces WHERE id=?", (wid,)):
            raise ValueError("Workspace not found.")

    def create_workspace(self, name="Untitled workspace"):
        wid = uid()
        with self.db:
            self.db.execute("INSERT INTO workspaces VALUES (?,?,?)", (wid, name[:100], iso(parse_time())))
        self.create_session(wid)
        return wid

    def create_session(self, wid):
        self.require_workspace(wid)
        sid = uid()
        n = self.db.execute("SELECT count(*) FROM sessions WHERE workspace_id=?", (wid,)).fetchone()[0] + 1
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sid, wid, "Session %02d" % n, iso(parse_time())))
        return sid

    def entity(self, wid, name):
        alias = self.rows("SELECT entity_id FROM entity_aliases WHERE workspace_id=? AND alias=?", (wid, key(name)))
        if alias:
            return alias[0]["entity_id"]
        existing = self.rows("SELECT id FROM entities WHERE workspace_id=? AND canonical=?", (wid, key(name)))
        if existing:
            return existing[0]["id"]
        eid = uid()
        self.db.execute("INSERT INTO entities VALUES (?,?,?,?)", (eid, wid, name, key(name)))
        return eid

    def facts(self, wid):
        return self.rows("SELECT * FROM facts WHERE workspace_id=? ORDER BY observed_at,rowid", (wid,))

    def ingest(self, wid, sid, text, observed_at=None, provider="local", config=None, cache=False, assertion_batch=None, request_id=None, new_session=False):
        self.require_workspace(wid)
        if not self.rows("SELECT id FROM sessions WHERE id=? AND workspace_id=?", (sid, wid)):
            raise ValueError("Session does not belong to this workspace.")
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError("Enter between 1 and 8,000 characters.")
        if provider not in ("local", "llm", "ai"):
            raise ValueError("Unknown extraction provider.")
        if not isinstance(new_session, bool):
            raise ValueError("new_session must be a boolean.")
        if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_id)):
            raise ValueError("Invalid ingestion request ID.")
        fingerprint = hashlib.sha256(json.dumps([sid, text, observed_at, new_session], ensure_ascii=False).encode()).hexdigest()
        def receipt():
            rows = self.rows("SELECT fingerprint,result FROM ingest_receipts WHERE workspace_id=? AND request_id=?", (wid, request_id)) if request_id else []
            if rows:
                if rows[0]["fingerprint"] != fingerprint:
                    raise ValueError("This request ID was already used for different input.")
                return json.loads(rows[0]["result"])
        previous = receipt()
        if previous is not None:
            return previous
        observed_at = iso(parse_time(observed_at))
        # Observation order is explicit; historical queries use this timeline.
        latest = self.rows("SELECT MAX(observed_at) AS ts FROM events WHERE workspace_id=?", (wid,))[0]["ts"]
        if latest and observed_at < latest:
            raise ValueError("Event time precedes this workspace's latest event. Use a new workspace for replay.")
        start = time.perf_counter()
        prior = self.facts(wid)
        aliases = []
        if assertion_batch is not None:
            assertions, unsupported = assertion_batch, []
        elif provider == "ai":
            assertions, unsupported, aliases = extract_ai(text, observed_at, prior, config, cache)
        else:
            extractor = extract_llm if provider == "llm" else extract_local
            assertions, unsupported = extractor(text, observed_at, prior)
        extraction_ms = (time.perf_counter()-start)*1000
        for a in assertions:
            a["scope"] = scope_for(a["relation"], a["value"], a.get("scope", ""))
            # Extraction is probabilistic; explicit lexical cues are conservative policy evidence.
            evidence = a["evidence"]
            if a["intent"] == "assert" and a["confidence"] >= .7:
                if re.search(r"\b(correction|I meant|mistaken|got .+ wrong)\b", evidence, re.I):
                    a["intent"] = "correct"
                elif re.search(r"\b(now|moved|relocated|switched|renamed|replaced|instead|from now on)\b", evidence, re.I):
                    a["intent"] = "update"
        eid, decisions = uid(), []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            previous = receipt()
            if previous is not None:
                return previous
            latest_now = self.rows("SELECT MAX(observed_at) AS ts FROM events WHERE workspace_id=?", (wid,))[0]["ts"]
            if latest_now and observed_at < latest_now:
                raise ValueError("Event time precedes this workspace's latest event. Retry with a current timestamp.")
            signature = lambda facts: [(f["id"], f["status"], f["valid_until"]) for f in facts]
            if signature(self.facts(wid)) != signature(prior):
                raise ValueError("Memory changed during extraction. Retry the statement against the latest graph.")
            if new_session:
                sid = uid()
                n = self.db.execute("SELECT count(*) FROM sessions WHERE workspace_id=?", (wid,)).fetchone()[0] + 1
                self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sid, wid, "Session %02d" % n, observed_at))
            self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (eid, wid, sid, "user", text.strip(), observed_at, "{}"))
            for alias in aliases:
                self.register_alias(wid, alias["alias"], alias["canonical"], text)
            reconciliation_start = time.perf_counter()
            for a in assertions:
                decisions.append(self.reconcile(wid, eid, a, observed_at))
            result = {"assertions": len(assertions), "decisions": decisions, "unsupported": unsupported, "provider": "gold annotations" if assertion_batch is not None else (config["provider"] + " · " + config["chat_model"] if provider == "ai" and config else provider), "latency_ms": round((time.perf_counter()-start)*1000, 2), "pipeline": {"extraction_ms": round(extraction_ms, 2), "reconciliation_ms": round((time.perf_counter()-reconciliation_start)*1000, 2)}, "aliases": aliases}
            self.db.execute("UPDATE events SET result=? WHERE id=?", (json.dumps(result), eid))
            response = dict(result, event_id=eid, session_id=sid)
            if request_id:
                self.db.execute("INSERT INTO ingest_receipts VALUES (?,?,?,?)", (wid, request_id, fingerprint, json.dumps(response)))
        return response

    def reconcile(self, wid, eid, a, observed_at):
        subject_id = self.entity(wid, a["subject"])
        a["scope"] = scope_for(a["relation"], a["value"], a.get("scope", ""))
        candidates = self.rows("SELECT * FROM facts WHERE workspace_id=? AND subject_id=? AND relation=? AND scope=? AND status IN ('active','unresolved') ORDER BY observed_at,rowid", (wid, subject_id, a["relation"], a["scope"]))
        candidates = [f for f in candidates if not f["valid_until"] or f["valid_until"] > observed_at]
        same = next((f for f in candidates if key(f["value"]) == key(a["value"])), None)
        intent, existing, status = a["intent"], None, "active"
        if intent == "cancel" and a["confidence"] < .7:
            # A weak cancellation is not permission to retire a known fact.
            fid = uid()
            existing = next((f for f in candidates if key(f["value"]) == key(a["value"])), None)
            self.put_fact(fid, wid, subject_id, a, observed_at, eid, "unresolved")
            if existing:
                self.transition(existing, "unresolved", observed_at, "Uncertain cancellation.")
            reason = "An uncertain cancellation requires clarification; no fact was retired."
            self.db.execute("INSERT INTO fact_evidence VALUES (?,?)", (fid, eid))
            self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)", (uid(), wid, eid, fid, existing["id"] if existing else None, "CONTRADICTS", reason, observed_at))
            return {"label": "CONTRADICTS", "reason": reason, "fact_id": fid, "existing_id": existing["id"] if existing else None, "subject": a["subject"], "relation": a["relation"], "value": a["value"]}
        label, reason = "UNRELATED", "A compatible fact was added without retiring other relations."
        if same and intent != "cancel" and same["status"] == "active":
            label = "SUPPORTS" if intent == "support" else "SAME"
            reason = "Additional evidence supports the existing assertion." if label == "SUPPORTS" else "The same assertion already exists; evidence was attached."
            fid, existing = same["id"], same
            if intent == "support" and a.get("valid_until") and same.get("valid_until") and a["valid_until"] > same["valid_until"]:
                self.transition(same, "active", observed_at, "Supporting evidence extended the same temporary state.", a["valid_until"], close=True)
        else:
            fid = uid()
            if intent == "cancel":
                matching = [f for f in candidates if key(f["value"]) == key(a["value"])]
                existing = matching[-1] if matching else None
                label, status = "SUPERSEDES", "invalid"
                reason = "An explicit cancellation retires only the matching plan or possession."
            elif candidates and (a["relation"] in SINGLE or a["relation"] == "temporary_location"):
                existing = candidates[-1]
                if intent == "uncertain" or a["confidence"] < .7:
                    label, status = "CONTRADICTS", "unresolved"
                    reason = "Incompatible evidence is uncertain; both possibilities need clarification."
                elif intent == "correct":
                    label = "UPDATES"
                    reason = "An explicit correction invalidates the previous value in this relation."
                elif intent == "update":
                    label = "SUPERSEDES"
                    reason = "An explicit change replaces the previous current value, preserving its history."
                else:
                    label, status = "CONTRADICTS", "unresolved"
                    reason = "Two incompatible assertions have no explicit update cue; the conflict remains unresolved."
            elif intent == "uncertain" or a["confidence"] < .7:
                status = "unresolved"
                reason = "Uncertain evidence is retained without asserting a current belief."
            self.put_fact(fid, wid, subject_id, a, observed_at, eid, status)
            if existing:
                if label in ("UPDATES", "SUPERSEDES"):
                    old_status = "invalid" if intent in ("correct", "cancel") else "superseded"
                    for old in candidates:
                        if intent == "cancel" and key(old["value"]) != key(a["value"]):
                            continue
                        self.transition(old, old_status, observed_at, reason, a.get("valid_from") or observed_at, fid, close=True)
                elif label == "CONTRADICTS":
                    for old in candidates:
                        self.transition(old, "unresolved", observed_at, reason)
        self.db.execute("INSERT OR IGNORE INTO fact_evidence VALUES (?,?)", (fid, eid))
        self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)", (uid(), wid, eid, fid, existing["id"] if existing else None, label, reason, observed_at))
        return {"label": label, "reason": reason, "fact_id": fid, "existing_id": existing["id"] if existing else None, "subject": a["subject"], "relation": a["relation"], "value": a["value"], "scope": a["scope"]}

    def state(self, wid, as_of=None):
        self.require_workspace(wid)
        now = iso(parse_time(as_of))
        facts = self.facts(wid)
        decisions = self.rows("SELECT * FROM decisions WHERE workspace_id=? ORDER BY created_at,rowid", (wid,))
        history = self.rows("SELECT * FROM fact_history WHERE workspace_id=? ORDER BY observed_at,seq", (wid,))
        for f in facts:
            f["history"] = [h for h in history if h["fact_id"] == f["id"]]
            f["evidence_count"] = self.db.execute("SELECT COUNT(*) FROM fact_evidence WHERE fact_id=?", (f["id"],)).fetchone()[0]
            f["effective_status"] = self.effective_status(f, now, decisions)
        events = self.rows("SELECT * FROM events WHERE workspace_id=? ORDER BY observed_at,rowid", (wid,))
        for e in events:
            e["result"] = json.loads(e["result"])
        return {"workspace": self.rows("SELECT * FROM workspaces WHERE id=?", (wid,))[0], "sessions": self.rows("SELECT * FROM sessions WHERE workspace_id=? ORDER BY rowid", (wid,)), "facts": facts, "entities": self.rows("SELECT * FROM entities WHERE workspace_id=?", (wid,)), "events": events, "decisions": decisions, "as_of": now}

    @staticmethod
    def effective_status(f, now, decisions):
        if f.get("history"):
            if f["observed_at"] > now or f["valid_from"] > now:
                return "future"
            known = [h for h in f["history"] if h["observed_at"] <= now]
            if not known:
                return "future"
            belief = known[-1]
            if belief["status"] in ("invalid", "superseded"):
                # A future-dated change does not prematurely retire today's belief.
                if belief["valid_until"] and now < belief["valid_until"]:
                    return "active"
                return belief["status"]
            if belief["valid_until"] and now >= belief["valid_until"]:
                return "expired"
            return belief["status"]
        if f["valid_from"] > now:
            return "future"
        # Reconstruct knowledge at observation time, including later corrections.
        own = [d for d in decisions if d["fact_id"] == f["id"] and d["created_at"] <= now]
        initial = own[0] if own else None
        tombstone = initial and initial["label"] == "SUPERSEDES" and f["valid_until"] == f["valid_from"]
        if tombstone:
            return "invalid"
        if f["valid_until"] and now >= f["valid_until"]:
            return f["status"] if f["status"] in ("invalid", "superseded") else "expired"
        conflicts = [d for d in decisions if d["created_at"] <= now and d["label"] == "CONTRADICTS" and (d["existing_id"] == f["id"] or d["fact_id"] == f["id"])]
        if conflicts or f["confidence"] < .7:
            return "unresolved"
        return "active"

    def query(self, wid, question, method="hybrid", as_of=None, k=5, gate=True, weights=None, persist=False, sid=None, embedding_model=None, answer_model=None, config=None, cache=False, temporal_policy=True, graph_enabled=True):
        start = time.perf_counter()
        if method not in ("hybrid", "vector", "graph", "recent", "context"):
            raise ValueError("Unknown retrieval method.")
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Enter a question between 1 and 2,000 characters.")
        state = self.state(wid, as_of)
        facts = [f for f in state["facts"] if f["observed_at"] <= state["as_of"]]
        relation = query_relation(question)
        personal = bool(re.search(r"\b(I|me|my|mine|we|our)\b", question, re.I))
        personal = personal or any(key(e["name"]) in key(question) for e in state["entities"] if e["name"] != "You")
        needed = personal or bool(re.search(r"\b(remember|earlier|previous|last session)\b", question, re.I))
        historical = bool(re.search(r"\b(previously|formerly|used to|before|historical|history|past|old address)\b", question, re.I))
        requested_scope = None
        if relation == "owns":
            requested_scope = next((s for s in ("phone", "laptop", "tablet") if re.search(r"\b"+s+r"s?\b", question, re.I)), None)
        if relation == "prefers":
            if re.search(r"\b(programming|language|code)\b", question, re.I):
                requested_scope = "programming_language"
            elif re.search(r"\b(drink|beverage|coffee|tea)\b", question, re.I):
                requested_scope = "beverage"
        named_subjects = {f["subject"] for f in facts if f["relation"] == relation and f["subject"] != "You" and re.search(r"(?<!\w)" + re.escape(f["subject"]) + r"(?!\w)", question, re.I)}
        if relation == "name":
            named_subjects.update("Your " + pet for pet in ("dog", "cat") if re.search(r"\b" + pet + r"\b", question, re.I))
        requested_subjects = named_subjects or ({"You"} if personal and relation != "name" else set())
        weights = weights or {"semantic": .4, "graph": .25, "temporal": .2, "confidence": .15, "penalty": .65}
        corpus = [fact_text(f) for f in facts]
        semantic_engine = "TF-IDF cosine"
        if config and config["provider"] != "offline" and corpus and not (gate and not needed) and method in ("hybrid", "vector"):
            semantic = dense_scores(self.db, question, corpus, config)
            semantic_engine = "Dense cosine · " + config["embedding_model"]
        elif embedding_model and corpus and not (gate and not needed) and method in ("hybrid", "vector"):
            semantic = dense_similarities(self.db, question, corpus, embedding_model)
            semantic_engine = "Dense cosine · " + embedding_model
        else:
            semantic = similarities(question, corpus)
        graph_scores, pagerank = personalized_pagerank(facts, question, [0.0]*len(facts) if method == "graph" else semantic, relation, current_only=method == "hybrid" and temporal_policy and not historical) if graph_enabled else ([0.0]*len(facts), {})
        ranked = []
        for i, f in enumerate(facts):
            graph = graph_scores[i]
            temporal = 1.0 if f["effective_status"] == "active" else .25 if f["effective_status"] == "unresolved" else 0
            penalty = 1.0 if f["effective_status"] in ("superseded", "invalid", "expired") else .5 if f["effective_status"] == "unresolved" else 0
            if not temporal_policy:
                temporal, penalty = 0, 0
            if historical and f["effective_status"] == "superseded":
                temporal, penalty = 1, 0
            components = {"semantic": semantic[i], "graph": graph, "temporal": temporal, "confidence": f["confidence"], "penalty": penalty}
            if method == "vector":
                score = semantic[i]
            elif method == "graph":
                score = graph
            elif method in ("recent", "context"):
                score = (i+1)/max(1, len(facts))
            else:
                score = sum(weights[n]*components[n] for n in ("semantic", "graph", "temporal", "confidence")) - weights["penalty"]*penalty
            eligible = not (gate and not needed)
            if method == "hybrid" and temporal_policy and temporal == 0:
                eligible = False
            if method == "hybrid" and requested_scope and f["relation"] == relation and f.get("scope") != requested_scope:
                eligible = False
            if method == "hybrid" and requested_subjects and f["relation"] == relation and f["subject"] not in requested_subjects:
                eligible = False
            ranked.append(dict(f, score=round(score, 4), components={n: round(v, 4) for n, v in components.items()}, eligible=eligible))
        # Stable tie-breaking deliberately preserves insertion order for baselines.
        ranked.sort(key=lambda f: -f["score"])
        retrieved = [f for f in ranked if f["eligible"]][:max(1, min(20, k))]
        context_events, used_events, context_truncated = [], [], False
        if method == "context" and not (gate and not needed):
            eligible_events = [e for e in state["events"] if e["role"] == "user" and e["observed_at"] <= state["as_of"]]
            chars = 0
            for e in reversed(eligible_events):
                if chars + len(e["text"]) > 16000:
                    context_truncated = True
                    break
                context_events.insert(0, e)
                chars += len(e["text"])
            retrieved = [{"id": e["id"], "subject": "Conversation", "relation": "conversation", "value": e["text"], "evidence": e["text"], "observed_at": e["observed_at"], "valid_from": e["observed_at"], "valid_until": None, "effective_status": "unreconciled", "intent": "assert"} for e in context_events]
        # Keep all relevant unresolved alternatives; top-k must not hide uncertainty.
        unresolved = [f for f in facts if f["effective_status"] == "unresolved" and (not relation or f["relation"] == relation)]
        if requested_scope:
            unresolved = [f for f in unresolved if f.get("scope") == requested_scope]
        if requested_subjects:
            unresolved = [f for f in unresolved if f["subject"] in requested_subjects]
        if method == "hybrid" and temporal_policy:
            selected_ids = {f["id"] for f in retrieved}
            retrieved.extend(f for f in ranked if f["id"] not in selected_ids and any(u["id"] == f["id"] for u in unresolved))
            # Cancellations are negative evidence, never a positive active plan.
            if relation in ("plans_to", "owns") and not any(f["relation"] == relation and f["effective_status"] == "active" for f in retrieved):
                cancellations = [f for f in ranked if f["relation"] == relation and f.get("intent") == "cancel" and (not requested_scope or f.get("scope") == requested_scope) and (not requested_subjects or f["subject"] in requested_subjects)]
                retrieved.extend(f for f in cancellations[:2] if f["id"] not in {r["id"] for r in retrieved})
        template_retrieved = retrieved if method != "context" else ranked
        answer, answer_value, used = compose_answer(question, relation, [f for f in template_retrieved if not (method == "hybrid" and f.get("intent") == "cancel")], method, gate and not needed)
        answer_engine = "evidence template"
        answer_status = "unresolved" if answer_value == "UNRESOLVED" else "answered" if used else "unknown"
        if method == "hybrid" and temporal_policy and unresolved and not historical and not (gate and not needed):
            values = list(dict.fromkeys(f["value"] for f in unresolved))
            answer = "This is unresolved: the evidence includes %s. Please confirm which is current." % " and ".join(values)
            answer_value, used, answer_status = "UNRESOLVED", [f["id"] for f in unresolved], "unresolved"
            answer_engine = "Conservative conflict guard"
        elif config and config["provider"] != "offline" and retrieved and not (gate and not needed):
            response = answer_ai(question, retrieved, config, cache, include_state=method == "hybrid" and temporal_policy)
            answer, answer_value, used = response["answer"], response["answer_value"], response["used_ids"]
            answer_status = response["answer_status"]
            answer_engine = config["provider"] + " · " + config["chat_model"]
            if method == "context":
                used_events = used
                used = [f["id"] for f in facts if f["event_id"] in used_events]
        elif answer_model and retrieved and not (gate and not needed):
            answer, used = grounded_answer(question, retrieved, answer_model)
            answer_engine = "LLM · " + answer_model
        result = {"question": question, "answer": answer, "answer_value": answer_value, "answer_status": answer_status, "method": method, "as_of": state["as_of"], "memory_needed": needed, "gate_bypassed": gate and not needed, "historical": historical, "candidates": ranked, "retrieved": retrieved, "used_ids": used, "used_event_ids": used_events, "context_events": context_events, "context_truncated": context_truncated, "latency_ms": round((time.perf_counter()-start)*1000, 2), "context_tokens_estimate": sum(len(fact_text(f).split())*1.33 for f in retrieved), "weights": weights, "answer_engine": answer_engine, "semantic_engine": semantic_engine, "graph_engine": "Weighted personalized PageRank (d=0.85, 40 iterations)", "pagerank": pagerank, "temporal_policy": temporal_policy, "graph_enabled": graph_enabled}
        if persist:
            if not self.rows("SELECT id FROM sessions WHERE id=? AND workspace_id=?", (sid, wid)):
                raise ValueError("Session does not belong to this workspace.")
            with self.db:
                self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (uid(), wid, sid, "query", question, iso(parse_time()), json.dumps(result)))
        return result


def query_relation(q):
    for pattern, relation in [
        (r"\b(live|reside|home|residence)\b", "lives_in"),
        (r"\b(prefer|preference|favorite|favourite)\b", "prefers"),
        (r"\b(work|employer|company)\b", "works_at"),
        (r"\b(lead|leading|project|manage)\b", "leads"),
        (r"\b(phone|device|own|use|possession)\b", "owns"),
        (r"\b(trip|plan|visit|travel|cancelled|canceled)\b", "plans_to"),
        (r"\b(birthday|born)\b", "birthday"),
        (r"\b(meeting|appointment)\b", "meeting_day"),
        (r"\b(dog|cat|pet|name)\b", "name"),
        (r"\b(staying|temporarily|this week)\b|where am I", "temporary_location"),
        (r"\b(like|enjoy|hobby)\b", "likes"),
        (r"\b(study|university|college)\b", "studies_at"),
    ]:
        if re.search(pattern, q, re.I):
            return relation
    return None


def fact_text(f):
    return "%s %s %s. %s" % (f["subject"], RELATIONS.get(f["relation"], f["relation"]), f["value"], f["evidence"])


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def similarities(query, corpus):
    """Real sparse TF-IDF cosine vectors. No pretrained semantic embeddings."""
    documents = [tokens(s) for s in corpus] + [tokens(query)]
    df = Counter(t for d in documents for t in set(d))
    vectors = [{t: (1+math.log(c))* (math.log((len(documents)+1)/(df[t]+1))+1) for t, c in Counter(d).items()} for d in documents]
    norms = [math.sqrt(sum(v*v for v in vec.values())) for vec in vectors]
    q = vectors[-1]
    return [sum(v*q.get(t, 0) for t, v in vec.items()) / (norms[i]*norms[-1] or 1) for i, vec in enumerate(vectors[:-1])]


def compose_answer(question, relation, retrieved, method, bypass):
    if bypass:
        return "This question does not appear to need personal memory. Memory retrieval was skipped; this lab only answers questions grounded in stored evidence.", None, []
    if relation is None:
        if re.search(r"\b(remember|know about me|memories|memory summary)\b", question, re.I) and retrieved:
            current = [f for f in retrieved if f["effective_status"] == "active"]
            if current:
                answer = "Here is the retrieved memory: " + "; ".join("%s %s %s" % (f["subject"], RELATIONS[f["relation"]], f["value"]) for f in current) + "."
                return answer, "; ".join(f["value"] for f in current), [f["id"] for f in current]
        return "I don’t have a supported memory relation for that question. Try a question about your home, preferences, work, plans, devices, birthday, meeting, or pet.", None, []
    matching = [f for f in retrieved if relation is None or f["relation"] == relation]
    if relation == "name":
        for animal in ("dog", "cat"):
            if animal in question.lower():
                matching = [f for f in matching if animal in f["subject"].lower()]
    if not matching:
        return "I don’t have a currently valid memory for that question. Add a fact, clarify a conflict, or inspect the history.", None, []
    conflicts = [f for f in matching if f["effective_status"] == "unresolved"]
    if method == "hybrid" and conflicts:
        values = list(dict.fromkeys(f["value"] for f in matching))
        return "This is unresolved: the evidence includes %s. Please confirm which is current." % " and ".join(values), "UNRESOLVED", [f["id"] for f in matching]
    f = matching[0]
    templates = {"lives_in": "You live in %s.", "prefers": "You prefer %s.", "works_at": "You work at %s.", "leads": "You lead %s.", "owns": "You use %s.", "plans_to": "You plan to visit %s.", "birthday": "Your birthday is %s.", "meeting_day": "Your meeting is on %s.", "name": f["subject"] + " is named %s.", "temporary_location": "You are temporarily in %s.", "likes": "You like %s.", "studies_at": "You study at %s."}
    return templates[f["relation"]] % f["value"], f["value"], [f["id"]]


SCENARIOS = {
    "location": {"name": "A change of address", "description": "An old home becomes history, a new one becomes current.", "turns": ["I live in Hyderabad.", "I moved to Chennai."], "question": "Where do I live now?"},
    "additive": {"name": "Two facts, both true", "description": "Leading a project should not overwrite an employer.", "turns": ["I work at Company X.", "I lead Project Y."], "question": "Where do I work?"},
    "correction": {"name": "A small correction", "description": "Correct the date without losing the evidence.", "turns": ["My meeting is Tuesday.", "Correction: Wednesday."], "question": "When is my meeting?"},
    "conflict": {"name": "Room for uncertainty", "description": "Weak conflicting evidence needs clarification.", "turns": ["I live in Pune.", "Maybe I live in Mumbai."], "question": "Where do I live?"},
    "temporary": {"name": "Just visiting", "description": "A temporary stay does not change a permanent home.", "turns": ["I live in Hyderabad.", "I am in Delhi this week."], "question": "Where do I live?"},
    "replacement": {"name": "A new device", "description": "An explicit sale retires only the matching possession.", "turns": ["I use an iPhone.", "I sold it and bought a Pixel."], "question": "What phone do I use?"},
    "cancellation": {"name": "Plans changed", "description": "A cancelled trip should not appear as an active plan.", "turns": ["I will visit Mumbai.", "The trip is cancelled."], "question": "What trip do I have planned?"},
    "rename": {"name": "Same dog, new name", "description": "Preserve identity while updating a name.", "turns": ["My dog is Bruno.", "We renamed him Milo."], "question": "What is my dog's name?"},
}


def load_scenario(memory, scenario):
    s = SCENARIOS.get(scenario)
    if not s:
        raise ValueError("Unknown scenario.")
    wid = memory.create_workspace(s["name"])
    start = parse_time() - timedelta(days=2)
    for i, turn in enumerate(s["turns"]):
        sid = memory.rows("SELECT id FROM sessions WHERE workspace_id=? ORDER BY rowid DESC", (wid,))[0]["id"] if i == 0 else memory.create_session(wid)
        memory.ingest(wid, sid, turn, iso(start + timedelta(days=i)))
    return wid


def seed(memory):
    if memory.rows("SELECT id FROM workspaces LIMIT 1"):
        return
    wid = memory.create_workspace("Research sandbox")
    start = parse_time() - timedelta(days=5)
    turns = ["I live in Hyderabad. I work at Meridian. I prefer Python.", "I lead Project Atlas. My dog is Bruno.", "I moved to Chennai. I now prefer Rust."]
    for i, text in enumerate(turns):
        sid = memory.rows("SELECT id FROM sessions WHERE workspace_id=? ORDER BY rowid DESC", (wid,))[0]["id"] if i == 0 else memory.create_session(wid)
        memory.ingest(wid, sid, text, iso(start + timedelta(days=i*2)))
