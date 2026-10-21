"""Background evaluation jobs with persisted progress and cooperative cancellation."""
import json
import threading
import time
import uuid
from .engine import data_dir

JOBS = {}
LOCK = threading.RLock()


def save(job):
    with LOCK:
        directory = data_dir() / "jobs"
        directory.mkdir(parents=True, exist_ok=True)
        serializable = {k: v for k, v in job.items() if k not in ("cancel",)}
        temp = directory / (job["id"] + ".tmp")
        temp.write_text(json.dumps(serializable))
        temp.replace(directory / (job["id"] + ".json"))


def get(jid):
    with LOCK:
        job = JOBS.get(jid)
        if job:
            return {k: v for k, v in job.items() if k != "cancel"}
    file = data_dir() / "jobs" / (jid + ".json")
    if not file.exists():
        raise ValueError("Evaluation job not found.")
    job = json.loads(file.read_text())
    if job["status"] in ("queued", "running"):
        job.update(status="interrupted", error="The server restarted before this job finished. Start a new run.")
    return job


def recent():
    directory = data_dir() / "jobs"
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if directory.exists() else []
    return [get(p.stem) for p in files[:10]]


def start(kind, work):
    with LOCK:
        if any(j["status"] in ("queued", "running") for j in JOBS.values()):
            raise ValueError("An evaluation is already running. Finish or cancel it before starting another.")
        jid = uuid.uuid4().hex[:16]
        job = {"id": jid, "kind": kind, "status": "queued", "completed": 0, "total": 0, "message": "Preparing evaluation", "started_at": time.time(), "elapsed_seconds": 0, "cancel": threading.Event()}
        JOBS[jid] = job
        save(job)
    def update(completed, total, message):
        with LOCK:
            job.update(status="running", completed=completed, total=total, message=message, elapsed_seconds=round(time.time()-job["started_at"], 1))
            save(job)
    def runner():
        try:
            result = work(update, job["cancel"].is_set)
            with LOCK:
                if job["cancel"].is_set():
                    job.update(status="cancelled", message="Cancelled. No partial run is reported as complete.")
                else:
                    job.update(status="completed", result=result, message="Evaluation complete", completed=job["total"])
                job["elapsed_seconds"] = round(time.time()-job["started_at"], 1)
                save(job)
        except Exception as exc:
            with LOCK:
                job.update(status="failed", error=str(exc), message="Evaluation failed", elapsed_seconds=round(time.time()-job["started_at"], 1))
                save(job)
    threading.Thread(target=runner, daemon=True).start()
    return get(jid)


def cancel(jid):
    with LOCK:
        job = JOBS.get(jid)
        if not job or job["status"] not in ("queued", "running"):
            raise ValueError("There is no active job to cancel.")
        job["cancel"].set()
        job["message"] = "Cancellation requested; waiting for the current model call."
        save(job)
    return get(jid)
