"""Presentation preflight: source, storage, models, reports, and local server."""
import argparse
import json
from pathlib import Path
from .engine import configuration, diagnostics, request_json, structured, embeddings
from .memory import Memory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--inference", action="store_true", help="Make an actual language-model and embedding request")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    results = []
    def record(name, ok, detail): results.append({"check": name, "ok": bool(ok), "detail": detail})
    record("Production frontend", (root/"dist/index.html").exists(), "Run npm run build if missing.")
    mem = Memory(); wid = mem.create_workspace("Preflight"); sid = mem.rows("SELECT id FROM sessions WHERE workspace_id=?", (wid,))[0]["id"]
    mem.ingest(wid, sid, "I live in Hyderabad.", "2026-01-01"); mem.ingest(wid, sid, "I moved to Chennai.", "2026-01-02")
    record("Temporal kernel", mem.query(wid, "Where do I live?")["answer_value"] == "Chennai", "Initial evidence retained; current value selected.")
    restored = mem.import_workspace(mem.export_workspace(wid))
    record("Backup restoration", mem.query(restored, "Where do I live?")["answer_value"] == "Chennai", "Workspace roundtrip with remapped IDs.")
    mem.close()
    engine = diagnostics()
    record("AI configuration", engine["ready"], engine["message"])
    try:
        health = request_json("http://127.0.0.1:%s/api/health" % args.port, timeout=2)
        record("Running application", health.get("app") == "amnesia", "Version %s on port %s" % (health.get("version"), args.port))
    except ValueError:
        record("Running application", False, "Start npm run review or npm start.")
    record("Final report", (root/"output/pdf/amnesia-final-report.pdf").exists(), "Generated report available for download.")
    if args.inference:
        try:
            c = configuration()
            answer = structured([{"role": "user", "content": "Return ready true."}], {"type": "object", "properties": {"ready": {"type": "boolean"}}, "required": ["ready"], "additionalProperties": False}, "preflight", c)
            vector = embeddings(["Long-term memory."], c)[0]
            record("Live inference", answer.get("ready") and len(vector) > 0, "Structured language output and %s-dimensional embeddings." % len(vector))
        except ValueError as exc:
            record("Live inference", False, str(exc))
    print(json.dumps({"ready": all(r["ok"] for r in results), "checks": results}, indent=2))
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__": main()
