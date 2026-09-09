# 同一答案的线索词不重复筛选

这是**生成器的可选题集筛选策略**，不属于“良好题目”的质量标准，也不改变标准型、变型或 n 字型的定义。

当前适用于一字标准型。筛选输入为之前生成的完整 HSK 一字标准型数据库；保留原文件，结果另存为私有目录中的 `one-standard-hsk-disjoint.sqlite`。两个数据库均位于仓库外的 `<仓库名>-private/word-kanji/datasets`。逐词等级、词条来源、题面和答案继续保留，读取方式仍可使用 `puzzle_details` 视图。

本次筛选得到 **1,407 道题**，覆盖 **587 个答案字**，每个答案保留 1–16 题，数据库约 **1.81 MB**。原始的 16,286,128 道题数据集保持不变。

这里的 1,407 道也符合[同题定义](../docs/wadou-kaichin-rules.md#24-一字标准型的相同题目定义)下的不同题目计数，因为位置互换的重复记录已被筛选排除。原始数据中的 16,286,128 是题面记录数，对应 4,071,532 道不同题目。入字、出字的身份不能互换后忽略；但不同题若共享线索词，仍可能被本生成器策略过滤。

| 每个答案保留题数 | 答案字数 |
| --- | --- |
| 1 | 274 |
| 2 | 126 |
| 3 | 79 |
| 4 | 36 |
| 5 | 24 |
| 6 | 17 |
| 7 | 8 |
| 8 | 8 |
| 9 | 6 |
| 10 | 3 |
| 11 | 3 |
| 12 | 1 |
| 13 | 1 |
| 16 | 1 |

## 策略的准确含义

1. 按答案汉字分别处理，不同答案之间允许出现相同线索词。
2. 每题用于去重的词是四个局部二字词：`上+答案`、`左+答案`、`答案+下`、`答案+右`。
3. 同一答案本身必然重复，因此**单字答案词不参与跨题去重**；它的等级仍保存在数据中。
4. 对四个线索词的等级从低到高排序，再按此序列从大到小选择。先提高最低等级；最低等级相同时提高第二低等级，以此类推。7–9 是高于 6 的一个等级组。
5. 等级序列相同时，选择原数据集中题目编号最小的代表，以保证可复现。
6. 保留一题后，剔除所有与它共享任意线索词的同答案候选，再从剩余候选中继续选择，直到没有可选题。

例如 `(5,5,5,5)` 优先于 `(1,7–9,7–9,7–9)`，而 `(5,5,6,7–9)` 优先于 `(5,5,5,5)`。这不是只比较最高等级，也不是比较平均等级。答案等级对同一答案的候选恒定，不影响排序。

位置互换的四种题面使用完全相同的词，必然互相冲突。实现只对每组的一个规范代表排序（上词编号小于左词、下词编号小于右词），这与在全体位置变体中按相同优先级和原始编号执行贪心选择等价。

该策略得到的是**等级优先贪心选择的数量**，不声称是“词不重复条件下最多可选多少题”的全局最优解。换用不同的同等级决胜规则也可能改变最终数量；当前规则已固定并记录到数据集元信息中。

## 执行

在仓库根目录执行：

```powershell
python -X utf8 word-kanji/scripts/select_one.py
```

也可使用枚举入口并显式指定仓库外的原始数据集，例如本地路径：

```powershell
python -X utf8 word-kanji/scripts/enumerate_one.py --disjoint-words-from C:/Code/puzzle-private/word-kanji/datasets/one-standard-hsk-all.sqlite

# 逐题复核，并对所有原始候选独立验证贪心选择顺序
python -X utf8 word-kanji/scripts/validate_selection.py
```

默认仍使用全部 HSK 等级（含 7–9）。可以加 `--max-level 6`，从原题集中只考虑最高等级不超过 6 的题目，然后执行相同的等级优先策略。已有目标文件不会被覆盖；再次运行请指定新输出路径。

## 数据表与来源追踪

继续提供 `words`、`puzzles`、`puzzle_details`、`level_stats` 和 `word_usage`。`words` 完整复制原词条及所有等级证据；`puzzles` 只包含筛选后的题目。

新增表：

| 表 | 内容 |
| --- | --- |
| `selection_trace` | 每道保留题对应的原题编号、该答案内的选择顺序、排序用等级序列和优先分数 |
| `selection_stats` | 每个答案的可用原题数、规范代表数、保留数、因跨题词语复用排除的原题数 |

`answer_stats` 中 `candidate_count` 与 `rejected_multiple_count` 保留原始全量枚举的统计口径，而 `puzzle_count` 更新为本次保留数。分析筛选效果请使用 `selection_stats`；不能再用前两个旧字段的差值计算本次保留数量。

概要见 [one-standard-hsk-disjoint.summary.json](one-standard-hsk-disjoint.summary.json)。其中包含筛选策略、数量、每个答案题数分布、各等级数量、原始数据集及新数据集 SHA-256。

```sql
-- 哪些答案保留了最多题目？
SELECT w.word, s.selected_puzzles
FROM selection_stats s JOIN words w ON w.id=s.answer_id
WHERE s.selected_puzzles>0 ORDER BY s.selected_puzzles DESC;

-- 查看某个答案的选择顺序与等级优先序列
SELECT d.*, t.choice_number, t.source_puzzle_id, t.sorted_clue_levels_json
FROM puzzle_details d JOIN selection_trace t ON t.puzzle_id=d.id
WHERE d.answer=:answer ORDER BY t.choice_number;
```

筛选仅在已通过字格互异和扩展词库唯一性检查的题目之间进行，未删除或更改原题目的规则。数据许可和来源沿用 [第三方说明](../THIRD_PARTY_NOTICES.md)。
