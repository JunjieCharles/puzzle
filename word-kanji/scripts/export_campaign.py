"""Publish clue-only campaign data from the private selected SQLite dataset."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage import PRIVATE_ROOT, private_output
from difficulty import MODEL, load_counts, clue_score

PUBLIC = ROOT / "public"
VERSION = "kanji-one-v1"


def difficulty(row):
    return row["difficulty"]


def arrange(rows, gap=31):
    """Greedy easy-first order with a hard distance and remaining-slot feasibility.

    Each group's easiest remaining puzzle is considered first. Reserve enough
    remaining slots for every group, so difficulty yields to spacing when needed.
    Raise instead of silently publishing an order that violates the requested gap.
    """
    if gap < 1:
        raise ValueError("gap must be positive")
    groups = defaultdict(list)
    for row in rows:
        groups[row["answer"]].append(row)
    for group in groups.values():
        group.sort(key=lambda r: (difficulty(r), r["id"]), reverse=True)
    size = len(rows)
    last = {key: -gap for key in groups}
    result = []
    for index in range(size):
        eligible = [key for key, group in groups.items() if group and index - last[key] >= gap]
        eligible.sort(key=lambda key: (difficulty(groups[key][-1]), groups[key][-1]["id"]))
        chosen = None
        for key in eligible:
            feasible = all(
                not (count := len(group) - (other == key))
                or max(index + 1, (index if other == key else last[other]) + gap)
                + (count - 1) * gap < size
                for other, group in groups.items()
            )
            # Account for groups competing for the same final slots, not just
            # each group's individual deadline. All remaining occurrences need
            # distinct slots no later than their latest possible positions.
            deadlines = sorted(size - 1 - repeat * gap
                               for other, group in groups.items()
                               for repeat in range(len(group) - (other == key))) if feasible else []
            if feasible and all(index + 1 + offset <= deadline for offset, deadline in enumerate(deadlines)):
                chosen = key
                break
        if chosen is None:
            raise ValueError("Cannot arrange this dataset with the requested spacing")
        result.append(groups[chosen].pop())
        last[chosen] = index
    return result


def digest_value(public_id, salt, value):
    normalized = unicodedata.normalize("NFC", value.strip())
    return hashlib.sha256(f"{VERSION}:{public_id}:{salt}:{normalized}".encode("utf-8")).hexdigest()


def public_record(row):
    public_id, salt = secrets.token_hex(16), secrets.token_hex(16)
    return {
        "id": public_id,
        "clues": {side: row[side] for side in ("top", "left", "bottom", "right")},
        "levels": {side: row[f"{side}_level"] for side in ("top", "left", "bottom", "right")},
        "difficulty": list(difficulty(row)),
        "salt": salt,
        "check": digest_value(public_id, salt, row["answer"]),
    }


def export(source, output, gap=31):
    source = private_output(source)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("SELECT * FROM puzzle_details ORDER BY id")]
    if not rows:
        raise ValueError("Dataset is empty")
    counts = load_counts()
    for row in rows:
        row["difficulty"] = clue_score(row, counts)
    ordered = arrange(rows, gap)
    records = [public_record(row) for row in ordered]
    # Identifies this exact order without exposing source IDs or solution groups.
    revision = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    payload = {"version": VERSION, "revision": revision, "puzzles": records}
    from scripts.audit_public import inspect_campaign
    if errors := inspect_campaign(payload):
        raise ValueError("Invalid public export: " + "; ".join(errors))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    last, distances = {}, []
    for index, row in enumerate(ordered):
        if row["answer"] in last:
            distances.append(index - last[row["answer"]])
        last[row["answer"]] = index
    quarter_means = []
    for start in range(0, len(ordered), 200):
        part = ordered[start:start + 200]
        quarter_means.append([round(sum(difficulty(row)[i] for row in part) / len(part), 3) for i in range(4)])
    return {"puzzles": len(records), "minimum_distance": min(distances, default=None),
            "difficulty_model": MODEL, "difficulty_range": [min(r["difficulty"] for r in rows), max(r["difficulty"] for r in rows)],
            "mean_difficulty_per_200_levels": quarter_means}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PRIVATE_ROOT / "datasets" / "one-standard-hsk-branching-lexicographic.sqlite")
    parser.add_argument("--output", type=Path, default=PUBLIC / "campaign.json")
    parser.add_argument("--gap", type=int, default=31, help="Level-number distance; 31 leaves 30 intervening levels")
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.output, args.gap), ensure_ascii=False))


if __name__ == "__main__":
    main()
