# 静态发布

当前提供手动触发的 GitHub Pages 工作流 `.github/workflows/pages.yml`。仓库设置 Pages 的 Source 选择 GitHub Actions，再从 Actions 手动运行工作流。工作流运行测试与公开数据检查，只打包前端文件白名单，不运行私有题库生成器。

最终地址为 `/puzzle/word-kanji/`，根据 Pages 的基础路径选择产物结构：

| Pages 基础路径 | 产物中的项目位置 |
| --- | --- |
| 空（域名根目录） | `puzzle/word-kanji/` |
| `/puzzle`（puzzle 仓库项目站） | `word-kanji/` |

其他基础路径目前直接报错，避免发布到错误地址。产物根目录提供相对跳转入口，项目内部使用相对资源路径和 hash 路由。

本地可运行 `python word-kanji/scripts/build_site.py --output <空输出目录> --base-path /puzzle`；域名根目录部署时省略 `--base-path`。发布目录不得改成整个仓库。

当前验证包括本地打包和浏览器检查；实际 GitHub Pages HTTPS 部署及真实手机键盘、剪贴板体验仍需在发布后检查。
