"""Package only application source, synthetic artifacts, and review materials."""
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "release/Amnesia-final-review.zip"
ALLOWED_DIRS = ("backend", "src", "public", "scripts", "tests", "docs", "data", "dist")
ROOT_FILES = ("README.md", "package.json", "package-lock.json", "tsconfig.json", "vite.config.ts", "index.html", ".gitignore", "Start Amnesia.command", "requirements-report.txt")
ARTIFACTS = ("output/evaluation-policy.json", "output/evaluation-policy.jsonl", "output/evaluation-codex.json", "output/evaluation-codex.jsonl", "output/evaluation-openai.json", "output/evaluation-openai.jsonl", "output/evaluation-ollama-final.json", "output/evaluation-ollama-final.jsonl", "output/pdf/amnesia-final-report.pdf")
files = [ROOT/f for f in ROOT_FILES+ARTIFACTS if (ROOT/f).is_file()]
for directory in ALLOWED_DIRS:
    files.extend(f for f in (ROOT/directory).rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc")
for file in files:
    relative = file.relative_to(ROOT)
    if any(part in (".amnesia", ".amnesia-preview", ".env", "node_modules") for part in relative.parts) or file.name == "credentials.json":
        raise SystemExit("Private runtime data must never enter the review package.")
manifest = ROOT / "docs/release-manifest.json"
files = [file for file in set(files) if file != manifest]
manifest.write_text(json.dumps({"version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(), "algorithm": "SHA256", "files": {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(files)}}, indent=2)+"\n")
files.append(manifest)
OUT.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(set(files)):
        archive.write(file, "Amnesia/" + str(file.relative_to(ROOT)))
digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
OUT.with_suffix(".sha256").write_text(digest+"  "+OUT.name+"\n")
print("%s\n%d files; %.1f MB\nSHA256 %s" % (OUT, len(set(files)), OUT.stat().st_size/1024/1024, digest))
