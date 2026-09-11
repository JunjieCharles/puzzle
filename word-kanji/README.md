# 和同開珎题目生成器

使用中文 HSK 2025 词库生成一字、二字标准型。支持逐词 HSK 等级、扩展词库唯一解审查、全题汉字互异及可选的同答案线索词不重复策略。

**仓库不保存真实题库的明文答案映射。** 带答案的题库、示例和缓存默认保存在仓库旁的 `<仓库名>-private/word-kanji`，详见 [公开与私有边界](docs/public-private.md)。公开仓库中的 HSK 和 CC-CEDICT 是通用词库，不是具体题目的答案表。

## 使用

### 闯关网页

在仓库根目录运行 `python word-kanji/scripts/serve.py`，访问 `http://localhost:8000/puzzle/word-kanji/`。
预览服务固定 JavaScript、CSS、SVG 和 JSON 的响应类型并禁用缓存；更新服务脚本后需重启。静态部署时也需正确配置 JavaScript MIME 类型，否则浏览器不会执行模块脚本。
前端文件集中在 `word-kanji/public/`；部署时将其中的文件复制到网站发布目录的 `puzzle/word-kanji/` 下，生产环境使用 HTTPS 以支持浏览器摘要校验。
无需安装前端依赖或构建。支持模式与题型选择、分页选关、一字及二字标准型答题、通过数加三的解锁范围、回看和本地进度；无尽模式暂未开放。
当前流程、输入交互和需求变更归档见 [页面设计需求](docs/game-design.md)。
帮助左侧的存档按钮支持复制文本存档码、粘贴导入，可用于备份或换设备恢复；格式与后续模式兼容约定见 [存档码](docs/save-code.md)。

一字公开题集包含 586 道闯关题；从 587 道每答案最难题中移出一道作为帮助例题，导出时也会排除该题及同题位置互换。重新导出一字题集：

```powershell
python -X utf8 word-kanji/scripts/export_campaign.py
```

难度按扩展词库（HSK 全等级 + CC-CEDICT）中，四个题面字在对应词首／词尾位置能组成的二字词数量评定。
四项计数从小到大排序后按字典序比较，先比较最小项，相同才比较下一项；越大越难，不求和，HSK 等级不参与难度排序。
关卡按难度从易到难排列，答案不重复，无需额外间隔。详细定义和新筛选结果见 [难度评定](docs/difficulty.md)。排序与答案分组只在导出时的内存中处理。

公开文件仅包含独立随机 ID、四个题面字、线索词等级、难度值、随机盐及题目绑定的 SHA-256 摘要。
浏览器只保存题集版本、实际通过数和已解锁范围内未通过题号，不保存输入或标准答案。初始解锁前三题，每通过一道新题再解锁一道。新本地记录使用 v2 键，同时读取并保留原 v1 记录；旧连续进度按前 N 题已通过转换，合并时保留双方已通过题目。重复导出相同题集会复用公开 ID、校验数据和版本，保留玩家进度；题集实际变化需另行处理迁移。导出优先以已有输出作为基准，否则以当前公开题集作为基准，请保留基准文件。

静态发布步骤与目录映射见 [部署说明](docs/deployment.md)。
许可署名随静态数据保存在 `NOTICE.txt`，游戏页面不展示说明文字。

### 生成工具

需要 Python 3.10 或更新版本，无第三方依赖。已附离线词库，日常生成不联网。在仓库根目录执行：

```powershell
# 随机生成一字、二字标准型各 5 题，写入仓库外私有目录
python -X utf8 word-kanji/generator.py

# 允许全部 HSK 等级，包括七至九级
python -X utf8 word-kanji/generator.py --max-level 7-9

# 全量枚举一字标准型，另存私有 SQLite
python -X utf8 word-kanji/scripts/enumerate_one.py

# 从私有全量题库中为每个答案只保留最难的一题
python -X utf8 word-kanji/scripts/select_one.py --one-per-answer
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
- 当前每答案最难题筛选：587 道题，覆盖 587 个不同答案字。此前字典序去重版 1,408 道题及旧等级优先版 1,407 道题保留在原私有数据集中。

二字标准型首发题库包含 **311 题**，622 个答案汉字在二字题库中各出现一次，不区分位置。筛选仍按六个外部线索的组词计数优先选择；排序改为比较先后填字两种顺序，每种顺序取较难一步，再取较容易的顺序，从易到难排列。公式及同分规则见[二字难度](docs/two-difficulty.md)，生成过程见[二字题库](docs/two-standard-count.md)。

允许与一字答案重复汉字；线索按“完整词语＋待猜位置”与一字题及其他二字题去重，同一个 AB 猜 A 和猜 B 可以分别使用。

生成二字题库：`python -X utf8 word-kanji/scripts/generate_two.py`。含答案数据写入仓库外私有目录 `datasets/two-standard-hsk-word-guess/`，公开输出为 `public/campaign-two.json`，另导出完整通用 HSK 二字词表供按需回看。可用 `--private-dir` 指定其他仓库外目录。

一字题库文件及版本 `3a92ed63edc4ea56` 保持不变；二字题库独立版本为 `d50323fe85aaf35b`。新存档码使用 `HT101-2`，继续接受 `HT101-1`，旧码缺省模式不会清除其已有进度。

2026-09-11 用户确认发布二字标准型。按此前确认，不处理首发前开发期二字题库的旧版本迁移；一字存档兼容逻辑保持不变。后续更换已发布题库须重新评估进度兼容。替换前的公开二字题库与私有生成数据在仓库外保留。

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
