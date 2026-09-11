"""Build hardest two-cell puzzles privately; publish only whitelisted clues and digests."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import heapq
import itertools
import json
from pathlib import Path
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import Lexicon, Puzzle, solve
from difficulty import word_counts
from matching import maximum_matching
from storage import PRIVATE_ROOT, private_output
from scripts.estimate_space import IndexedAudit, count_distinct

VERSION = "kanji-two-v1"
MODEL = "broad-directional-word-count-lexicographic-six-v1"
ORDER_MODEL = "two-step-best-order-minimax-v1"
SELECTION_RULE = "global-answer-characters-and-word-guess-dedup-v1"


def clue_resources(answer, clues):
    """A word with its missing position; the middle word has both positions missing."""
    positions = (0, 1, 0, 1, 0, 1)
    incoming = (True, True, False, False, True, False)
    return {(c + answer[positions[i]], 1) if incoming[i] else (answer[positions[i]] + c, 0)
            for i, c in enumerate(clues)} | {(answer, 2)}


def exclude_used_clues(answer, domains, forbidden):
    positions = (0, 1, 0, 1, 0, 1)
    incoming = (True, True, False, False, True, False)
    return [{c for c in domain if c not in answer and
             ((c + answer[positions[i]], 1) if incoming[i] else (answer[positions[i]] + c, 0)) not in forbidden}
            for i, domain in enumerate(domains)]


def one_clue_resources(source, campaign):
    from scripts.export_campaign import digest_value
    def key(c):
        return tuple(sorted((c["top"], c["left"]))) + tuple(sorted((c["bottom"], c["right"])))
    public = {key(p["clues"]): p for p in campaign["puzzles"]}
    used, found = set(), set()
    source = private_output(source)
    db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT answer, top, left, bottom, right FROM puzzle_details"):
            p = public.get(key(row))
            if p is None:
                continue
            a = row["answer"]
            if digest_value(p["id"], p["salt"], a) != p["check"]:
                raise ValueError("One-cell private/public data mismatch")
            used.update(((row["top"] + a, 1), (row["left"] + a, 1),
                         (a + row["bottom"], 0), (a + row["right"], 0)))
            found.add(p["id"])
    finally:
        db.close()
    if len(found) != len(campaign["puzzles"]):
        raise ValueError("Missing one-cell private records")
    return used


def puzzle_from(clues):
    return Puzzle(tuple(clues[:2]), tuple(clues[2:4]), clues[4], clues[5])


def clue_score(clues, counts):
    starts, ends = counts
    return tuple(sorted((starts[clues[0]], starts[clues[1]], ends[clues[2]],
                         ends[clues[3]], starts[clues[4]], ends[clues[5]])))


def order_difficulty(answer, clues, counts):
    """Best solving order, with the hardest step as that order's difficulty."""
    starts, ends = counts
    first = min(starts[clues[0]], starts[clues[4]], ends[clues[2]])
    second = min(starts[clues[1]], ends[clues[3]], ends[clues[5]])
    first_then_second = max(first, min(second, starts[answer[0]]))
    second_then_first = max(second, min(first, ends[answer[1]]))
    return min(first_then_second, second_then_first)


def arrange_selected(rows, counts):
    # Selection and its same-score decisions are untouched. The previous key
    # breaks ties only after comparing the user's new minimax difficulty.
    return sorted(rows, key=lambda r: (order_difficulty(r["answer"], r["clues"], counts),
                                      tuple(r["difficulty"]), tuple(r["clues"]), r["answer"]))


def has_unique(answer, domains, audit):
    """Exhaustive existence search; intersecting all remaining clues is a safe bound."""
    order = sorted(range(6), key=lambda i: len(domains[i]))
    positions = (0, 1, 0, 1, 0, 1)
    incoming = (True, True, False, False, True, False)
    options = {i: [(c, (audit.after if incoming[i] else audit.before)[c])
                   for c in sorted(domains[i])] for i in order}
    universe = set(audit.after) | set(audit.before)
    suffix = [(universe, universe)] * 7
    for depth in range(5, -1, -1):
        i = order[depth]
        parts = list(suffix[depth + 1])
        parts[positions[i]] = parts[positions[i]].intersection(*(s for _, s in options[i]))
        suffix[depth] = tuple(parts)

    def unique(xs, ys):
        return sum(len(audit.after[x] & ys) for x in xs) == 1

    def visit(depth, used, xs, ys):
        if depth == 6:
            return unique(xs, ys)
        if not unique(xs & suffix[depth][0], ys & suffix[depth][1]):
            return False
        i = order[depth]
        for c, candidates in options[i]:
            if c not in used and visit(depth + 1, used | {c},
                                       xs & candidates if positions[i] == 0 else xs,
                                       ys & candidates if positions[i] == 1 else ys):
                return True
        return False
    return visit(0, set(answer), universe, universe)


