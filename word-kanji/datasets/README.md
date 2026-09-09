# 全量一字标准型数据

生成范围为 HSK 2025 大纲全部等级（含 7–9）的一字标准型。布局固定为：

```text
       上
       ↓
左 → 答案 → 右
       ↓
       下
```

所有给定字与答案字互异；局部四个二字词和单字答案均有 HSK 词汇记录。唯一性在完整 HSK 加 CC-CEDICT 快照内验证，检查时不排除含重复字的其他答案。

**上、左线索互换以及下、右线索互换后的四种题面记录均保留**。按照[同题定义](../docs/wadou-kaichin-rules.md#24-一字标准型的相同题目定义)，这四条记录属于同一道题；交换入字与出字则不按此规则合并。同一答案可以对应多道不同题目。这里是全量枚举，不是随机抽样或每个答案仅取一题。

## 文件

| 文件 | 内容 |
| --- | --- |
| `one-standard-hsk-all.sqlite`（仓库外） | 私有全量题目、词条、等级、来源和统计，SQLite 3 格式 |
| [one-standard-hsk-all.summary.json](one-standard-hsk-all.summary.json) | 生成计数、等级分布、来源版本、耗时、文件大小和 SHA-256 |
| `one-standard-hsk-all.validation.json` | 生成后的独立抽查和统计核对结果 |

本次从 **16,622,336** 个候选题面记录中保留 **16,286,128** 条，按当前同题定义对应 **4,071,532 道不同题目**，覆盖 **587** 个不同答案；排除多解候选题面记录 **336,208** 条。SQLite 文件约 **831 MB**（793 MiB），含查询索引。实际生成及最终检查耗时约 33 秒。

数据库和生成时 JSON 摘要继续保留原样，其中 `puzzle_count` 是位置排列分别计数的记录数，不是按新同题定义去重后的数量。

同一答案之间限制线索词不重复的另存结果与策略说明见 [disjoint-selection.md](disjoint-selection.md)；该筛选不改变此处的全量数据集。

大型 SQLite 文件已移至仓库外私有目录 `<仓库名>-private/word-kanji/datasets`，不再存于此目录。脚本、格式说明及不含答案的 JSON 数量摘要可纳入 Git。重新生成命令：

```powershell
python -X utf8 word-kanji/scripts/enumerate_one.py

# 只读核对数据库、统计及按答案分层抽样的唯一解与等级
python -X utf8 word-kanji/scripts/validate_one_dataset.py
```

已有输出不会被覆盖；如需另存新版本，使用 `--output` 指定另一个仓库外路径。未完成文件以 `.partial` 结尾，只有全部生成及检查完成后才发布为 `.sqlite`。

## 表和字段

### `words`：词条及等级

- `id`：本数据文件内的词条编号。
- `word`：规范化汉字词条，同字面只存一次。
- `hsk_level`：可排序整数 `1…7`，其中 **7 表示合并的 7–9 级，不是单独的七级**。
- `hsk_label`：用于显示的 `1…6`、`7-9`。
- `listed_levels_json`：来源列出的所有等级。
- `source_entries_json`：原始词条、词汇编号、拼音、词性和等级记录。

保留随附 HSK 词库中所有一字、二字词条，不只保留本次出题用到的词。等级沿用字面词条最早收录等级，不表示逐义项难度。

### `puzzles`：题目事实表

- `id`：确定性枚举顺序中的题目编号。
- `answer_id`：答案词，引用 `words.id`。
- `top_word_id`：`上 + 答案` 的词条编号。
- `left_word_id`：`左 + 答案` 的词条编号。
- `bottom_word_id`：`答案 + 下` 的词条编号。
- `right_word_id`：`答案 + 右` 的词条编号。
- `max_hsk_level`：答案及四个局部词的最高等级，编码同上。

不重复存储所有词条文本和级别，避免放大文件。通过词条编号可以完整恢复题面、每个词及其级别。题表已建立答案索引以及 `(max_hsk_level, answer_id)` 索引。

### `puzzle_details`：直接可读的视图

提供 `id, answer, answer_level, top, left, bottom, right, top_word, top_level, left_word, left_level, bottom_word, bottom_level, right_word, right_level, max_level`，适合直接查询或按需导出 CSV。

### 统计与元数据

- `answer_stats`：每个有候选的答案的候选数、保留数、多解排除数。
- `level_stats`：按题目最高 HSK 等级统计，互斥分组，不是累计数。
- `word_usage`：每个被使用词条的答案使用次数及局部边使用次数。使用次数以位置不同的题目分别计数。
- `metadata`：`key='build'` 对应完整生成及词库版本信息，值为 JSON。

## 查询示例

```sql
-- 查看前十道题及全部词语等级
SELECT * FROM puzzle_details ORDER BY id LIMIT 10;

-- 按同题定义选取规范代表；两个组分别排序，不跨组排序
-- 当前 words.id 按字面排序，因此可比较入词 ID 和出词 ID
SELECT COUNT(*) FROM puzzles
WHERE top_word_id < left_word_id AND bottom_word_id < right_word_id;

-- 按最高 HSK 等级统计（7 为 7–9 级）
SELECT max_hsk_level, puzzle_count FROM level_stats ORDER BY max_hsk_level;

-- 所有词均不超过六级的题数
SELECT SUM(puzzle_count) FROM level_stats WHERE max_hsk_level <= 6;

-- 各答案对应多少道题
SELECT w.word, w.hsk_label, s.puzzle_count
FROM answer_stats s JOIN words w ON w.id=s.answer_id
ORDER BY s.puzzle_count DESC;

-- 查询指定答案
SELECT d.* FROM puzzle_details d WHERE d.answer=:answer LIMIT 20;

-- 哪些局部词最常被使用
SELECT w.word, w.hsk_label, u.edge_uses
FROM word_usage u JOIN words w ON w.id=u.word_id
ORDER BY u.edge_uses DESC LIMIT 20;
```

Python 标准库的 `sqlite3` 即可读取，不需第三方依赖。建议先按条件筛选，再导出所需数据；不要一次把全部题目载入内存。

数据及派生题集延续 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，来源和修改说明见 [第三方说明](../THIRD_PARTY_NOTICES.md)。
