"""Optional per-answer, disjoint-clue-word selection stage for the one-cell generator."""
from __future__ import annotations

import argparse
from array import array
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import LEVELS, level_rank
from storage import PRIVATE_ROOT, private_output
from scripts.enumerate_one import SCHEMA
from difficulty import MODEL, load_counts, reference_scores, reference_score


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def priority(refs, ranks):
    """Lexicographic maximin across the FOUR clue words, not the shared answer."""
    score = 0
    for rank in sorted(ranks[ref] for ref in refs):
        score = score * 8 + rank
    return score


def select_rows(rows, ranks, scores=None):
    """Rows: (source_id, top, left, bottom, right), ascending source_id.

    Returns canonical count and greedy choices in descending difficulty priority
    when scores are supplied; otherwise retains the legacy HSK-level ordering.
    Compact integer arrays keep the largest answer's candidate pool bounded.
    Equal priority is broken by the original puzzle ID (lowest first).
    """
    buckets = defaultdict(lambda: array("Q"))
    previous = -1
    candidate_count = 0
    base = max(max(scores[0].values(), default=0), max(scores[1].values(), default=0)) + 1 if scores is not None else None
    for row in rows:
        if len(row) != 5 or row[0] <= previous:
            raise ValueError("Selection rows must have five integers and increasing unique source IDs")
        previous = row[0]
        candidate_count += 1
        refs = row[1:]
        if len(set(refs)) != 4:
            raise ValueError("A source puzzle repeats a clue word")
        buckets[priority(refs, ranks) if scores is None else reference_score(refs, scores, base)].extend(row)
    used = set()
    chosen = []
    for score in sorted(buckets, reverse=True):
        bucket = buckets[score]
        for index in range(0, len(bucket), 5):
            source_id, top, left, bottom, right = bucket[index:index + 5]
            refs = (top, left, bottom, right)
            if used.isdisjoint(refs):
                chosen.append((source_id, *refs, score))
                used.update(refs)
    return candidate_count, chosen


