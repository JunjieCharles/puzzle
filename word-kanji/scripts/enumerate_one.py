"""Exhaustively generate one-character standard puzzles into a queryable SQLite file."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import LEVELS, Lexicon, level_rank
from storage import PRIVATE_ROOT, private_output
from scripts.estimate_space import count_space


def canonical_candidates(lexicon, maximum="7-9"):
    """Yield (answer, top, left, bottom, right, unique), top<left and bottom<right.

    Every result has four distinct fixed letters, all different from the answer.
    Uniqueness uses the entire broad lexicon, including repeated-letter rivals.
    Each canonical result represents exactly four positional puzzle layouts.
    """
    common = lexicon.words_up_to(maximum)
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for word in common:
        if len(word) == 2:
            incoming[word[1]].add(word[0])
            outgoing[word[0]].add(word[1])
    bits = {c: 1 << i for i, c in enumerate(lexicon.broad_answers[1])}
    after, before = defaultdict(int), defaultdict(int)
    for word in lexicon.broad_two:
        after[word[0]] |= bits.get(word[1], 0)
        before[word[1]] |= bits.get(word[0], 0)
    for answer in sorted(w for w in common if len(w) == 1):
        ins = sorted(incoming[answer] - {answer})
        outs = sorted(outgoing[answer] - {answer})
        if len(ins) < 2 or len(outs) < 2:
            continue
        bottom_pairs = [(b, r, before[b] & before[r]) for b, r in itertools.combinations(outs, 2)]
        for top, left in itertools.combinations(ins, 2):
            possible = after[top] & after[left]
            for bottom, right, lower_possible in bottom_pairs:
                if top == bottom or top == right or left == bottom or left == right:
                    continue
                solutions = possible & lower_possible
                if not solutions & bits[answer]:
                    raise AssertionError("An HSK candidate lost its intended answer in the broad lexicon")
                yield answer, top, left, bottom, right, solutions == bits[answer]


def orientations(top, left, bottom, right):
    yield top, left, bottom, right
    yield left, top, bottom, right
    yield top, left, right, bottom
    yield left, top, right, bottom


SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE words (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    hsk_level INTEGER NOT NULL CHECK(hsk_level BETWEEN 1 AND 7),
    hsk_label TEXT NOT NULL,
    listed_levels_json TEXT NOT NULL,
    source_entries_json TEXT NOT NULL
);
CREATE TABLE puzzles (
    id INTEGER PRIMARY KEY,
    answer_id INTEGER NOT NULL REFERENCES words(id),
    top_word_id INTEGER NOT NULL REFERENCES words(id),
    left_word_id INTEGER NOT NULL REFERENCES words(id),
    bottom_word_id INTEGER NOT NULL REFERENCES words(id),
    right_word_id INTEGER NOT NULL REFERENCES words(id),
    max_hsk_level INTEGER NOT NULL CHECK(max_hsk_level BETWEEN 1 AND 7)
);
CREATE TABLE answer_stats (
    answer_id INTEGER PRIMARY KEY REFERENCES words(id),
    candidate_count INTEGER NOT NULL,
    puzzle_count INTEGER NOT NULL,
    rejected_multiple_count INTEGER NOT NULL
);
CREATE TABLE level_stats (max_hsk_level INTEGER PRIMARY KEY, puzzle_count INTEGER NOT NULL);
CREATE TABLE word_usage (
    word_id INTEGER PRIMARY KEY REFERENCES words(id),
    answer_uses INTEGER NOT NULL,
    edge_uses INTEGER NOT NULL
);
CREATE VIEW puzzle_details AS
SELECT p.id, a.word AS answer, a.hsk_label AS answer_level,
       substr(t.word,1,1) AS top, substr(l.word,1,1) AS left,
       substr(b.word,2,1) AS bottom, substr(r.word,2,1) AS right,
       t.word AS top_word, t.hsk_label AS top_level,
       l.word AS left_word, l.hsk_label AS left_level,
       b.word AS bottom_word, b.hsk_label AS bottom_level,
       r.word AS right_word, r.hsk_label AS right_level,
       CASE p.max_hsk_level WHEN 7 THEN '7-9' ELSE CAST(p.max_hsk_level AS TEXT) END AS max_level
FROM puzzles p
JOIN words a ON a.id=p.answer_id JOIN words t ON t.id=p.top_word_id
JOIN words l ON l.id=p.left_word_id JOIN words b ON b.id=p.bottom_word_id
JOIN words r ON r.id=p.right_word_id;
"""


