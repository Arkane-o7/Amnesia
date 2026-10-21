"""Freeze independently declared evaluation inputs for the review archive."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.evaluate import dataset
from backend.benchmark_data import natural_cases
folder = ROOT / "data"
folder.mkdir(exist_ok=True)
for name, items in (("policy-gold-600.jsonl", dataset(600, 42)), ("live-ai-gold-30.jsonl", natural_cases())):
    file = folder / name
    file.write_text("".join(json.dumps(item, ensure_ascii=False)+"\n" for item in items))
    print(file)
