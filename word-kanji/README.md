# 和同開珎题目生成器

使用中文 HSK 2025 词库生成一字、二字标准型。支持逐词 HSK 等级、扩展词库唯一解审查、全题汉字互异及可选的同答案线索词不重复策略。

**仓库不保存真实题库的明文答案映射。** 带答案的题库、示例和缓存默认保存在仓库旁的 `<仓库名>-private/word-kanji`，详见 [公开与私有边界](docs/public-private.md)。公开仓库中的 HSK 和 CC-CEDICT 是通用词库，不是具体题目的答案表。

## 使用

需要 Python 3.10 或更新版本，无第三方依赖。已附离线词库，日常生成不联网。在仓库根目录执行：

```powershell
# 随机生成一字、二字标准型各 5 题，写入仓库外私有目录
python -X utf8 word-kanji/generator.py

# 允许全部 HSK 等级，包括七至九级
python -X utf8 word-kanji/generator.py --max-level 7-9

# 全量枚举一字标准型，另存私有 SQLite
python -X utf8 word-kanji/scripts/enumerate_one.py

# 从私有全量题库中按等级优先挑选同答案不复用线索词的题目
python -X utf8 word-kanji/scripts/select_one.py
```

默认私有目录可以用环境变量 `WORD_KANJI_PRIVATE_DIR` 更改。生成器拒绝把带答案的输出写入仓库；`--output` 也必须指向仓库外。

随机生成器同时输出私有 `.html`、`.md`、`.json`，用于本地审阅。这些格式含答案，不可直接部署为静态网站资源。SQLite 全量枚举与筛选不生成 HTML；已有数据库不会被覆盖。

| 随机生成参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--one` | `5` | 一字标准型数量，可为 0 |
| `--two` | `5` | 二字标准型数量，可为 0；总数须大于 0 |
| `--max-level` | `6` | 选词上限，可选 `1` 至 `6` 或 `7-9` |
| `--seed` | 每次随机 | 固定种子可复现，实际种子只记录在私有题集中 |
| `--attempts` | `100` | 每个候选答案的随机线索尝试次数 |
| `--output` | 私有目录下 `examples/puzzles` | 仓库外输出路径前缀 |

随机生成器同一批同一题型不重复答案；全量枚举器会保留同一答案的所有有效线索组合。候选不足时明确报错，不将随机尝试失败解释为无解证明。

## 当前数据规模

- 全量一字型：16,286,128 条位置排列记录，按同题定义对应 4,071,532 道不同题目，覆盖 587 个答案字。
- 同答案线索词不重复筛选：1,407 道题，仍覆盖 587 个答案字。

以上只公开数量，数据库保存于仓库外。格式与查询说明见 [全量数据](datasets/README.md)和[筛选策略](datasets/disjoint-selection.md)。

## 词库与质量

采用 [krmanik/HSK-3.0 的 2025 版](https://github.com/krmanik/HSK-3.0/tree/182692ce5a11bc30bdc771835d2f0f27491c25de/New%20HSK%20%282025%29)，对应[官方大纲](https://www.chinesetest.cn/syllabus)标注的 2025-11 发布、2026-07 实施版本。全部等级均属于本项目常见词汇范围；`7-9` 是合并组。默认六级上限只是选词范围。

等级按字面词条最早收录等级标注，不代表每个读音或义项都在该级教授。唯一性在完整 HSK 加 CC-CEDICT 的固定快照并集中检查，包括罕见词备选解，不按互异性排除其他答案。

详细来源和清洗政策见 [词库说明](docs/lexicons.md)，玩法和同题定义见 [规则文档](docs/wadou-kaichin-rules.md)。

## 验证与重建

```powershell
python -X utf8 -m unittest discover -s word-kanji/tests -v
python -X utf8 word-kanji/scripts/audit_public.py

# 可选：从固定上游提交下载，缓存于仓库外；重建公开的通用词库
python -X utf8 word-kanji/scripts/import_lexicons.py
```

词库文件及 SHA-256 记录在 [manifest.json](data/manifest.json)，生成时校验数据完整性。数据及派生题集的署名与许可见 [第三方说明](THIRD_PARTY_NOTICES.md)。