def select_database(source, output, maximum="7-9", progress=None, mode="branch-count"):
    if mode not in {"branch-count", "hsk-level"}:
        raise ValueError("Unknown selection mode")
    source, output = Path(source).resolve(), private_output(output)
    staging = output.with_name(output.name + ".partial")
    if source == output or output.exists() or staging.exists():
        raise FileExistsError("Source must be preserved; use a new output path without an existing partial file")
    started = time.perf_counter()
    source_hash = file_hash(source)
    source_summary = json.loads(source.with_suffix(".summary.json").read_text(encoding="utf-8"))
    if source_summary["sha256"] != source_hash:
        raise ValueError("Source dataset checksum mismatch")
    if (source_summary["puzzle_type"] != "one-character-standard"
            or not source_summary.get("positional_swaps_preserved")
            or level_rank(source_summary["max_level"]) < level_rank(maximum)):
        raise ValueError("Expected a complete one-character dataset covering the requested HSK ceiling")
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original, closing(sqlite3.connect(staging)) as selected:
        selected.executescript(SCHEMA)
        selected.executescript("""
        CREATE TABLE selection_stats (
            answer_id INTEGER PRIMARY KEY REFERENCES words(id),
            eligible_source_puzzles INTEGER NOT NULL,
            canonical_candidates INTEGER NOT NULL,
            selected_puzzles INTEGER NOT NULL,
            discarded_for_word_overlap INTEGER NOT NULL
        );
        CREATE TABLE selection_trace (
            puzzle_id INTEGER PRIMARY KEY REFERENCES puzzles(id),
            source_puzzle_id INTEGER NOT NULL UNIQUE,
            choice_number INTEGER NOT NULL,
            sorted_clue_levels_json TEXT NOT NULL,
            priority INTEGER NOT NULL
        );
        """)
        words = original.execute("SELECT * FROM words ORDER BY id").fetchall()
        selected.executemany("INSERT INTO words VALUES (?,?,?,?,?,?)", words)
        ranks = {r[0]: r[2] for r in words}
        scores = reference_scores({r[0]: r[1] for r in words}, load_counts()) if mode == "branch-count" else None
        available = dict(original.execute("SELECT answer_id,count(*) FROM puzzles WHERE max_hsk_level<=? GROUP BY answer_id",
                                          (level_rank(maximum),)))
        source_answer_stats = original.execute("SELECT * FROM answer_stats ORDER BY answer_id").fetchall()
        counts, level_counts, answer_uses, edge_uses, histogram = Counter(), Counter(), Counter(), Counter(), Counter()
        total = canonical_total = 0
        last_progress = time.perf_counter()
        for answer_id, source_candidates, _, source_rejected in source_answer_stats:
            rows = original.execute("""
                SELECT id,top_word_id,left_word_id,bottom_word_id,right_word_id
                FROM puzzles WHERE answer_id=? AND max_hsk_level<=?
                AND top_word_id<left_word_id AND bottom_word_id<right_word_id ORDER BY id
            """, (answer_id, level_rank(maximum)))
            canonical_count, chosen = select_rows(rows, ranks, scores)
            if canonical_count * 4 != available.get(answer_id, 0):
                raise AssertionError("Source does not have all four orientation variants")
            canonical_total += canonical_count
            counts[answer_id] = len(chosen)
            if chosen:
                histogram[len(chosen)] += 1
            for choice, (source_id, top, left, bottom, right, score) in enumerate(chosen, 1):
                refs = (top, left, bottom, right)
                total += 1
                highest = max(ranks[answer_id], *(ranks[ref] for ref in refs))
                selected.execute("INSERT INTO puzzles VALUES (?,?,?,?,?,?,?)", (total, answer_id, *refs, highest))
                selected.execute("INSERT INTO selection_trace VALUES (?,?,?,?,?)",
                                 (total, source_id, choice, json.dumps([LEVELS[ranks[r] - 1] for r in sorted(refs, key=ranks.get)]), score))
                level_counts[highest] += 1
                answer_uses[answer_id] += 1
                edge_uses.update(refs)
            selected.execute("INSERT INTO answer_stats VALUES (?,?,?,?)",
                             (answer_id, source_candidates, len(chosen), source_rejected))
            selected.execute("INSERT INTO selection_stats VALUES (?,?,?,?,?)",
                             (answer_id, available.get(answer_id, 0), canonical_count, len(chosen),
                              available.get(answer_id, 0) - len(chosen)))
            if progress and time.perf_counter() - last_progress >= 10:
                progress(f"processed answers={len(counts)}; selected={total:,}; canonical candidates scanned={canonical_total:,}")
                last_progress = time.perf_counter()
        selected.executemany("INSERT INTO level_stats VALUES (?,?)", sorted(level_counts.items()))
        selected.executemany("INSERT INTO word_usage VALUES (?,?,?)",
                             [(r, answer_uses[r], edge_uses[r]) for r in sorted(set(answer_uses) | set(edge_uses))])
        selected.execute("CREATE INDEX idx_puzzles_answer ON puzzles(answer_id)")
        selected.execute("CREATE INDEX idx_puzzles_level_answer ON puzzles(max_hsk_level,answer_id)")
        summary = {
            "schema_version": 2, "puzzle_type": "one-character-standard", "max_level": maximum,
            "selection_policy": "per-answer-disjoint-clue-words-" + ("high-difficulty-first" if scores is not None else "high-level-first"),
            "difficulty_model": MODEL if scores is not None else "legacy-hsk-maximin",
            "priority": ("Four top/left prefix counts and bottom/right suffix counts sorted ascending, compared lexicographically descending; all HSK + CC-CEDICT two-character words"
                         if scores is not None else "Four clue-word HSK ranks sorted ascending, compared lexicographically descending; 7 means 7-9"),
            "tie_break": "ascending source puzzle ID; canonical top<left and bottom<right by word ID",
            "generator_constraint_only": True, "answer_word_excluded_from_overlap": True,
            "cross_answer_word_reuse_allowed": True, "maximum_cardinality_claimed": False,
            "source_file": source.name, "source_sha256": source_hash,
            "source_puzzle_count": source_summary["puzzle_count"],
            "eligible_source_puzzles": sum(available.values()), "canonical_candidates": canonical_total,
            "puzzle_count": total, "discarded_for_word_overlap": sum(available.values()) - total,
            "answers_with_puzzles": sum(c > 0 for c in counts.values()),
            "puzzles_per_answer_histogram": dict(sorted(histogram.items())),
            "counts_by_max_hsk_level": {LEVELS[k - 1]: v for k, v in sorted(level_counts.items())},
            "distinct_letters": True, "positional_swaps_preserved": False,
            "uniqueness_scope": source_summary["uniqueness_scope"], "sources": source_summary["sources"],
            "license": "CC-BY-SA-4.0",
        }
        selected.execute("INSERT INTO metadata VALUES (?,?)", ("build", json.dumps(summary, ensure_ascii=False)))
        selected.commit()
        assert selected.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert selected.execute("PRAGMA foreign_key_check").fetchall() == []
        # Validate non-reuse across every selected row, grouped by answer.
        seen = defaultdict(set)
        for answer_id, top, left, bottom, right in selected.execute(
                "SELECT answer_id,top_word_id,left_word_id,bottom_word_id,right_word_id FROM puzzles"):
            refs = (top, left, bottom, right)
            assert seen[answer_id].isdisjoint(refs)
            seen[answer_id].update(refs)
        assert sum(len(refs) for refs in seen.values()) == total * 4
    if file_hash(source) != source_hash:
        raise AssertionError("Source dataset changed during selection")
    staging.replace(output)
    summary.update({"file": output.name, "bytes": output.stat().st_size,
                    "sha256": file_hash(output), "source_unchanged": True,
                    "elapsed_seconds": time.perf_counter() - started})
    output.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-all.sqlite")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("branch-count", "hsk-level"), default="branch-count")
    parser.add_argument("--max-level", choices=LEVELS, default="7-9")
    args = parser.parse_args()
    output = args.output or PRIVATE_ROOT / "datasets" / ("one-standard-hsk-branching-lexicographic.sqlite" if args.mode == "branch-count" else "one-standard-hsk-disjoint.sqlite")
    summary = select_database(args.source, output, args.max_level, lambda msg: print(msg, flush=True), args.mode)
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
