# 汉字户型图（实验）

在可选的 5×5、6×6、7×7、8×8 网格上（默认 6×6），为简体汉字字形的不同连通块分配互不重叠的连通房间（当前默认八连通，可切换四连通）。当前包含黑体最细字重对比网页，以及离线分区算法实验，尚未提供正式答题流程或题库。

## 字体对比网页

运行 `python -X utf8 hanzi-floorplan/scripts/serve.py`，打开 http://localhost:8002/puzzle/hanzi-floorplan/ 。

对比思源黑体 ExtraLight、MiSans Thin、Noto Sans SC Thin、微软雅黑 Light、等线 Light、苹方 SC Ultralight、冬青黑体 GB W3、HarmonyOS Sans SC Thin。当前为本次对比默认选中思源黑体、MiSans 和 HarmonyOS Sans SC。其他字体不预加载、不预探测，勾选后才加载指定细字重。思源黑体、HarmonyOS Sans SC Thin 及各自许可证随页面提供，其余只读取本机指定字体，加载失败才显示不可用。也可以临时载入自己的字体文件。

默认“相同可见边长 + 100%”，使墨迹最大边长铺满方框并保持字形比例。支持编辑汉字、同字号／同可见边长对齐、网格尺寸选择与叠加、房间四／八连通切换、连通块着色及阈值调整。默认展示每款字体的房间轮廓与汉字叠加，灰格为空白，并标注所选目标的损失比例。当前默认使用“平滑中心线（实验）”：提取近似中心线，计算其横纵各 ±3 像素微扰的平均越界；可切回“墨迹越界（原指标）”。先最小化所选损失，相同损失时再最小化房间占用格数，保持每个房间非空、连通且互不重叠。通过指派下界及有限连通性分支定界核验，确认最优时标注已达最小，否则标注“尚未证明最优”和下界；面积仅用于同损失下的并列比较，不以增加主目标损失换面积；不添加对称、紧凑度、墙长或拐角评分。离线生成器仍为早期模型，不用于当前网页判定；分区只在内存中计算，不保存题目映射。静态部署只复制 `public/` 到 `/puzzle/hanzi-floorplan/`。

“小范围自动微调”默认开启，在当前摆放附近搜索位移组合，显示最终位移及所选损失前后对比。大小固定不变（微调 0%），水平／垂直各 −10 至 +10 像素，步长 2 像素，共至多 121 个位置；页面只保留开关，不再配置范围。保留原方案、禁止裁掉笔画，不保证连续范围的全局最优。

前端算法测试：`node --test hanzi-floorplan/tests/analysis.test.mjs hanzi-floorplan/tests/floorplan.test.mjs hanzi-floorplan/tests/placement.test.mjs hanzi-floorplan/tests/scoring.test.mjs`。Python 测试还覆盖预览服务的子路径、资源和源码隔离。

- [设计需求、例图观察及优化模型](docs/game-design.md)
- 字体：Adobe Source Han Sans SC ExtraLight（思源黑体简体中文最细字重）。
- 依赖：Python 3.10+；`python -m pip install -r hanzi-floorplan/requirements.txt`。
- 测试：`python -X utf8 -m unittest discover -s hanzi-floorplan/tests -v`。
- 生成器：`scripts/generate.py`；必须由调用者传入实验汉字，不内置真实题目与答案映射。

“笔画中心线”观察模式可查看近似骨架，显示未经自动微调的基准字形。平滑模式的损失不是墨迹像素数；页面另列实际墨迹越界供对照。骨架依赖字体和阈值，并非字体原始笔画路径，不能保证完全消除字重差异或分区跳变。

## 本地生成

从 [Adobe 官方字体仓库](https://github.com/adobe-fonts/source-han-sans/tree/release/OTF/SimplifiedChinese) 下载 `SourceHanSansSC-ExtraLight.otf`，默认放在仓库外的 `../puzzle-private/hanzi-floorplan/fonts/`；也可以通过 `--font hanzi-floorplan/public/fonts/SourceHanSansSC-ExtraLight.otf` 使用网页附带的通用字体。字体遵循官方仓库的 SIL Open Font License，许可证位于 `public/fonts/LICENSE.txt`。

在 PowerShell 中输入待试的汉字，再运行：

```powershell
$experimentChars = Read-Host '输入需要试验的汉字'
python -X utf8 hanzi-floorplan/scripts/generate.py --chars $experimentChars
```

可以通过 `--font` 指定字体，通过 `--output` 指定仓库外输出目录，通过 `--time-limit` 设置每字求解时间上限（秒）。默认输出到 `../puzzle-private/hanzi-floorplan/exports/`；也可用 `HANZI_FLOORPLAN_PRIVATE` 设置私有根目录，默认输出其 `exports/` 子目录。

产物为 `contact-sheet.png`（左侧纯户型，右侧叠字）和 `private-report.json`（字形、分区、参数及诊断）。它们均含可关联答案的信息，只能放在仓库外，不能直接发布。重复运行会覆盖指定输出目录中的这两个文件。

`public/` 只包含字体对比网页及通用字体，不包含离线实验报告或逐题叠字图。正式题库公开导出仍需另外设计字段白名单及独立 ID。
