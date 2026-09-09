# Puzzle 网页

每个 puzzle 在独立子目录中开发，网址统一为 `/puzzle/<项目名>/`。

- [word-kanji](word-kanji/README.md)：和同開珎。
- [仓库协作约定](AGENTS.md)：目录组织、需求归档及答案保护。

## 本地预览与部署

运行 `python word-kanji/scripts/serve.py`，访问终端列出的地址。项目内的预览服务将 `word-kanji/public/` 映射到 `/puzzle/word-kanji/`，不会公开项目的生成器、词库或文档。修改前端文件后刷新即可。

静态部署时，将各项目 `public/` 内的文件复制到网站发布目录的 `puzzle/<项目名>/` 下。无需为了部署路径改变源码结构，也不要发布整个仓库。

```text
puzzle/
├── AGENTS.md
├── README.md
└── word-kanji/
    ├── public/       页面及公开题集
    ├── docs/         规则和设计需求
    ├── scripts/      预览、生成、导出和检查工具
    ├── tests/
    ├── data/         通用词库
    └── datasets/     题库格式与汇总统计
```

含明文答案的私有题库始终保存在仓库外。
