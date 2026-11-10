# 汉字油漆桶

将汉字笔画围出的闭合空白区域涂色。后续统一使用 HarmonyOS Sans SC Thin，词库采用扩展范围并排除单字词条。

- [当前设计需求](docs/game-design.md)
- [六字体连通块一致性过滤与禁字报告](docs/font-components.md)：计数忽略不足25像素的噪点区域。
- `scripts/specimen.py` 使用真实字体生成对比图，依赖见 `requirements.txt`。
- 前端已实现猜词闯关、选关、存档与帮助；另保留涂色实验及私有题库预览。
- [当前HSK二字＋三字＋四字合并题库](docs/hsk-combined-bank.md)：至少两字非空且非单矩形，二、三字共同用字去重（四字另计）、按算术平均覆盖率混合排序。生成命令：`python -X utf8 hanzi-paint-bucket/scripts/build_idiom_bank.py --hsk-combined`。旧[HSK二字库](docs/hsk-bank.md)作为历史记录。
- [平移相似度与阈值试验](docs/shift-similarity.md)：当前正式采用全局最大 IoU >95%、对应最小曼哈顿位移 <10px。
- [独立成语题库](docs/idiom-bank.md)：四字成语至少两字有有效涂色，空白字位参与完整词库单解检查；`python -X utf8 hanzi-paint-bucket/scripts/preview_bank.py --idioms` 在8005端口预览。
- [历史HSK三字及以上题库](docs/hsk-multi-bank.md)：已被二、三、四字合并版取代，三字词新增全部字位非空要求。

## 前端页面

**题目与答案预览**：运行 `python -X utf8 hanzi-paint-bucket/scripts/preview_bank.py`，打开 http://localhost:8004/puzzle/hanzi-paint-bucket/preview/ 。默认每页 12 题，可翻页、按题号跳转、显示／隐藏答案。仅监听本机，动态读取仓库外当前题库；不发布静态答案、不暴露数据库下载。`--bank` 可指定另一个仓库外题库，`--port` 可更换端口。

**猜词游戏与涂色实验**：

运行 `python -X utf8 hanzi-paint-bucket/scripts/serve.py`，打开 http://localhost:8003/puzzle/hanzi-paint-bucket/ 。仅 `public/` 可通过服务访问；静态部署时将其内容复制至 `/puzzle/hanzi-paint-bucket/`。

游戏仅使用最新 HSK 合并题库的 246 题；自由输入实验位于同目录 `lab.html`。公开导出：`python -X utf8 hanzi-paint-bucket/scripts/export_game.py`；题目内容未变时保留题集版本及进度。按用户要求试用 AES-GCM 密文，提交与查看答案统一在浏览器解密，提交时直接比较完整词语，不再使用题目摘要和盐；密钥随公开包提供，只避免直接存放明文，不防止开发者工具解密。`word-kanji` 的游戏实现不变。

HarmonyOS Sans SC Thin、完整字体字符覆盖表及许可证随页面提供，不再选择其他字体。加载失败或缺字时明确提示，不替代字体。实验页默认输入为空，最多显示前 16 个非空白字符，不保存输入及涂色结果。更新字体后运行 `python hanzi-paint-bucket/scripts/font_coverage.py` 重新生成覆盖表。

验证：`node --test hanzi-paint-bucket/tests/*.test.mjs`，以及 `python -X utf8 -m unittest discover -s hanzi-paint-bucket/tests -v`。

## 扩展词库统计与私有面积表

安装 `requirements.txt` 中依赖后，运行 `python -X utf8 hanzi-paint-bucket/scripts/analyze_hsk.py --skip-similarity`。分析器使用本机 Edge、前端渲染函数及项目附带的 HarmonyOS Sans SC Thin。缺字单列，不渲染替代字形。当前统计扩展词库与原 HSK 范围的并集，排除单字词条；字符也仅从剩余词条提取。

默认输出至仓库外 `../puzzle-private/hanzi-paint-bucket/extended-analysis/`，已有结果不会覆盖；重新统计请使用 `--output` 指定新的仓库外目录。`--lexicon` 指定 HSK 快照，`--extended-lexicon` 指定扩展词库；`--scope hsk` 切回 HSK（仍排除单字词）。去掉 `--skip-similarity` 可进一步计算固定位置的多解关系，耗时和内存会增加。

- `analysis.sqlite`：有字形字符（包括零面积字）的总面积、各闭合区面积、面积比例、包围盒、压缩掩码，以及合格词、单列缺字与元数据。开启多解分析时另存相似对。
- `character-areas.csv`：可用表格软件查看的逐字面积明细，仅供私有分析。
- `summary.json`：不含具体字词映射的计数、面积分位数和容差分析汇总。
- [当前扩展词库统计](docs/extended-analysis.md)；[历史 HSK 三字体结果](docs/hsk-analysis.md)。

分析测试：`python -X utf8 -m unittest discover -s hanzi-paint-bucket/tests -v`。更新词库、字体或渲染方式后必须重新统计，不能沿用旧面积和多解关系。

从仓库根目录运行，传入待观察文字：

```powershell
python -X utf8 hanzi-paint-bucket/scripts/specimen.py --chars $experimentChars
```

输出默认位于仓库外 `../puzzle-private/hanzi-paint-bucket/`；`--output` 可指定其他仓库外目录。使用项目附带的 HarmonyOS Sans SC Thin。截图包含字形与填色对应关系，因此不得复制回仓库或公开目录。
