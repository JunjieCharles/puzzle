"""Reject known answer-bearing artifacts in public Git content; allow vocabulary and aggregates."""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "word-kanji"))
SENSITIVE_KEYS = {"answer", "answers", "solution", "solutions", "recent_answers", "cooling_state", "edge_words", "broad_unique_answer", "source_puzzle_id", "top_candidate_contributors"}


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
        if {"character", "rooms"} <= value.keys():
            errors.append(f"glyph-to-floorplan mapping at {location}")
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
    if path.suffix == '.gz':
        import gzip
        import io
        if name.replace('\\', '/') != 'hanzi-paint-bucket/public/levels.json.gz':
            return ['unreviewed compressed artifact']
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                decoded = stream.read(16 * 1024 * 1024 + 1)
            if len(decoded) > 16 * 1024 * 1024:
                return ['oversized compressed bank']
            return inspect_file(name[:-3], decoded)
        except (OSError, EOFError, ValueError):
            return ['invalid compressed bank']
    if path.name in {"contact-sheet.png", "private-report.json"}:
        return [f"private experiment artifact: {name}"]
    if (path.suffix in {".sqlite", ".db", ".bundle", ".pyc"}
            or "examples" in path.parts or "private" in path.parts or "raw" in path.parts):
        return [f"private artifact path: {name}"]
    if path.suffix == ".json":
        value = json.loads(payload.decode("utf-8-sig"))
        errors = inspect_json(value)
        if name.replace('\\', '/') == 'hanzi-paint-bucket/public/levels.json':
            errors.extend(inspect_paint_campaign(value))
        if path.name == "campaign.json":
            errors.extend(inspect_campaign(value))
        elif path.name == "campaign-two.json":
            errors.extend(inspect_two_campaign(value))
        elif path.name == "hsk-two-words.json":
            # Exact full HSK vocabulary, never a puzzle-specific candidate list.
            from generator import Lexicon
            expected = {"version": "hsk-two-words-v1", "words": sorted(w for w in Lexicon.load().records if len(w) == 2)}
            from scripts.vocabulary_policy import filter_words
            filtered = dict(expected, words=filter_words(expected["words"]))
            if value not in (expected, filtered):
                errors.append("two-word vocabulary must equal the complete generic HSK list")
        elif path.name == "endless-lexicon.json":
            from scripts.export_endless_lexicon import payload as endless_vocabulary
            from scripts.vocabulary_policy import filter_endless
            expected = endless_vocabulary()
            if value not in (expected, filter_endless(expected)):
                errors.append("endless vocabulary must equal complete generic HSK and expanded lists")
        return errors
    return []


def inspect_paint_campaign(value):
    """Paint-only encryption exception; no plaintext or glyph mapping fields."""
    import base64
    import struct
    if not isinstance(value, dict):
        return ['invalid paint envelope']
    encrypted = value.get('version') in {'paint-v2', 'paint-v3', 'paint-v4'}
    legacy_check = value.get('version') in {'paint-v1', 'paint-v2'}
    fields = {'version', 'revision', 'puzzles'} | ({'encryption'} if encrypted else set())
    if set(value) != fields:
        return ['invalid paint envelope']
    if value['version'] not in {'paint-v1', 'paint-v2', 'paint-v3', 'paint-v4'} or not re.fullmatch(r'[a-f0-9]{16}', str(value['revision'])):
        return ['invalid paint version']
    if encrypted:
        try:
            config = value['encryption']
            if set(config) != {'algorithm', 'key'} or config['algorithm'] != 'AES-GCM' or len(base64.b64decode(config['key'], validate=True)) != 32:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            return ['invalid paint encryption configuration']
    if not isinstance(value['puzzles'], list) or not value['puzzles']:
        return ['empty paint bank']
    errors, ids = [], set()
    for record in value['puzzles']:
        fields = {'id', 'images'} | ({'salt', 'check'} if legacy_check else set()) | ({'sealed'} if encrypted else set())
        if not isinstance(record, dict) or set(record) != fields:
            errors.append('unexpected paint fields'); continue
        if encrypted:
            try:
                sealed = record['sealed']
                maximum = 200000 if value['version'] == 'paint-v4' else 32
                if set(sealed) != {'iv', 'ciphertext'} or len(base64.b64decode(sealed['iv'], validate=True)) != 12 or not 22 <= len(base64.b64decode(sealed['ciphertext'], validate=True)) <= maximum:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                errors.append('invalid paint ciphertext')
        for key, length in [('id',32)] + ([('salt',32), ('check',64)] if legacy_check else []):
            if not re.fullmatch(rf'[a-f0-9]{{{length}}}', str(record[key])):
                errors.append('invalid paint identifier or check')
        if record['id'] in ids: errors.append('duplicate paint ID')
        ids.add(record['id'])
        if not isinstance(record['images'], list) or not 2 <= len(record['images']) <= 4:
            errors.append('invalid paint clues'); continue
        for image in record['images']:
            try:
                if not image.startswith('data:image/png;base64,'): raise ValueError()
                raw = base64.b64decode(image.split(',',1)[1], validate=True)
                if raw[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError()
                offset, chunks = 8, []
                while offset < len(raw):
                    size = struct.unpack('>I',raw[offset:offset+4])[0]
                    kind = raw[offset+4:offset+8]
                    if kind not in {b'IHDR',b'IDAT',b'IEND'} or offset+size+12>len(raw): raise ValueError()
                    if kind == b'IHDR' and struct.unpack('>II',raw[offset+8:offset+16]) != (480,480): raise ValueError()
                    chunks.append(kind); offset += size+12
                if chunks[0]!=b'IHDR' or chunks[-1]!=b'IEND' or b'IDAT' not in chunks: raise ValueError()
            except (ValueError, TypeError, AttributeError, IndexError, struct.error):
                errors.append('invalid paint PNG or unexpected metadata')
    return errors


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
