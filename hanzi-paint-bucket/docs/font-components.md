# 六字体涂色连通块一致性

2026-11-10 用户新增要求：此前三款黑体加本机黑体、微软雅黑、等线，均用可用最细字重；同字在任一字体中的涂色连通块数与其他字体不同，则禁用于出题。用户补充：不计噪点区域。

## 定义与范围

- 当前应用于HSK二、三、四字合并库的全部候选字（2,879字），不限当前入选题里的字。独立成语库保持原版。
- 使用既有前端绘制与闭合区域算法：480×480画布、400px字号、alpha≥128为笔画，四邻接识别封闭空白。每款字体按完整字形居中绘制，涂色块不单独居中。
- 每个连通块面积**小于25像素**时忽略；恰好25像素保留。先逐块过滤，再统计数量。完全无有效区域的字计0；六字体均为0时一致。不能以多个噪点相加达标。
- 只比较有效连通块数量，不要求六种字体的轮廓、面积或位置相同。所有字体均有字形才能比较，禁止字体回退。缺字单列为无法验证并保守不出题，本次无缺字。
- 不一致字只从出题候选排除，仍留在完整多解比较词库中。噪点门槛仅影响该计数，不修改现有HarmonyOS题面、面积、覆盖率及IoU所用的原始掩码。

## 字体版本

| 字体 | 使用字体文件／字重 | 版本 |
| --- | --- | --- |
| Noto Sans SC | 此前使用的本机静态Thin | 0.00，2016-05-04 |
| MiSans | Thin | 4.003 |
| HarmonyOS Sans SC | Thin | 1.0 |
| 黑体 SimHei | Regular，本机仅此字重 | 5.03 |
| 微软雅黑 | Microsoft YaHei Light，非UI版 | 6.25 |
| 等线 | DengXian Light | 1.22 |

以真实文件为准，不人工减细或合成字重。微软雅黑从TTC提取第0字面到仓库外供浏览器加载。字体指纹、内部字重和渲染版本见 [font-components.summary.json](font-components.summary.json)，不可外推为所有版本的同名字体均有相同结果。除项目原有HarmonyOS外，其他字体不放入仓库或公开资源。

## 结果

2,879个候选字中 **389字不一致、0字缺字**。此前422题共839个不同汉字，其中189字不一致，直接影响179题（二字148、三字10、四字21）。这些为旧题库影响统计，不是重建后的净减少数。

首次应用该规则时，按三种长度分别用字去重，得到 **288题：240道二字、14道三字、34道四字**。此后二、三字改为共同去重，当前结果见[合并题库](hsk-combined-bank.md)。所有禁字和逐字体计数仅存于私有报告，不在仓库文档列出真实题目或答案映射。

## 复现与查看

```powershell
python -X utf8 hanzi-paint-bucket/scripts/analyze_font_components.py
python -X utf8 hanzi-paint-bucket/scripts/build_idiom_bank.py --hsk-combined
```

分析默认目录 `../puzzle-private/hanzi-paint-bucket/font-component-analysis/`，拒绝仓库内输出及覆盖已有非空目录。`--recount` 可依据已记录的每块面积重新按25像素门槛计数，不需重绘；只用于相同HSK快照。

私有 `components.sqlite` 保存每字每字体计数及原始各块面积；`banned-characters.json` 和 `report.html` 保存完整禁字清单、六字体计数及是否出现在旧题库。报告入口：`http://localhost:8004/puzzle/hanzi-paint-bucket/preview/font-report`（同样为本机、no-store，不能下载数据库或字体文件）。仓库仅保存无答案汇总。
