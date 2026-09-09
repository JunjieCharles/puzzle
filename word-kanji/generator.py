"""Offline Chinese Wadou Kaichin generator. Python 3.10+, standard library only."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import secrets
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from storage import PRIVATE_ROOT, private_output

ROOT = Path(__file__).resolve().parent
LEVELS = ("1", "2", "3", "4", "5", "6", "7-9")


def is_hanzi_word(word: str) -> bool:
    return bool(word) and all(
        0x3400 <= ord(c) <= 0x4DBF or 0x4E00 <= ord(c) <= 0x9FFF
        or 0x20000 <= ord(c) <= 0x323AF for c in word
    )


def level_rank(level: str) -> int:
    return LEVELS.index(level) + 1


@dataclass(frozen=True)
class Puzzle:
    """Horizontal answer chain; each answer cell has an upper and lower clue."""

    top: tuple[str, ...]
    bottom: tuple[str, ...]
    left: str
    right: str

    def __post_init__(self) -> None:
        if len(self.top) not in (1, 2) or len(self.top) != len(self.bottom):
            raise ValueError("Only one/two-character standard layouts are supported")
        if any(len(c) != 1 or not is_hanzi_word(c) for c in self.fixed_letters):
            raise ValueError("Each fixed cell must contain one Hanzi")

    @property
    def size(self) -> int:
        return len(self.top)

    @property
    def fixed_letters(self) -> tuple[str, ...]:
        return self.top + self.bottom + (self.left, self.right)

    def edge_words(self, answer: str) -> list[tuple[str, str]]:
        if len(answer) != self.size:
            raise ValueError("Answer length does not match the puzzle")
        words = [("左 → ①", self.left + answer[0])]
        for i, char in enumerate(answer):
            label = "①②"[i]
            words.extend([(f"上 → {label}", self.top[i] + char),
                          (f"{label} → 下", char + self.bottom[i])])
            if i + 1 < self.size:
                words.append((f"{label} → {'①②'[i + 1]}", char + answer[i + 1]))
        words.append((f"{'①②'[self.size - 1]} → 右", answer[-1] + self.right))
        return words

    def distinct(self, answer: str) -> bool:
        letters = self.fixed_letters + tuple(answer)
        return len(set(letters)) == len(letters)

    def grid(self) -> list[list[str]]:
        width = 2 * self.size + 3
        grid = [["" for _ in range(width)] for _ in range(5)]
        grid[2][0], grid[2][-1] = self.left, self.right
        for i in range(self.size):
            col = 2 + 2 * i
            grid[0][col], grid[4][col] = self.top[i], self.bottom[i]
            grid[1][col] = grid[3][col] = "↓"
            grid[2][col] = "①②"[i]
        for col in range(1, width, 2):
            grid[2][col] = "→"
        return grid


class Lexicon:
    def __init__(self, records: list[dict], broad_words: set[str], metadata: dict | None = None):
        self.records = {r["word"]: r for r in records}
        if any(not is_hanzi_word(w) or r["level"] not in LEVELS for w, r in self.records.items()):
            raise ValueError("Invalid HSK word or level")
        self.metadata = metadata or {}
        # Broad audit includes every HSK level, regardless of generation ceiling.
        broad = set(self.records) | broad_words
        self.broad_two = {w for w in broad if len(w) == 2 and is_hanzi_word(w)}
        self.broad_answers = {
            n: tuple(sorted(w for w in broad if len(w) == n and is_hanzi_word(w))) for n in (1, 2)
        }

    @classmethod
    def load(cls, data_dir: Path = ROOT / "data") -> Lexicon:
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["outputs"].items():
            if hashlib.sha256((data_dir / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Word-list checksum mismatch: {name}")
        payload = json.loads((data_dir / "hsk-2025.json").read_text(encoding="utf-8"))
        broad_words = set((data_dir / "cedict-1-2.txt").read_text(encoding="utf-8").splitlines())
        return cls(payload["words"], broad_words, manifest)

    def words_up_to(self, maximum: str) -> set[str]:
        return {w for w, r in self.records.items() if level_rank(r["level"]) <= level_rank(maximum)}

    def annotate(self, word: str) -> dict:
        record = self.records[word]
        return {"word": word, "hsk_level": record["level"],
                "listed_levels": record.get("levels", [record["level"]]),
                "source_entries": record.get("entries", [])}


def solve(puzzle: Puzzle, lexicon: Lexicon) -> list[str]:
    """Exhaustive broad-word audit. Deliberately does NOT filter repeated letters."""
    # Cheap vertical/outer constraints narrow candidates before full verification.
    return [answer for answer in lexicon.broad_answers[puzzle.size]
            if all(word in lexicon.broad_two for _, word in puzzle.edge_words(answer))]


def generate(lexicon: Lexicon, size: int, count: int, maximum: str,
             rng: random.Random, attempts_per_answer: int = 100) -> list[tuple[Puzzle, str]]:
    if size not in (1, 2) or count < 0 or attempts_per_answer < 1:
        raise ValueError("Invalid puzzle size, count, or attempt budget")
    if count == 0:
        return []
    common = lexicon.words_up_to(maximum)
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for word in sorted(common):
        if len(word) == 2:
            incoming[word[1]].append(word[0])
            outgoing[word[0]].append(word[1])
    answers = sorted(w for w in common if len(w) == size and len(set(w)) == size)
    rng.shuffle(answers)
    result = []
    for answer in answers:
        # The two-character answer is itself the middle horizontal edge.
        domains = ([incoming[c] for c in answer] + [outgoing[c] for c in answer]
                   + [incoming[answer[0]], outgoing[answer[-1]]])
        domains = [tuple(c for c in domain if c not in answer) for domain in domains]
        if any(not domain for domain in domains):
            continue
        for _ in range(attempts_per_answer):
            # Randomized all-different clue assignment; most constrained first.
            order = sorted(range(len(domains)), key=lambda i: len(domains[i]))
            chosen = [""] * len(domains)
            used = set(answer)
            for index in order:
                options = [c for c in domains[index] if c not in used]
                if not options:
                    break
                chosen[index] = rng.choice(options)
                used.add(chosen[index])
            if not all(chosen):
                continue
            puzzle = Puzzle(tuple(chosen[:size]), tuple(chosen[size:2 * size]), chosen[-2], chosen[-1])
            if solve(puzzle, lexicon) == [answer]:
                result.append((puzzle, answer))
                break  # Different answers within each batch.
        if len(result) == count:
            return result
    raise ValueError(f"Only found {len(result)}/{count} {size}-character puzzles at HSK ≤ {maximum}. "
                     "Try a higher level, fewer puzzles, another seed, or more attempts.")


def make_record(puzzle: Puzzle, answer: str, lexicon: Lexicon, number: int) -> dict:
    edges = [{"relation": relation, **lexicon.annotate(word)} for relation, word in puzzle.edge_words(answer)]
    answer_record = lexicon.annotate(answer)
    maximum = max([e["hsk_level"] for e in edges] + [answer_record["hsk_level"]], key=level_rank)
    return {"id": f"{'一二'[puzzle.size - 1]}-{number:02d}",
            "type": f"{'一二'[puzzle.size - 1]}字标准型", "size": puzzle.size,
            "layout": {"top": puzzle.top, "bottom": puzzle.bottom, "left": puzzle.left, "right": puzzle.right},
            "grid": puzzle.grid(), "answer": answer_record, "edge_words": edges,
            "max_used_hsk_level": maximum,
            "quality": {"all_distinct": puzzle.distinct(answer), "broad_solution_count": 1,
                        "broad_unique_answer": answer,
                        "scope": "完整 HSK 2025 词库 ∪ CC-CEDICT 简体一/二字词快照；不按互异性过滤备选解"}}


def markdown_output(bundle: dict) -> str:
    parts = ["# 随机和同開珎题目", "", f"种子：`{bundle['seed']}`；本批词汇上限：HSK {bundle['max_level']}。",
             "", "只按 ↓、→ 组中文二字词，答案按编号顺序组成词语。答案与等级在下方折叠区。",
             "", "等级为字面词条在 HSK 2025 大纲中的最早收录等级；7–9 为一个等级组，不代表逐义项难度。",
             "", "唯一性已在完整 HSK 与 CC-CEDICT 快照的并集中检查，不代表所有中文词汇下绝对唯一。", ""]
    for p in bundle["puzzles"]:
        parts.extend([f"## {p['id']} · {p['type']}", "", "```text"])
        parts.extend(" ".join(cell or "　" for cell in row).rstrip() for row in p["grid"])
        parts.extend(["```", "", "<details>", "<summary>答案、词语等级与校验</summary>", "",
                      f"答案：**{p['answer']['word']}**（HSK {p['answer']['hsk_level']}）", "",
                      "| 关系 | 词语 | HSK 等级 |", "| --- | --- | --- |"])
        parts.extend(f"| {e['relation']} | {e['word']} | {e['hsk_level']} |" for e in p["edge_words"])
        parts.extend(["", "全部字格互异；扩展词库内唯一解。", "", "</details>", ""])
    parts.extend(["词库署名：[krmanik/HSK-3.0](https://github.com/krmanik/HSK-3.0)、"
                  "[CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict)。"
                  "数据及派生题集：[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。", ""])
    return "\n".join(parts)


def html_output(bundle: dict) -> str:
    esc = html.escape
    cards = []
    for p in bundle["puzzles"]:
        cells = []
        for row in p["grid"]:
            for cell in row:
                kind = "blank" if cell in ("①", "②") else "arrow" if cell in ("→", "↓") else "clue"
                cells.append(f'<span class="{kind}">{esc(cell)}</span>')
        rows = "".join(f"<tr><td>{esc(e['relation'])}</td><td>{esc(e['word'])}</td>"
                       f"<td><span class='badge'>HSK {e['hsk_level']}</span></td></tr>" for e in p["edge_words"])
        cards.append(f'''<article><header><span>{p['id']}</span><h2>{p['type']}</h2>
<span class="badge">最高 HSK {p['max_used_hsk_level']}</span></header>
<div class="board" style="--cols:{2 * p['size'] + 3}">{''.join(cells)}</div>
<details><summary>查看答案与词语等级</summary>
<p class="answer">{esc(p['answer']['word'])} <span class="badge">HSK {p['answer']['hsk_level']}</span></p>
<table><thead><tr><th>关系</th><th>词语</th><th>等级</th></tr></thead><tbody>{rows}</tbody></table>
<p class="check">全题汉字互异 · 扩展词库内唯一解</p></details></article>''')
    return f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>和同開珎 · 随机题目</title><style>
:root{{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#203c36;background:#f5f3eb}}
*{{box-sizing:border-box}}body{{max-width:1140px;margin:auto;padding:40px 24px}}h1{{font-size:36px;margin:8px 0 16px}}
.intro{{max-width:780px;line-height:1.8;color:#53665e}}.eyebrow{{letter-spacing:3px;font-size:13px;color:#617a67}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:24px;margin-top:30px}}
article{{background:#fffefa;border:1px solid #d9dfd4;border-radius:16px;padding:24px;align-self:start}}
header{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}header>span:first-child{{color:#748378;font-size:13px}}
h2{{font-size:18px;margin:0;flex:1}}.badge{{font-size:12px;padding:4px 8px;border-radius:6px;background:#e8efe5;color:#3c6248;white-space:nowrap}}
.board{{display:grid;grid-template-columns:repeat(var(--cols),1fr);grid-template-rows:repeat(5,42px);max-width:350px;margin:30px auto}}
.board span{{display:flex;align-items:center;justify-content:center;font-size:29px}}.board .arrow{{font-size:23px;color:#78897e}}
.board .blank{{border:2px solid #547d65;border-radius:5px;color:#547d65;background:#f0f5ec;font-size:24px}}
summary{{cursor:pointer;color:#42644f;padding:12px 0;border-top:1px solid #e3e7dd}}summary:focus-visible{{outline:2px solid #547d65}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;padding:9px 4px;border-bottom:1px solid #eef0e9}}
th{{color:#79857a;font-weight:500}}.answer{{font-size:26px;letter-spacing:3px}}.answer .badge{{letter-spacing:0;vertical-align:middle}}
.check,footer{{font-size:12px;color:#748378;line-height:1.8}}footer{{margin-top:32px}}a{{color:#42644f}}
@media(max-width:450px){{body{{padding:24px 12px}}.cards{{grid-template-columns:1fr}}article{{padding:18px}}}}
@media print{{body{{background:white}}article{{break-inside:avoid}}details{{display:none}}}}
</style><body><div class="eyebrow">中文填词 / HSK 2025</div><h1>和同開珎</h1>
<p class="intro">每格填一个汉字，让每条 ↓、→ 都组成中文二字词；按编号读取答案，还要组成一个词语。
本批使用 HSK 1–{esc(bundle['max_level'])} 词汇，共 {len(bundle['puzzles'])} 题。随机种子：{bundle['seed']}。</p>
<div class="cards">{''.join(cards)}</div>
<footer>等级按字面词条最早收录级别标注，不代表每个读音或义项均在该级教授。HSK 7–9 也是可选的常见词范围。
唯一性审查覆盖完整 HSK 与 CC-CEDICT 固定快照，不代表所有中文词汇下绝对唯一。
<br>词库：<a href="https://github.com/krmanik/HSK-3.0">krmanik/HSK-3.0</a> ·
<a href="https://www.mdbg.net/chinese/dictionary?page=cc-cedict">CC-CEDICT</a> ·
数据及其派生题集：<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>。
详细版本及来源见同目录 JSON 和项目 data/manifest.json。</footer></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="生成一字、二字标准型中文和同開珎题目（离线）")
    parser.add_argument("--one", type=int, default=5, help="一字标准型题数，默认 5")
    parser.add_argument("--two", type=int, default=5, help="二字标准型题数，默认 5")
    parser.add_argument("--max-level", choices=LEVELS, default="6", help="生成词汇上限；7-9 也属于常见词汇")
    parser.add_argument("--seed", type=int, help="固定种子可复现；省略则随机")
    parser.add_argument("--attempts", type=int, default=100, help="每个候选答案的随机选线索次数")
    parser.add_argument("--output", type=Path, default=PRIVATE_ROOT / "examples" / "puzzles", help="仓库外的私有输出路径前缀")
    args = parser.parse_args()
    if args.one < 0 or args.two < 0 or args.one + args.two == 0 or args.attempts < 1:
        parser.error("题数须非负且总数大于零，尝试次数须为正数")
    seed = args.seed if args.seed is not None else secrets.randbits(64)
    try:
        args.output = private_output(args.output)
        lexicon = Lexicon.load()
        rng = random.Random(seed)
        records = []
        for size, count in ((1, args.one), (2, args.two)):
            generated = generate(lexicon, size, count, args.max_level, rng, args.attempts)
            records.extend(make_record(p, a, lexicon, i + 1) for i, (p, a) in enumerate(generated))
        bundle = {"schema_version": 1, "standard": lexicon.metadata["standard"], "seed": seed,
                  "max_level": args.max_level,
                  "level_policy": "按字面词条最早收录等级；不是逐义项等级",
                  "sources": lexicon.metadata, "puzzles": records}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for suffix, content in ((".json", json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"),
                                (".md", markdown_output(bundle)), (".html", html_output(bundle))):
            path = Path(str(args.output) + suffix)
            path.write_text(content, encoding="utf-8", newline="\n")
            print(path)
        print(f"Generated {len(records)} puzzles; seed={seed}; broad uniqueness + distinctness verified.")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
