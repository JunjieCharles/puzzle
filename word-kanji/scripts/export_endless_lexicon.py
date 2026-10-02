"""Export complete generic vocabulary only; no puzzle selection or answer mapping."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon


def payload():
    lexicon = Lexicon.load()
    return {"version": "endless-lexicon-v1",
            "common": sorted(w for w in lexicon.records if len(w) in (1, 2)),
            "broad": sorted(set(lexicon.broad_answers[1]) | lexicon.broad_two)}


if __name__ == "__main__":
    data = (json.dumps(payload(), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    (ROOT / "public" / "endless-lexicon.json").write_bytes(data)
    print(f"Generic vocabulary: {len(data)} bytes, SHA-256 {hashlib.sha256(data).hexdigest()}")
