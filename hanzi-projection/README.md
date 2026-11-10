# 汉字双视图（暂定）

将汉字光栅化为灰度图，对比不同字体的逐行、逐列黑度累计投影。当前为字形实验室，不是正式题库。

- [设计需求与边界](docs/game-design.md)
- 预览：在仓库根目录运行 `python hanzi-projection/scripts/serve.py`，打开 http://localhost:8001/puzzle/hanzi-projection/ 。
- 测试：`node --test hanzi-projection/tests/projection.test.mjs`。
- 仅发布 `public/` 内容，目标路径为 `/puzzle/hanzi-projection/`；无构建依赖。

字体只使用访问者已安装的版本，不随网页分发。宋体、黑体、楷体、仿宋、微软雅黑、等线、苹方、冬青黑体和思源黑体 CN 会按实际可用情况显示。

默认采样画布为 256×256，默认对比黑体、微软雅黑、思源黑体。

默认常用字用于观察结构差异，可直接修改输入。所有图像及曲线即时计算，不存储或导出标准答案映射。
