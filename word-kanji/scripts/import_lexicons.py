"""Build offline word lists from pinned, attributed upstream snapshots (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import is_hanzi_word  # noqa: E402
from storage import PRIVATE_ROOT

HSK_COMMIT = "182692ce5a11bc30bdc771835d2f0f27491c25de"
CEDICT_COMMIT = "2adf7c9885a17077966922b89de7ce655d7d82a0"
HSK_BASE = f"https://raw.githubusercontent.com/krmanik/HSK-3.0/{HSK_COMMIT}/"
CEDICT_URL = (
    "https://raw.githubusercontent.com/Punpuf/hsk-syllabus-vocabulary-parser/"
    f"{CEDICT_COMMIT}/cedict_ts.u8"
)
LEVELS = ("1", "2", "3", "4", "5", "6", "7-9")


def download(url: str, name: str) -> tuple[str, dict]:
    path = PRIVATE_ROOT / "data" / "raw" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "word-kanji-importer/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        path.write_bytes(payload)
    payload = path.read_bytes()
    return payload.decode("utf-8-sig"), {
        "url": url, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)
    }


def normalize_headword(raw: str) -> list[str]:
    """Remove sense numbers; expand explicitly optional parenthesized Hanzi only."""
    word = re.sub(r"[0-9¹²³⁴⁵⁶⁷⁸⁹]+$", "", raw.strip())
    match = re.search(r"[（(]([\u3400-\u9fff]+)[）)]", word)
    if match:
        without = word[:match.start()] + word[match.end():]
        with_optional = word[:match.start()] + match[1] + word[match.end():]
        return sorted(set(normalize_headword(without) + normalize_headword(with_optional)))
    return [word] if is_hanzi_word(word) else []


def read_hsk(level: str) -> tuple[str, str, dict]:
    path = f"New HSK (2025)/HSK Words/temp/HSK_Level_{level}_words.txt"
    content, source = download(HSK_BASE + urllib.parse.quote(path), f"hsk-{level}.tsv")
    return level, content, source


def main() -> None:
    data_dir = ROOT / "data"
    license_dir = data_dir / "licenses"
    license_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    sources = {}
    skipped = []
    indices = set()
    raw_rows = 0
    with ThreadPoolExecutor(max_workers=7) as pool:
        downloads = list(pool.map(read_hsk, LEVELS))
    for level, content, source in downloads:
        sources[level] = source
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            columns = line.split("\t")
            if len(columns) < 4 or not columns[0].isdigit():
                raise ValueError(f"Unexpected HSK row {level}:{number}: {line!r}")
            index, raw_levels, raw_word, pinyin = columns[:4]
            pos = columns[4] if len(columns) > 4 else ""
            indices.add(int(index))
            raw_rows += 1
            grades = sorted(set(re.findall(r"7-9|[1-6]", raw_levels)), key=LEVELS.index)
            if not grades or level not in grades:
                raise ValueError(f"Unexpected level field: {line!r}")
            words = normalize_headword(raw_word)
            if not words:
                skipped.append({"index": int(index), "raw_word": raw_word})
            for word in words:
                record = entries.setdefault(word, {"word": word, "levels": [], "entries": []})
                record["levels"] = sorted(set(record["levels"] + grades), key=LEVELS.index)
                evidence = {"index": int(index), "headword": raw_word, "levels": grades,
                            "pinyin": pinyin, "part_of_speech": pos}
                if evidence not in record["entries"]:
                    record["entries"].append(evidence)
    if indices != set(range(1, 11001)):
        raise ValueError(f"HSK source index coverage mismatch: {len(indices)} indices")
    records = []
    for word in sorted(entries):
        record = entries[word]
        record["level"] = record["levels"][0]
        records.append(record)
    hsk_file = data_dir / "hsk-2025.json"
    hsk_file.write_text(json.dumps({"standard": "HSK 3.0 (2025-11 / 2026-07)",
                                    "words": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"HSK: {raw_rows} source rows, {len(indices)} numbered entries, {len(records)} headwords", flush=True)

    cedict, cedict_source = download(CEDICT_URL, "cedict_ts.u8")
    broad = set()
    for line in cedict.splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split(" ", 2)
        if len(columns) != 3:
            raise ValueError(f"Invalid CC-CEDICT entry: {line!r}")
        simplified = columns[1]
        if len(simplified) in (1, 2) and is_hanzi_word(simplified):
            broad.add(simplified)
    cedict_file = data_dir / "cedict-1-2.txt"
    cedict_file.write_text("\n".join(sorted(broad)) + "\n", encoding="utf-8", newline="\n")
    upstream_license, license_source = download(HSK_BASE + "License.md", "HSK-License.md")
    (license_dir / "HSK-upstream.md").write_text(upstream_license.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    header = "\n".join(line.rstrip() for line in cedict.splitlines() if line.startswith("#"))
    (license_dir / "CC-CEDICT.txt").write_text(header + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "standard": "HSK 3.0 (2025-11 / 2026-07)",
        "official_syllabus": "https://www.chinesetest.cn/syllabus",
        "hsk_repository": "https://github.com/krmanik/HSK-3.0",
        "hsk_commit": HSK_COMMIT, "hsk_sources": sources,
        "hsk_license_source": license_source,
        "hsk_source_rows": raw_rows, "hsk_numbered_entries": len(indices),
        "hsk_headwords": len(records), "hsk_earliest_level_counts": dict(Counter(r["level"] for r in records)),
        "skipped_non_hanzi_entries": skipped,
        "cedict_source": cedict_source, "cedict_mirror_commit": CEDICT_COMMIT,
        "cedict_snapshot_date": re.search(r"^#! date=(.+)$", cedict, re.MULTILINE)[1],
        "cedict_one_two_character_headwords": len(broad),
        "license": "CC-BY-SA-4.0",
        "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (hsk_file, cedict_file)},
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"CC-CEDICT: {len(broad)} one/two-character headwords; {len(skipped)} excluded non-Hanzi HSK rows")


if __name__ == "__main__":
    main()
