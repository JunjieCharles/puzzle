"""Reject known answer-bearing artifacts in public Git content; allow vocabulary and aggregates."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "word-kanji"))
SENSITIVE_KEYS = {"answer", "answers", "edge_words", "broad_unique_answer", "source_puzzle_id", "top_candidate_contributors"}


def inspect_campaign(value):
    """Strict whitelist for browser-accessible campaign data, including nesting."""
    errors = []
    if not isinstance(value, dict) or set(value) != {"version", "revision", "puzzles"}:
        return ["invalid campaign envelope"]
    if value["version"] != "kanji-one-v1" or not re.fullmatch(r"[0-9a-f]{16}", str(value["revision"])):
        errors.append("invalid campaign version/revision")
    if not isinstance(value["puzzles"], list) or not value["puzzles"]:
        return errors + ["empty or invalid campaign"]
    ids = set()
    for record in value["puzzles"]:
        if not isinstance(record, dict) or set(record) != {"id", "clues", "levels", "difficulty", "salt", "check"}:
            errors.append("unexpected campaign record fields")
            continue
        for key, length in (("id", 32), ("salt", 32), ("check", 64)):
            if not isinstance(record[key], str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", record[key]):
                errors.append(f"invalid campaign {key}")
        if str(record["id"]) in ids:
            errors.append("duplicate public ID")
        ids.add(str(record["id"]))
        for key in ("clues", "levels"):
            if not isinstance(record[key], dict) or set(record[key]) != {"top", "left", "bottom", "right"}:
                errors.append(f"invalid campaign {key}")
                continue
            for item in record[key].values():
                valid = (isinstance(item, str) and len(item) == 1 and
                         ("\u3400" <= item <= "\u9fff" or "\U00020000" <= item <= "\U000323af")) if key == "clues" else item in ("1", "2", "3", "4", "5", "6", "7-9")
                if not valid:
                    errors.append(f"invalid campaign {key} value")
        score = record["difficulty"]
        # Historical public exports used a scalar; new exports use sorted counts.
        valid_score = (type(score) is int and 4 <= score <= 4 * 0x110000) or (
            isinstance(score, list) and len(score) == 4
            and all(type(item) is int and 1 <= item <= 0x110000 for item in score)
            and score == sorted(score))
        if not valid_score:
            errors.append("invalid campaign difficulty")
    return errors


def inspect_json(value, location="$"):
    errors = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SENSITIVE_KEYS:
                errors.append(f"answer-bearing JSON field {location}.{key}")
            errors.extend(inspect_json(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(inspect_json(child, f"{location}[{index}]"))
    return errors


def inspect_two_campaign(value):
    from generator import is_hanzi_word, LEVELS
    if not isinstance(value, dict) or set(value) != {"version", "revision", "puzzles"}:
        return ["invalid two-cell envelope"]
    if value["version"] != "kanji-two-v1" or not re.fullmatch(r"[0-9a-f]{16}", str(value["revision"])):
        return ["invalid two-cell version/revision"]
    if not isinstance(value["puzzles"], list) or not value["puzzles"]:
        return ["empty two-cell campaign"]
    errors, ids = [], set()
    for record in value["puzzles"]:
        if not isinstance(record, dict) or set(record) != {"id", "clues", "levels", "difficulty", "salt", "check"}:
            errors.append("unexpected two-cell fields")
            continue
        for key, length in (("id", 32), ("salt", 32), ("check", 64)):
            if not isinstance(record[key], str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", record[key]):
                errors.append(f"invalid two-cell {key}")
        if str(record["id"]) in ids:
            errors.append("duplicate two-cell ID")
        ids.add(str(record["id"]))
        for key in ("clues", "levels"):
            fields = {"top", "bottom", "left", "right"} | ({"middle"} if key == "levels" else set())
            data = record[key]
            if not isinstance(data, dict) or set(data) != fields:
                errors.append(f"invalid two-cell {key}")
                continue
            values = []
            for side in fields:
                item = data[side]
                if side in ("top", "bottom"):
                    if not isinstance(item, list) or len(item) != 2:
                        errors.append(f"invalid two-cell {key} pair")
                        continue
                    values.extend(item)
                else:
                    values.append(item)
            if any(not isinstance(v, str) or not (len(v) == 1 and is_hanzi_word(v) if key == "clues" else v in LEVELS) for v in values):
                errors.append(f"invalid two-cell {key} value")
            if key == "clues" and len({str(v) for v in values}) != 6:
                errors.append("repeated two-cell clues")
        score = record["difficulty"]
        # Legacy exports used the six-count selection score; new exports expose
        # only the minimax scalar, never the answer-specific intermediate counts.
        if not ((type(score) is int and 1 <= score <= 0x110000) or
                (isinstance(score, list) and len(score) == 6 and all(type(v) is int and 1 <= v <= 0x110000 for v in score) and score == sorted(score))):
            errors.append("invalid two-cell difficulty")
    return errors


def inspect_file(name, payload):
    path = Path(name)
    if (path.suffix in {".sqlite", ".db", ".bundle", ".pyc"}
            or "examples" in path.parts or "private" in path.parts or "raw" in path.parts):
        return [f"private artifact path: {name}"]
    if path.suffix == ".json":
        value = json.loads(payload.decode("utf-8-sig"))
        errors = inspect_json(value)
        if path.name == "campaign.json":
            errors.extend(inspect_campaign(value))
        elif path.name == "campaign-two.json":
            errors.extend(inspect_two_campaign(value))
        elif path.name == "hsk-two-words.json":
            # Exact full HSK vocabulary, never a puzzle-specific candidate list.
            from generator import Lexicon
            expected = {"version": "hsk-two-words-v1", "words": sorted(w for w in Lexicon.load().records if len(w) == 2)}
            if value != expected:
                errors.append("two-word vocabulary must equal the complete generic HSK list")
        return errors
    return []


def git(*args):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Audit exact index blobs rather than working files")
    parser.add_argument("--history", action="store_true", help="Also audit every blob reachable from any Git ref")
    args = parser.parse_args()
    problems = []
    checked = 0
    if args.history:
        seen = set()
        for commit in git("rev-list", "--all").decode().splitlines():
            for row in git("ls-tree", "-rz", commit).split(b"\0"):
                if not row:
                    continue
                attributes, name = row.split(b"\t", 1)
                _, kind, digest = attributes.split()
                if kind != b"blob" or (name, digest) in seen:
                    continue
                seen.add((name, digest))
                problems.extend(f"{commit[:8]}:{name.decode()}: {error}" for error in
                                inspect_file(name.decode(), git("cat-file", "blob", digest.decode())))
                checked += 1
    else:
        command = ("ls-files", "-z", "--cached") if args.staged else ("ls-files", "-z", "--cached", "--others", "--exclude-standard")
        for name in sorted(set(n.decode() for n in git(*command).split(b"\0") if n)):
            path = ROOT / name
            if not args.staged and not path.is_file():
                continue
            payload = git("show", f":{name}") if args.staged else path.read_bytes()
            problems.extend(f"{name}: {error}" for error in inspect_file(name, payload))
            checked += 1
    if problems:
        print("\n".join(problems[:30]))
        raise SystemExit(f"Public-content audit failed: {len(problems)} findings")
    print(f"Public-content audit passed ({checked} files/blobs).")


if __name__ == "__main__":
    main()