def hardest(answer, domains, audit, counts):
    """Best-first monotone Cartesian search; first valid tuple has maximum score.

    The equivalent top1/left and bottom2/right swaps are represented as pairs.
    Equal scores use deterministic option and heap index order, never HSK level.
    """
    starts, ends = counts
    groups = [list(itertools.combinations(sorted(domains[0]), 2)),
              [(c,) for c in sorted(domains[1])],
              [(c,) for c in sorted(domains[2])],
              list(itertools.combinations(sorted(domains[3]), 2))]
    for group, counter in zip(groups, (starts, starts, ends, ends)):
        group.sort(key=lambda letters: (tuple(-v for v in sorted(counter[c] for c in letters)), letters))

    def materialize(indices):
        first, top2, bottom1, second = (g[i] for g, i in zip(groups, indices))
        return first[0], top2[0], bottom1[0], second[0], first[1], second[1]

    def item(indices):
        return tuple(-v for v in clue_score(materialize(indices), counts)), indices

    start = (0, 0, 0, 0)
    heap, seen = [item(start)], {start}
    while heap:
        negative_score, indices = heapq.heappop(heap)
        clues = materialize(indices)
        if len(set(clues)) == 6 and audit.solve(puzzle_from(clues)) == [answer]:
            return {"answer": answer, "clues": clues, "difficulty": tuple(-v for v in negative_score)}
        for dimension in range(4):
            updated = list(indices)
            updated[dimension] += 1
            updated = tuple(updated)
            if updated[dimension] < len(groups[dimension]) and updated not in seen:
                seen.add(updated)
                heapq.heappush(heap, item(updated))
    raise ValueError("Existence and hardest searches disagree")


def select(rows):
    """Maximize cardinality, then prefer each row in difficulty/canonical tie order."""
    rows = sorted(rows, key=lambda r: (tuple(-v for v in r["difficulty"]), r["clues"], r["answer"]))
    characters = sorted(set("".join(r["answer"] for r in rows)))
    indices = {c: i for i, c in enumerate(characters)}
    graph = [set() for _ in characters]
    for row in rows:
        a, b = map(indices.get, row["answer"])
        graph[a].add(b)
        graph[b].add(a)
    def size():
        return sum(v != -1 for v in maximum_matching([sorted(g) for g in graph])) // 2
    remaining = size()
    selected, used = [], set()
    for row in rows:
        a, b = map(indices.get, row["answer"])
        if a in used or b in used or b not in graph[a]:
            continue
        old_a, old_b = graph[a], graph[b]
        graph[a], graph[b] = set(), set()
        for v in old_a: graph[v].discard(a)
        for v in old_b: graph[v].discard(b)
        if size() == remaining - 1:
            selected.append(row)
            used.update((a, b))
            remaining -= 1
        else:
            graph[a], graph[b] = old_a - {b}, old_b - {a}
            for v in graph[a]: graph[v].add(a)
            for v in graph[b]: graph[v].add(b)
        if remaining == 0:
            break
    if remaining:
        raise ValueError("Failed to preserve maximum cardinality")
    return sorted(selected, key=lambda r: (r["difficulty"], r["clues"], r["answer"]))


def digest(public_id, salt, answer):
    return hashlib.sha256(f"{VERSION}:{public_id}:{salt}:{answer}".encode()).hexdigest()


def public_payload(rows, lexicon, previous=None):
    from scripts.audit_public import inspect_two_campaign
    if previous is not None and inspect_two_campaign(previous):
        raise ValueError("Invalid existing two-cell export")
    def key(clues):
        return tuple(clues["top"]) + tuple(clues["bottom"]) + (clues["left"], clues["right"])
    old = {key(p["clues"]): p for p in previous["puzzles"]} if previous else {}
    counts = word_counts(lexicon.broad_two)
    records = []
    for row in rows:
        c, answer = row["clues"], row["answer"]
        prior = old.get(tuple(c))
        reusable = prior and digest(prior["id"], prior["salt"], answer) == prior["check"]
        public_id, salt = (prior["id"], prior["salt"]) if reusable else (secrets.token_hex(16), secrets.token_hex(16))
        level = lambda w: lexicon.records[w]["level"]
        records.append({"id": public_id,
                        "clues": {"top": list(c[:2]), "bottom": list(c[2:4]), "left": c[4], "right": c[5]},
                        "levels": {"top": [level(c[0] + answer[0]), level(c[1] + answer[1])],
                                   "bottom": [level(answer[0] + c[2]), level(answer[1] + c[3])],
                                   "left": level(c[4] + answer[0]), "right": level(answer[1] + c[5]),
                                   "middle": level(answer)},
                        "difficulty": order_difficulty(answer, c, counts), "salt": salt, "check": digest(public_id, salt, answer)})
    revision = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    payload = {"version": VERSION, "revision": revision, "puzzles": records}
    if errors := inspect_two_campaign(payload):
        raise ValueError("Invalid two-cell export: " + "; ".join(errors))
    return payload


