"""Dependency-free localhost JSON API and production static server."""
import argparse
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .memory import Memory, SCENARIOS, load_scenario, seed
from .evaluate import dataset, run
from .engine import configuration, diagnostics, save_configuration, structured, embeddings, data_dir, save_cloud_key, cloud_key
from .quality import evaluate_ai
from . import jobs
from .codex_provider import login_status

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AMNESIA_DATA_DIR", ROOT / ".amnesia"))
EVAL_LOCK = threading.Lock()


def saved_reports():
    result = {}
    for kind, candidates in (("policy", ("evaluation-policy.json",)), ("live_ai", ("evaluation-codex.json", "evaluation-openai.json", "evaluation-ollama-final.json"))):
        own = DATA / "reports" / (kind + ".json")
        file = own if own.exists() else next((ROOT / "output" / name for name in candidates if (ROOT / "output" / name).exists()), None)
        result[kind] = json.loads(file.read_text()) if file else None
        if result[kind] and file != own:
            result[kind]["artifact_origin"] = "Bundled verification run"
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if self.path != "/api/health":
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.route(False)

    def do_POST(self):
        self.route(True)

    def route(self, post):
        mem = None
        try:
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            if not path.startswith("/api/"):
                if post:
                    return self.send_json({"error": "Not found."}, 404)
                return self.static(path)
            # Bind localhost and reject cross-origin writes, including DNS rebinding.
            allowed_hosts = ("127.0.0.1", "localhost")
            if self.headers.get("Host", "").split(":")[0] not in allowed_hosts:
                return self.send_json({"error": "Localhost access only."}, 403)
            if post:
                origin = self.headers.get("Origin")
                if origin and (urlparse(origin).hostname not in allowed_hosts or urlparse(origin).port not in (int(os.environ.get("AMNESIA_WEB_PORT", 5173)), self.server.server_port)):
                    return self.send_json({"error": "Origin not allowed."}, 403)
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    return self.send_json({"error": "JSON content type required."}, 415)
                size = int(self.headers.get("Content-Length", "0"))
                limit = 8*1024*1024 if path == "/api/import" else 65536
                if size < 1 or size > limit:
                    raise ValueError("Request body exceeds the allowed size for this action.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("JSON object required.")
            else:
                body = {k: v[0] for k, v in query.items()}
            if path == "/api/health" and not post:
                c = configuration()
                configured = login_status()["codex_authenticated"] if c["provider"] == "codex" else c["provider"] == "ollama" or bool(cloud_key())
                return self.send_json({"ok": True, "app": "amnesia", "project_root": str(ROOT), "data_root": str(DATA.resolve()), "extractor": "local" if c["provider"] == "offline" else "ai", "provider": c["provider"], "chat_model": c["chat_model"], "embedding_model": c["embedding_model"], "external_enabled": c["provider"] in ("codex", "openai"), "llm_configured": configured, "storage": "SQLite", "version": "1.0.0"})
            if path == "/api/engine":
                return self.send_json(diagnostics(save_configuration(body) if post else None))
            if path == "/api/engine/credentials" and post:
                return self.send_json(save_cloud_key(body.get("api_key")))
            if path == "/api/engine/test" and post:
                import time
                c = configuration(); begin = time.perf_counter()
                if c["provider"] == "offline":
                    return self.send_json({"ok": True, "message": "Offline rules selected; no AI inference requested.", "latency_ms": 0})
                reply = structured([{"role": "user", "content": "Return ready as true."}], {"type": "object", "properties": {"ready": {"type": "boolean"}}, "required": ["ready"], "additionalProperties": False}, "connection_test", c)
                vector = embeddings(["A memory that changes with time."], c)[0]
                if not reply.get("ready") or not vector:
                    raise ValueError("The model did not pass the connection test.")
                return self.send_json({"ok": True, "message": "Language inference and dense embeddings both passed.", "latency_ms": round((time.perf_counter()-begin)*1000), "dimensions": len(vector)})
            if path == "/api/jobs" and not post:
                return self.send_json(jobs.recent())
            if path.startswith("/api/jobs/"):
                jid = path.split("/")[3]
                if not jid.isalnum() or len(jid) > 32:
                    raise ValueError("Invalid job identifier.")
                return self.send_json(jobs.cancel(jid) if post and path.endswith("/cancel") else jobs.get(jid))
            if path == "/api/experiments/start" and post:
                kind, count = body.get("kind", "policy"), int(body.get("count", 600))
                if kind not in ("policy", "live_ai"):
                    raise ValueError("Choose a policy or live AI evaluation.")
                if kind == "policy" and (not 10 <= count <= 2000 or count % 10):
                    raise ValueError("Policy size must be a multiple of 10 from 10 to 2000.")
                if kind == "live_ai" and count not in (20, 60):
                    raise ValueError("Choose 20 or 60 live AI questions.")
                c = configuration()
                def evaluate(progress, cancelled):
                    report = evaluate_ai(count, c, progress, cancelled) if kind == "live_ai" else run(count, int(body.get("seed", 42)), gold_inputs=True, progress=progress, cancelled=cancelled)
                    if report is None:
                        return None
                    report.update(suite=kind, title="Curated end-to-end AI" if kind == "live_ai" else "Gold-assertion reconciliation and retrieval")
                    if kind == "policy":
                        report["extractor"] = "Gold annotated assertions (extraction isolated)"
                        report["limitations"] = ["Gold assertions isolate policy and retrieval; these results do not measure natural-language extraction.", "Synthetic controlled set, not a blind external benchmark.", "Answers are deterministic evidence templates; live LLM results are reported separately."] + report["limitations"][3:]
                    folder = DATA / "reports"; folder.mkdir(parents=True, exist_ok=True)
                    temporary = folder / (kind + ".tmp"); temporary.write_text(json.dumps(report, indent=2)); temporary.replace(folder / (kind + ".json"))
                    return report
                return self.send_json(jobs.start(kind, evaluate), 202)
            if path == "/api/reports" and not post:
                return self.send_json(saved_reports())
            if path == "/api/review" and not post:
                return self.send_json({"engine": diagnostics(), "reports": saved_reports(), "report_available": (ROOT/"output/pdf/amnesia-final-report.pdf").exists(), "version": "1.0.0"})
            if path == "/api/report" and not post:
                file = ROOT / "output/pdf/amnesia-final-report.pdf"
                if not file.exists():
                    raise ValueError("The final report has not been generated yet.")
                return self.send_bytes(file.read_bytes(), "application/pdf", 'attachment; filename="amnesia-final-report.pdf"')
            if path == "/api/scenarios" and not post:
                return self.send_json([dict(id=k, **v) for k, v in SCENARIOS.items()])
            if path == "/api/evaluation":
                if not post:
                    report = DATA / "evaluation.json"
                    return self.send_json(json.loads(report.read_text()) if report.exists() else None)
                count = int(body.get("count", 600))
                if not 10 <= count <= 2000 or count % 10:
                    raise ValueError("Use a multiple of 10 between 10 and 2,000 instances.")
                if not EVAL_LOCK.acquire(blocking=False):
                    return self.send_json({"error": "An evaluation is already running."}, 409)
                try:
                    report = run(count, int(body.get("seed", 42)))
                    temporary = DATA / "evaluation.tmp"
                    temporary.write_text(json.dumps(report, indent=2))
                    temporary.replace(DATA / "evaluation.json")
                    with (DATA / "dataset.jsonl").open("w") as stream:
                        for item in dataset(count, int(body.get("seed", 42))):
                            stream.write(json.dumps(item)+"\n")
                    return self.send_json(report)
                finally:
                    EVAL_LOCK.release()
            if path == "/api/dataset" and not post:
                if body.get("suite") == "live_ai":
                    from .benchmark_data import natural_cases
                    report = saved_reports()["live_ai"]
                    count = report["count"] if report else 60
                    items = natural_cases()[:10 if count == 20 else 30]
                    return self.send_bytes("".join(json.dumps(item)+"\n" for item in items).encode(), "application/x-ndjson", 'attachment; filename="amnesia-live-ai-gold.jsonl"')
                if body.get("suite") == "policy":
                    report = saved_reports()["policy"]
                    count, seed = (report["count"], report.get("seed", 42)) if report else (600, 42)
                    return self.send_bytes("".join(json.dumps(item)+"\n" for item in dataset(count, seed)).encode(), "application/x-ndjson", 'attachment; filename="amnesia-policy-gold.jsonl"')
                file = DATA / "dataset.jsonl"
                if not file.exists():
                    raise ValueError("Run an evaluation to generate the dataset first.")
                return self.send_bytes(file.read_bytes(), "application/x-ndjson", 'attachment; filename="amnesia-dataset.jsonl"')
            mem = Memory(DATA / "memory.sqlite3")
            if path == "/api/workspaces":
                if post:
                    name = body.get("name", "New workspace")
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError("A workspace name is required.")
                    return self.send_json({"id": mem.create_workspace(name.strip())}, 201)
                return self.send_json(mem.rows("SELECT * FROM workspaces ORDER BY rowid DESC"))
            if path == "/api/state" and not post:
                return self.send_json(mem.state(body.get("workspace_id"), body.get("as_of")))
            if path == "/api/export" and not post:
                state = mem.export_workspace(body.get("workspace_id"))
                return self.send_bytes(json.dumps(state, indent=2).encode(), "application/json", 'attachment; filename="amnesia-workspace.json"')
            if path == "/api/import" and post:
                return self.send_json({"id": mem.import_workspace(body.get("workspace"), body.get("name"))}, 201)
            if path == "/api/conflicts/resolve" and post:
                return self.send_json(mem.resolve_conflict(body.get("workspace_id"), body.get("session_id"), body.get("fact_id"), body.get("evidence")))
            if path == "/api/sessions" and post:
                return self.send_json({"id": mem.create_session(body.get("workspace_id"))}, 201)
            if path == "/api/scenarios/load" and post:
                return self.send_json({"id": load_scenario(mem, body.get("scenario"))}, 201)
            if path == "/api/events" and post:
                c = configuration()
                return self.send_json(mem.ingest(body.get("workspace_id"), body.get("session_id"), body.get("text"), body.get("observed_at"), "local" if c["provider"] == "offline" else "ai", config=c, request_id=body.get("request_id"), new_session=body.get("new_session", False)))
            if path == "/api/query" and post:
                return self.send_json(mem.query(body.get("workspace_id"), body.get("question"), method=body.get("method", "hybrid"), as_of=body.get("as_of"), k=int(body.get("k", 5)), gate=bool(body.get("gate", True)), persist=bool(body.get("persist", False)), sid=body.get("session_id"), config=configuration()))
            return self.send_json({"error": "API route not found."}, 404)
        except (ValueError, TypeError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            # Keep server-only details and credentials out of browser responses.
            print("API error:", type(exc).__name__, str(exc))
            self.send_json({"error": "The local server could not complete the request. Check its terminal output."}, 500)
        finally:
            if mem:
                mem.close()

    def send_bytes(self, body, mime, disposition=None):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(body)

    def static(self, path):
        base = (ROOT / "dist").resolve()
        file = (base / path.lstrip("/")).resolve()
        if base not in file.parents:
            file = base / "index.html"
        if not file.is_file():
            file = base / "index.html"
        if not file.exists():
            return self.send_json({"error": "Frontend not built. Run npm run dev or npm run build."}, 404)
        return self.send_bytes(file.read_bytes(), mimetypes.guess_type(str(file))[0] or "application/octet-stream")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--production", action="store_true", help="Serve the compiled frontend from dist/")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    mem = Memory(DATA / "memory.sqlite3")
    seed(mem)
    mem.close()
    preferred = args.port or int(os.environ.get("AMNESIA_API_PORT", 8787))
    for port in range(preferred, preferred + (1 if args.port else 30)):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            if args.port or port == preferred + 29:
                raise
    print("Amnesia API%s: http://127.0.0.1:%d" % (" + app" if args.production else "", port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
