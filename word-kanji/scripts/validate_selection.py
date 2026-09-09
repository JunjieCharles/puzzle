"""Validate every selected puzzle and prove the greedy order against all source candidates."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import LEVELS, Lexicon, Puzzle, level_rank, solve
from storage import PRIVATE_ROOT
from scripts.select_one import file_hash


def validate(source, output):
    started = time.perf_counter()
    source, output = Path(source).resolve(), Path(output).resolve()
    summary = json.loads(output.with_suffix(".summary.json").read_text(encoding="utf-8"))
    assert file_hash(source) == summary["source_sha256"]
    assert file_hash(output) == summary["sha256"]
    lexicon = Lexicon.load()
    assert summary["sources"] == lexicon.metadata
    selected_groups = defaultdict(list)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original, closing(
            sqlite3.connect(output.as_uri() + "?mode=ro", uri=True)) as selected:
        assert selected.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert selected.execute("PRAGMA foreign_key_check").fetchall() == []
        word_rows = selected.execute("SELECT * FROM words ORDER BY id").fetchall()
        assert word_rows == original.execute("SELECT * FROM words ORDER BY id").fetchall()
        ranks = {r[0]: r[2] for r in word_rows}
        words = {r[0]: r[1] for r in word_rows}
        levels = Counter()
        rows = selected.execute("""
            SELECT p.id,p.answer_id,p.top_word_id,p.left_word_id,p.bottom_word_id,p.right_word_id,
                   p.max_hsk_level,t.source_puzzle_id,t.choice_number
            FROM puzzles p JOIN selection_trace t ON t.puzzle_id=p.id ORDER BY p.id
        """).fetchall()
        assert len(rows) == summary["puzzle_count"] == selected.execute("SELECT count(*) FROM puzzles").fetchone()[0]
        for number, (_, answer_id, top, left, bottom, right, highest, source_id, choice) in enumerate(rows, 1):
            refs = (top, left, bottom, right)
            expected = original.execute("SELECT answer_id,top_word_id,left_word_id,bottom_word_id,right_word_id,max_hsk_level FROM puzzles WHERE id=?",
                                        (source_id,)).fetchone()
            assert expected == (answer_id, *refs, highest)
            answer = words[answer_id]
            t, l, b, r = (words[ref] for ref in refs)
            puzzle = Puzzle((t[0],), (b[1],), l[0], r[1])
            assert (t[1], l[1], b[0], r[0]) == (answer,) * 4
            assert puzzle.distinct(answer)
            assert solve(puzzle, lexicon) == [answer]
            assert highest == max(ranks[answer_id], *(ranks[r] for r in refs))
            levels[highest] += 1
            assert choice == len(selected_groups[answer_id]) + 1
            key = tuple(-r for r in sorted(ranks[r] for r in refs)) + (source_id,)
            selected_groups[answer_id].append((key, refs))
            if number % 300 == 0:
                print(f"Validated {number}/{len(rows)} selected puzzles with the original full-scan solver", flush=True)
        assert {LEVELS[k - 1]: v for k, v in levels.items()} == summary["counts_by_max_hsk_level"]
        scanned = 0
        # Independent full-candidate proof: find the FIRST selected puzzle which
        # blocks each candidate. That selected puzzle must outrank the candidate;
        # otherwise the candidate was still available and should have won then.
        for answer_id, count in original.execute("SELECT answer_id,count(*) FROM puzzles WHERE max_hsk_level<=? GROUP BY answer_id",
                                                  (level_rank(summary["max_level"]),)):
            choices = selected_groups[answer_id]
            assert choices
            used_at = {}
            for index, (key, refs) in enumerate(choices):
                assert all(ref not in used_at for ref in refs), "Repeated clue word for an answer"
                used_at.update({ref: index for ref in refs})
            candidates = original.execute("""
                SELECT id,top_word_id,left_word_id,bottom_word_id,right_word_id FROM puzzles
                WHERE answer_id=? AND max_hsk_level<=?
                AND top_word_id<left_word_id AND bottom_word_id<right_word_id
            """, (answer_id, level_rank(summary["max_level"])))
            per_answer = 0
            for source_id, top, left, bottom, right in candidates:
                refs = (top, left, bottom, right)
                blockers = [used_at[r] for r in refs if r in used_at]
                assert blockers, "An unused non-overlapping candidate remains"
                blocker = min(blockers)
                candidate_key = tuple(-r for r in sorted(ranks[r] for r in refs)) + (source_id,)
                assert choices[blocker][0] <= candidate_key, "Greedy high-level/source-ID order violated"
                per_answer += 1
            assert per_answer * 4 == count
            scanned += per_answer
        assert scanned == summary["canonical_candidates"]
    report = {"file": output.name, "sha256": summary["sha256"], "source_sha256": summary["source_sha256"],
              "validated_selected_puzzles": len(rows), "original_solver_unique_for_all_selected": True,
              "source_words_grades_and_rows_preserved": True, "per_answer_clue_words_disjoint": True,
              "canonical_source_candidates_checked_for_greedy_order": scanned,
              "high_level_first_and_tie_break_verified": True,
              "no_unblocked_candidate_remains": True, "elapsed_seconds": time.perf_counter() - started}
    output.with_suffix(".validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-all.sqlite")
    parser.add_argument("--selected", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-disjoint.sqlite")
    args = parser.parse_args()
    validate(args.source, args.selected)