def run(private_dir, output, one_source=PRIVATE_ROOT / "datasets" / "one-standard-hsk-hardest.sqlite"):
    private_dir = private_output(private_dir)
    private_dir.mkdir(parents=True, exist_ok=True)
    cache = private_dir / "hardest.json"
    lexicon = Lexicon.load()
    audit, counts = IndexedAudit(lexicon), word_counts(lexicon.broad_two)
    common = lexicon.words_up_to("7-9")
    one_bytes = (ROOT / "public" / "campaign.json").read_bytes()
    one_campaign = json.loads(one_bytes)
    forbidden = one_clue_resources(one_source, one_campaign)
    scope = {"rule": SELECTION_RULE, "one_sha256": hashlib.sha256(one_bytes).hexdigest()}
    if cache.exists():
        bundle = json.loads(cache.read_text(encoding="utf-8"))
        if bundle["sources"] != lexicon.metadata["outputs"] or bundle["model"] != MODEL or bundle.get("scope") != scope:
            raise ValueError("Private cache has different sources or model")
        rows = bundle["rows"]
    else:
        incoming, outgoing = defaultdict(set), defaultdict(set)
        for word in common:
            if len(word) == 2:
                incoming[word[1]].add(word[0]); outgoing[word[0]].add(word[1])
        answers = sorted(w for w in common if len(w) == 2 and len(set(w)) == 2)
        rows = []
        for index, answer in enumerate(answers, 1):
            domains = [incoming[answer[0]], incoming[answer[1]], outgoing[answer[0]],
                       outgoing[answer[1]], incoming[answer[0]], outgoing[answer[1]]]
            domains = exclude_used_clues(answer, domains, forbidden)
            if all(domains) and count_distinct(domains) and has_unique(answer, domains, audit):
                rows.append(hardest(answer, domains, audit, counts))
            if index % 500 == 0:
                print(json.dumps({"processed": index, "hardest_found": len(rows)}), flush=True)
        cache.write_text(json.dumps({"sources": lexicon.metadata["outputs"], "model": MODEL, "scope": scope, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    selected = select(rows)
    used = set()
    used_resources = set(forbidden)
    for row in selected:
        answer, clues = row["answer"], row["clues"]
        puzzle = puzzle_from(clues)
        resources = clue_resources(answer, clues)
        if (used.intersection(answer) or len(set(answer)) != 2 or answer not in common
            or used_resources.intersection(resources) or len(resources) != 7
            or not puzzle.distinct(answer) or solve(puzzle, lexicon) != [answer]
            or any(w not in common for _, w in puzzle.edge_words(answer))
            or tuple(row["difficulty"]) != clue_score(clues, counts)):
            raise ValueError("Selected puzzle failed verification")
        used.update(answer)
        used_resources.update(resources)
    selected = arrange_selected(selected, counts)
    (private_dir / "selected.json").write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
    output = Path(output)
    previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
    payload = public_payload(selected, lexicon, previous)
    if previous and previous["revision"] != payload["revision"]:
        backup = private_dir / f"public-before-{previous['revision']}.json"
        if not backup.exists():
            backup.write_bytes(output.read_bytes())
    if previous and not (private_dir / "previous-public-campaign.json").exists():
        (private_dir / "previous-public-campaign.json").write_bytes(output.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    # General vocabulary, no ordering or IDs associating words with specific puzzles.
    vocabulary = {"version": "hsk-two-words-v1", "words": sorted(w for w in common if len(w) == 2)}
    (output.parent / "hsk-two-words.json").write_text(json.dumps(vocabulary, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    summary = {"model": MODEL, "order_model": ORDER_MODEL, "selection_rule": SELECTION_RULE, "one_revision": one_campaign["revision"],
               "one_clue_resources": len(forbidden), "external_clue_resources": 6 * len(selected),
               "feasible_answers": len(rows), "puzzles": len(selected),
               "distinct_answer_characters": len(used), "revision": payload["revision"],
               "sources": lexicon.metadata["outputs"], "full_solver_verified": len(selected)}
    (private_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, default=PRIVATE_ROOT / "datasets" / "two-standard-hsk-word-guess")
    parser.add_argument("--one-source", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-hardest.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "public" / "campaign-two.json")
    args = parser.parse_args()
    run(args.private_dir, args.output, args.one_source)
