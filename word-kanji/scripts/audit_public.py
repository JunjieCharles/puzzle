"""Reject known answer-bearing artifacts in public Git content; allow vocabulary and aggregates."""
import argparse
import json
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
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
        if type(record["difficulty"]) is not int or not 4 <= record["difficulty"] <= 28:
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
