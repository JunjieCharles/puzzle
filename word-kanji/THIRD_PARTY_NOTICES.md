# 第三方数据署名与许可

## HSK 词汇

- 整理者：Mani / [krmanik/HSK-3.0](https://github.com/krmanik/HSK-3.0)。
- 官方大纲发布者：中外语言交流合作中心；[中文考试服务网](https://www.chinesetest.cn/syllabus)提供大纲入口。
- 固定提交：`182692ce5a11bc30bdc771835d2f0f27491c25de`。
- 上游将 HSK 3.0 word lists 标注为 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，原许可保存在 [data/licenses/HSK-upstream.md](data/licenses/HSK-upstream.md)。此说明沿用词表整理数据的许可，不将其解释为对整份官方 PDF 的重新许可。
- 本项目的修改：解析制表符记录、展开括号可选汉字、移除义项编号、按字面合并并记录等级及来源、转换为 JSON。

## CC-CEDICT

- 作者：CC-CEDICT 社区贡献者；发布者 MDBG。源于 Paul Andrew Denisowski 于 1997 年启动的 CEDICT。
- 官方地址：[CC-CEDICT 下载页](https://www.mdbg.net/chinese/dictionary?page=cc-cedict)。
- 本次使用 [Punpuf/hsk-syllabus-vocabulary-parser](https://github.com/Punpuf/hsk-syllabus-vocabulary-parser) 的 `cedict_ts.u8` 镜像，固定提交 `2adf7c9885a17077966922b89de7ce655d7d82a0`，字典快照日期 2026-02-10。
- 许可：[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)。文件头保存在 [data/licenses/CC-CEDICT.txt](data/licenses/CC-CEDICT.txt)。镜像仓库的代码许可不替代词典数据本身的许可。
- 本项目的修改：只提取简体字段中的一字、二字纯汉字词，按字面去重；不保留全部英文释义。生成器使用该派生词库进行扩展唯一性审查。

## 派生数据

`data/hsk-2025.json`、`data/cedict-1-2.txt` 和生成的题集数据延续 **CC BY-SA 4.0**。再分发时保留作者、来源链接、许可链接及变更说明。许可法律文本见 [CC BY-SA 4.0 Legal Code](https://creativecommons.org/licenses/by-sa/4.0/legalcode)。本说明不替项目其他代码另行指定许可证。
