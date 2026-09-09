"""Read-only validation of a completed exhaustive one-character puzzle dataset."""
import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon, Puzzle, level_rank, solve
from storage import PRIVATE_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-all.sqlite")
    args = parser.parse_args()
    started = time.perf_counter()
    summary = json.loads(args.path.with_suffix(".summary.json").read_text(encoding="utf-8"))
    lexicon = Lexicon.load()
    assert summary["sources"] == lexicon.metadata, "Dataset and validation lexicons differ"
    digest = hashlib.sha256()
    with args.path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest() == summary["sha256"], "Dataset SHA-256 mismatch"
    with closing(sqlite3.connect(args.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        count, first, last = db.execute("SELECT count(*),min(id),max(id) FROM puzzles").fetchone()
        assert (count, first, last) == (summary["puzzle_count"], 1, summary["puzzle_count"])
        levels = dict(db.execute("SELECT max_hsk_level,count(*) FROM puzzles GROUP BY max_hsk_level"))
        assert levels == dict(db.execute("SELECT * FROM level_stats"))
        expected_levels = {level_rank(k): v for k, v in summary["counts_by_max_hsk_level"].items()}
        assert levels == expected_levels
        answers = dict(db.execute("SELECT answer_id,count(*) FROM puzzles GROUP BY answer_id"))
        assert answers == dict(db.execute("SELECT answer_id,puzzle_count FROM answer_stats WHERE puzzle_count>0"))
        assert sum(row[0] for row in db.execute("SELECT candidate_count FROM answer_stats")) == summary["candidate_count"]
        assert db.execute("SELECT SUM(answer_uses),SUM(edge_uses) FROM word_usage").fetchone() == (count, 4 * count)
        sample_ids = {first, last}
        sample_ids.update(random.Random(20260909).sample(range(1, count + 1), min(count, 128)))
        sample_ids.update(row[0] for row in db.execute("SELECT MIN(id) FROM puzzles GROUP BY answer_id"))
        sample_ids.update(row[0] for row in db.execute("SELECT MIN(id) FROM puzzles GROUP BY max_hsk_level"))
        db.row_factory = sqlite3.Row
        for number, ident in enumerate(sorted(sample_ids), 1):
            row = db.execute("SELECT * FROM puzzle_details WHERE id=?", (ident,)).fetchone()
            puzzle = Puzzle((row["top"],), (row["bottom"],), row["left"], row["right"])
            answer = row["answer"]
            assert puzzle.distinct(answer)
            assert solve(puzzle, lexicon) == [answer], f"Uniqueness failed for {ident}"
            words = [answer]
            for position in ("top", "left", "bottom", "right"):
                word = row[position] + answer if position in ("top", "left") else answer + row[position]
                assert word == row[position + "_word"]
                assert row[position + "_level"] == lexicon.records[word]["level"]
                words.append(word)
            assert row["answer_level"] == lexicon.records[answer]["level"]
            assert level_rank(row["max_level"]) == max(level_rank(lexicon.records[w]["level"]) for w in words)
            if number % 200 == 0:
                print(f"Cross-checked {number}/{len(sample_ids)} rows with the original full-scan solver", flush=True)
    result = {"dataset": args.path.name, "sha256": digest.hexdigest(), "puzzle_count": count,
              "integrity_check": "ok", "foreign_keys": "ok", "stored_statistics": "matched",
              "independent_full_scan_solver_samples": len(sample_ids),
              "sampling": "128 seeded random IDs + first row per answer and per max level + endpoints",
              "sampled_distinctness_and_word_grades": "matched",
              "elapsed_seconds": time.perf_counter() - started}
    args.path.with_suffix(".validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                                       encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
