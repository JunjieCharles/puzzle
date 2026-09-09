"""Count distinct-letter candidate assignments exactly, then benchmark bounded samples.

This estimates the existing horizontal one/two-answer layouts; it does not
enumerate or save the full puzzle space. Run from any working directory.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import random
import sys
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon, Puzzle, solve


@lru_cache(maxsize=None)
def partitions(size):
    """Set partitions with the partition-lattice Moebius coefficient."""
    def visit(index, blocks):
        if index == size:
            weight = math.prod((-1) ** (b.bit_count() - 1) * math.factorial(b.bit_count() - 1)
                               for b in blocks)
            yield tuple(blocks), weight
            return
        for i in range(len(blocks)):
            updated = blocks.copy()
            updated[i] |= 1 << index
            yield from visit(index + 1, updated)
        yield from visit(index + 1, blocks + [1 << index])
    return tuple(visit(0, []))


def count_distinct(domains):
    """Exact injective assignments, without enumerating the Cartesian product."""
    alphabet = sorted(set().union(*domains))
    bit = {c: 1 << i for i, c in enumerate(alphabet)}
    masks = [sum(bit[c] for c in domain) for domain in domains]
    intersections = [0] * (1 << len(domains))
    intersections[0] = (1 << len(alphabet)) - 1
    sizes = [0] * len(intersections)
    for mask in range(1, len(intersections)):
        low = mask & -mask
        intersections[mask] = intersections[mask ^ low] & masks[low.bit_length() - 1]
        sizes[mask] = intersections[mask].bit_count()
    return sum(weight * math.prod(sizes[block] for block in blocks)
               for blocks, weight in partitions(len(domains)))


class IndexedAudit:
    """Benchmark prototype of the same full-lexicon solver using set intersections."""
    def __init__(self, lexicon):
        self.after = defaultdict(set)
        self.before = defaultdict(set)
        for word in lexicon.broad_two:
            self.after[word[0]].add(word[1])
            self.before[word[1]].add(word[0])
        self.single = set(lexicon.broad_answers[1])

    def solve(self, puzzle):
        if puzzle.size == 1:
            return sorted(self.after[puzzle.left] & self.after[puzzle.top[0]]
                          & self.before[puzzle.bottom[0]] & self.before[puzzle.right] & self.single)
        first = self.after[puzzle.left] & self.after[puzzle.top[0]] & self.before[puzzle.bottom[0]]
        second = self.after[puzzle.top[1]] & self.before[puzzle.bottom[1]] & self.before[puzzle.right]
        return sorted(a + b for a in first for b in self.after[a] & second)


def make_puzzle(size, clues):
    return Puzzle(tuple(clues[:size]), tuple(clues[size:2 * size]), clues[-2], clues[-1])


def count_space(lexicon, size, level):
    words = lexicon.words_up_to(level)
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for word in words:
        if len(word) == 2:
            incoming[word[1]].add(word[0])
            outgoing[word[0]].add(word[1])
    answers = sorted(w for w in words if len(w) == size and len(set(w)) == size)
    spaces = []
    for answer in answers:
        domains = ([incoming[c] for c in answer] + [outgoing[c] for c in answer]
                   + [incoming[answer[0]], outgoing[answer[-1]]])
        domains = [set(domain) - set(answer) for domain in domains]
        if any(not domain for domain in domains):
            continue
        count = count_distinct(domains)
        if count:
            spaces.append((answer, [tuple(sorted(d)) for d in domains], count))
    return answers, spaces


def self_check():
    rng = random.Random(42)
    for size in (4, 6):
        for _ in range(25):
            domains = [set(rng.sample("abcdefg", rng.randint(1, 4))) for _ in range(size)]
            expected = sum(len(set(c)) == size for c in itertools.product(*domains))
            assert count_distinct(domains) == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "space-estimate.json")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    self_check()
    lexicon = Lexicon.load()
    indexed = IndexedAudit(lexicon)
    rng = random.Random(20260910)
    results = []
    for level, size in itertools.product(("6", "7-9"), (1, 2)):
        started = time.perf_counter()
        answers, spaces = count_space(lexicon, size, level)
        count_seconds = time.perf_counter() - started
        total = sum(s[2] for s in spaces)
        weights = [s[2] for s in spaces]
        samples = []
        for _ in range(args.samples):
            answer, domains, _ = rng.choices(spaces, weights=weights)[0]
            while True:
                clues = tuple(rng.choice(d) for d in domains)
                if len(set(clues)) == len(clues):
                    break
            samples.append((make_puzzle(size, clues), answer))
        started = time.perf_counter()
        baseline = [solve(p, lexicon) for p, _ in samples]
        baseline_seconds = (time.perf_counter() - started) / len(samples)
        for (puzzle, _), expected in zip(samples, baseline):
            assert indexed.solve(puzzle) == expected
        started = time.perf_counter()
        for _ in range(100):
            for puzzle, _ in samples:
                indexed.solve(puzzle)
        indexed_seconds = (time.perf_counter() - started) / (len(samples) * 100)
        # Bounded real enumeration: includes product iteration, duplicate-letter
        # filtering, Puzzle construction, and indexed uniqueness auditing.
        enum_count = 0
        started = time.perf_counter()
        for _, domains, _ in rng.choices(spaces, weights=weights, k=8):
            accepted = 0
            for clues in itertools.product(*domains):
                if len(set(clues)) != len(clues):
                    continue
                indexed.solve(make_puzzle(size, clues))
                enum_count += 1
                accepted += 1
                if accepted >= 2000:
                    break
        enum_seconds = (time.perf_counter() - started) / enum_count
        unique = sum(solution == [answer] for solution, (_, answer) in zip(baseline, samples))
        row = {"max_level": level, "size": size, "hsk_answer_words": len(answers),
               "answers_with_distinct_clues": len(spaces), "candidate_assignments": total,
               "equivalent_clue_swaps_collapsed": total // 4,
               "count_seconds": count_seconds, "samples": len(samples), "sample_unique": unique,
               "sample_unique_fraction": unique / len(samples),
               "current_solver_seconds_per_candidate": baseline_seconds,
               "current_solver_full_seconds_estimate": baseline_seconds * total,
               "indexed_solver_seconds_per_candidate": indexed_seconds,
               "enumerate_and_indexed_audit_seconds_per_candidate": enum_seconds,
               "enumerate_and_indexed_audit_full_seconds_estimate": enum_seconds * total}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    output = {"python": platform.python_version(), "platform": platform.platform(),
              "logical_scope": "current fixed horizontal one/two-cell standard layouts; all characters distinct; before uniqueness filtering",
              "hsk_commit": lexicon.metadata["hsk_commit"], "cedict_date": lexicon.metadata["cedict_snapshot_date"],
              "results": results}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
