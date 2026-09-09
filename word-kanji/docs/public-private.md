# 公开仓库与私有题库的边界

公开仓库保留生成器代码、规则定义、通用 HSK／CC-CEDICT 词库、人工测试夹具，以及不列出具体答案的汇总统计。

以下内容保存于仓库外：完整 SQLite 题库、题面与答案映射、含解答的 JSON／Markdown／HTML 示例、原始数据缓存、截图，以及清理前的 Git 历史备份。通用词库虽然包含可以作为答案的汉字和词语，但不含“某题对应哪个答案”的记录，不属于题目答案表。

## 存储约定

默认私有目录为仓库旁的 `<仓库名>-private/word-kanji`。本地仓库为 `C:\Code\puzzle` 时，对应 `C:\Code\puzzle-private\word-kanji`。可以通过环境变量 `WORD_KANJI_PRIVATE_DIR` 指定其他仓库外目录。

所有会输出解答的生成命令默认写入私有目录，并拒绝将私有产物写入当前仓库，即使该路径已被 Git 忽略。仍可通过 `--output` 指定其他仓库外路径。

```powershell
$env:WORD_KANJI_PRIVATE_DIR = 'C:\Code\puzzle-private\word-kanji'
python -X utf8 word-kanji/generator.py
python -X utf8 word-kanji/scripts/select_one.py
```

测试使用人工字表或仅存在于内存的运行时生成结果，不在仓库中保存真实题库的解答夹具。词表规范化测试可以保留普通字词，因为它们不对应任何公开题面。

## 提交前检查

```powershell
python -X utf8 -m unittest discover -s word-kanji/tests -v
python -X utf8 word-kanji/scripts/audit_public.py
python -X utf8 word-kanji/scripts/audit_public.py --staged
python -X utf8 word-kanji/scripts/audit_public.py --history
```

检查脚本拒绝已知私有产物路径和答案映射字段，允许词库及数量统计；对自由文本规则说明仍需人工审阅。历史检查覆盖所有可达 Git 引用，避免只删除当前文件却留下旧版本。

私有目录、Git 备份包和生成缓存不应进入静态网站的部署目录。现有包含解答的生成格式只用于私有工作流。

## 静态闯关页面

部署范围仅为 `word-kanji/public/` 内的文件，在网站上对应 `/puzzle/word-kanji/`。`word-kanji/scripts/export_campaign.py` 从仓库外的筛选数据库生成 `word-kanji/public/campaign.json`，采用严格字段白名单，并由审计脚本检查其嵌套结构。项目内的本地预览服务也只映射本项目的 `public/`，不将仓库作为资源根目录。

每题仅发布随机 ID、四个题面字、四个线索词的等级、难度、随机盐和校验摘要。摘要输入为 UTF-8 编码的 `kanji-one-v1:<id>:<salt>:<NFC(trim(input))>`，算法为 SHA-256。不同题目独立加盐；内部题目 ID、答案分组、完整词语和答案字均不导出。

这是避免明文答案的静态判题方案；单字空间有限，仍可离线穷举摘要，不能严格保密。前端不加载通用词库或私有数据库，仅通过 Web Crypto 检查玩家输入。生产部署需要 HTTPS，本地 localhost 可以测试。

localStorage 仅保存题集版本和已过关数。判题成功后只读显示玩家当前填字，仍属于运行时输入；切换关卡、返回或离开页面时清除，不把玩家填过的正确内容保存为答案缓存。刷新后不恢复输入。相同题集重复导出保留公开标识、校验数据和版本；实际题集变更需明确迁移规则。