def build_database(lexicon, output, maximum="7-9", progress=None):
    """Write a staging database; publish only after complete enumeration and checks."""
    output = private_output(output)
    staging = output.with_name(output.name + ".partial")
    if output.exists() or staging.exists():
        raise FileExistsError(f"Output or partial file already exists: {output}; use a new --output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    _, spaces = count_space(lexicon, 1, maximum)
    expected = sum(s[2] for s in spaces)
    records = sorted((r for r in lexicon.records.values() if len(r["word"]) in (1, 2)), key=lambda r: r["word"])
    word_ids = {r["word"]: i for i, r in enumerate(records, 1)}
    ranks = {r["word"]: level_rank(r["level"]) for r in records}
    candidate_counts, answer_counts, rejected_counts = Counter(), Counter(), Counter()
    level_counts, edge_uses = Counter(), Counter()
    candidates = emitted = 0
    pending = []
    last_progress = time.perf_counter()
    connection = sqlite3.connect(staging)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA cache_size=-65536")
        connection.executescript(SCHEMA)
        connection.executemany("INSERT INTO words VALUES (?,?,?,?,?,?)", [
            (word_ids[r["word"]], r["word"], ranks[r["word"]], r["level"],
             json.dumps(r.get("levels", [r["level"]]), ensure_ascii=False),
             json.dumps(r.get("entries", []), ensure_ascii=False)) for r in records])
        connection.commit()
        def flush():
            if pending:
                connection.executemany("INSERT INTO puzzles VALUES (?,?,?,?,?,?,?)", pending)
                connection.commit()
                pending.clear()

        for answer, top, left, bottom, right, unique in canonical_candidates(lexicon, maximum):
            answer_id = word_ids[answer]
            candidates += 4
            candidate_counts[answer_id] += 4
            if not unique:
                rejected_counts[answer_id] += 4
                continue
            edge_words = (top + answer, left + answer, answer + bottom, answer + right)
            word_refs = tuple(word_ids[w] for w in edge_words)
            highest = max(ranks[answer], *(ranks[w] for w in edge_words))
            t, l, b, r = word_refs
            for refs in ((t, l, b, r), (l, t, b, r), (t, l, r, b), (l, t, r, b)):
                emitted += 1
                pending.append((emitted, answer_id, *refs, highest))
            answer_counts[answer_id] += 4
            level_counts[highest] += 4
            for ref in word_refs:
                edge_uses[ref] += 4
            if len(pending) >= 20000:
                flush()
                now = time.perf_counter()
                if progress and now - last_progress >= 10:
                    progress(f"candidates={candidates:,}/{expected:,}; stored={emitted:,}; elapsed={now-started:.1f}s")
                    last_progress = now
        flush()
        if candidates != expected or candidates != emitted + sum(rejected_counts.values()):
            raise AssertionError("Enumeration count disagrees with independent combinatorial count")
        connection.executemany("INSERT INTO answer_stats VALUES (?,?,?,?)", [
            (a, candidate_counts[a], answer_counts[a], rejected_counts[a]) for a in sorted(candidate_counts)])
        connection.executemany("INSERT INTO level_stats VALUES (?,?)", sorted(level_counts.items()))
        connection.executemany("INSERT INTO word_usage VALUES (?,?,?)", [
            (i, answer_counts[i], edge_uses[i]) for i in sorted(set(answer_counts) | set(edge_uses))])
        connection.commit()
        if progress:
            progress(f"Enumeration done: {emitted:,} puzzles. Creating statistics indexes and checking database.")
        connection.execute("CREATE INDEX idx_puzzles_answer ON puzzles(answer_id)")
        connection.execute("CREATE INDEX idx_puzzles_level_answer ON puzzles(max_hsk_level, answer_id)")
        connection.execute("ANALYZE")
        summary = {
            "schema_version": 1, "puzzle_type": "one-character-standard", "max_level": maximum,
            "level_encoding": {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7-9"},
            "candidate_count": candidates, "puzzle_count": emitted,
            "rejected_multiple_count": sum(rejected_counts.values()),
            "answers_with_candidates": len(candidate_counts), "answers_with_puzzles": sum(c > 0 for c in answer_counts.values()),
            "counts_by_max_hsk_level": {LEVELS[k-1]: v for k, v in sorted(level_counts.items())},
            "distinct_letters": True, "positional_swaps_preserved": True,
            "uniqueness_scope": "All HSK words plus CC-CEDICT snapshot; repeated-letter alternatives are included",
            "sources": lexicon.metadata,
            "elapsed_seconds_before_final_checks": time.perf_counter() - started,
            "license": "CC-BY-SA-4.0",
        }
        connection.execute("INSERT INTO metadata VALUES (?,?)", ("build", json.dumps(summary, ensure_ascii=False)))
        connection.commit()
        if connection.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0] != emitted:
            raise AssertionError("Stored row count mismatch")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise AssertionError("SQLite integrity check failed")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")
    finally:
        connection.close()
    staging.replace(output)
    summary["file"] = output.name
    summary["bytes"] = output.stat().st_size
    with output.open("rb") as handle:
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    summary["sha256"] = digest.hexdigest()
    summary["elapsed_seconds"] = time.perf_counter() - started
    output.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8", newline="\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-level", choices=LEVELS, default="7-9")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--disjoint-words-from", type=Path,
                        help="Optional generator filter: select high-difficulty-first, non-repeating clue words per answer from an existing full dataset")
    args = parser.parse_args()
    try:
        if args.disjoint_words_from:
            from scripts.select_one import select_database
            output = args.output or PRIVATE_ROOT / "datasets" / "one-standard-hsk-branching-lexicographic.sqlite"
            summary = select_database(args.disjoint_words_from, output, args.max_level, lambda msg: print(msg, flush=True))
        else:
            output = args.output or PRIVATE_ROOT / "datasets" / "one-standard-hsk-all.sqlite"
            summary = build_database(Lexicon.load(), output, args.max_level, lambda msg: print(msg, flush=True))
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
