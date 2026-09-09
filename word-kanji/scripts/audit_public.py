"""Reject known answer-bearing artifacts in public Git content; allow vocabulary and aggregates."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SENSITIVE_KEYS = {"answer", "answers", "edge_words", "broad_unique_answer", "source_puzzle_id", "top_candidate_contributors"}


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
        return inspect_json(json.loads(payload.decode("utf-8-sig")))
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
