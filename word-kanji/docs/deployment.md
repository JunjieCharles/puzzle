# 静态发布

当前提供手动触发的 GitHub Pages 工作流 `.github/workflows/pages.yml`。仓库设置 Pages 的 Source 选择 GitHub Actions，再从 Actions 手动运行工作流。工作流运行测试与公开数据检查，只打包前端文件白名单，不运行私有题库生成器。

## Toy 独立产物

本地看效果：`python -X utf8 word-kanji/scripts/serve_toy.py`，打开 `http://127.0.0.1:8011/toy/word-kanji/index.html`。这个服务只监听本机，页面底部标明云存档和排行榜为模拟数据，不请求官方 SDK、不向平台读写。演示云数据只在页面内存中保存；浏览器缓存用于演示恢复。用户当前要求先预览、暂不发布，不能将本地预览视作上传授权。

普通网站保持现有部署流程。Toy 版本在仓库根目录运行：

```powershell
python -X utf8 word-kanji/scripts/build_toy.py --output "$env:TEMP/word-kanji-toy"
```

输出目录必须为空，脚本拒绝覆盖已有文件。只将这个输出目录交给 Toy CLI，不上传仓库、public 源目录或私有题库。产物根目录为 index.html，在 `/toy/<slug>/index.html` 下使用相对资源路径与 hash 导航；平台 SDK 从官方 HTTPS CDN 加载。打包剔除网页存档码 UI 与编解码模块，共用题集字节保持不变。

2026-10-02 已运行 47 项 Python 单元测试、Toy 云逻辑测试及 Edge 浏览器双版本测试。浏览器使用运行时人工题目和模拟 SDK，验证两题型过关、两榜独立、模拟先到先赢、重复提交、云恢复、账号隔离、普通网页存档码及手机/桌面布局；不代表真实 Toy 云接口已验证。测试入口：

```powershell
node --experimental-default-type=module word-kanji/tests/toy_cloud.mjs "$env:TEMP/word-kanji-toy"
# 需本地可用的 Node Playwright 和 Edge；可用 NODE_PATH 指向已有依赖目录。
node word-kanji/tests/browser_toy.cjs "$env:TEMP/word-kanji-toy"
```

浏览器测试自带仅映射两套公开资源的临时 HTTP 服务。第三个可选参数为仓库外截图目录，截图只包含人工数据。不要用测试账号或测试分数污染正式榜单。

Toy doctor 检查无 ERROR，需人工解释的 WARN：index.html 的目录规范化保留 location.hash（双子路径刷新已测）；两个榜位各自 getMyRank/submitScore 被循环启发式规则标记（不是循环逐 key 存云数据，榜位无批量接口）；资源文件名未加内容指纹（更新缓存效率建议）。这些提示不代表真实宿主联调已完成。

首次发布仍需准备名称、slug、封面和图标，安装/登录官方 CLI 后按技能规定先预览，再确认提交审核。真实平台中确认已登录时无操作自动恢复/保存、首次上榜确认不影响存档、双设备进度、两榜同分顺序及预览数据隔离。当前尚未上传。

## 普通网站

2026-10-02 网页版新增浏览器生成的无尽模式。发布白名单增加 `endless.js`、`endless-engine.js`、`endless-worker.js` 和完整通用词库 `endless-lexicon.json`；没有预生成题库或答案映射。Worker 使用相对 URL 加载，静态主机须提供 JavaScript MIME 类型及 HTTPS（localhost 可测试）。词库由 `scripts/export_endless_lexicon.py` 从完整通用源词库导出；若改变词库内容，必须同步评估生成器序列版本和 Worker 中的固定词库 SHA-256，不能直接替换已发布序列。本轮未运行线上发布。

最终地址为 `/puzzle/word-kanji/`，根据 Pages 的基础路径选择产物结构：

| Pages 基础路径 | 产物中的项目位置 |
| --- | --- |
| 空（域名根目录） | `puzzle/word-kanji/` |
| `/puzzle`（puzzle 仓库项目站） | `word-kanji/` |

其他基础路径目前直接报错，避免发布到错误地址。产物根目录提供相对跳转入口，项目内部使用相对资源路径和 hash 路由。

本地可运行 `python word-kanji/scripts/build_site.py --output <空输出目录> --base-path /puzzle`；域名根目录部署时省略 `--base-path`。发布目录不得改成整个仓库。

当前验证包括本地打包和浏览器检查；实际 GitHub Pages HTTPS 部署及真实手机键盘、剪贴板体验仍需在发布后检查。

2026-09-11 公开产物白名单增加 `campaign-two.json` 和完整通用词表 `hsk-two-words.json`，不打包私有生成缓存。原 `campaign.json` 不重新导出，保留一字题库版本和旧存档兼容性。新增二字路由在同一 `/puzzle/word-kanji/` 下使用 hash，不增加服务器路径规则。

通过数加三的解锁机制使用独立 v2 本地记录和协议 2 文本码，保留读取旧存档的入口。页面脚本及其存档模块使用 `v=progress-2` 资源参数，避免更新时复用缺少新接口的旧模块缓存；题库文件和题集版本不变。
