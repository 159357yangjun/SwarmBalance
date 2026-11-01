# 旧 console 兼容入口

实现已迁移至 `swarmbalance/web/`、`application/`、`diagnostics/` 和 `cli/`。此目录保留旧模块导入和 `python -m console.run` / `console.selfcheck` 的转发。

新启动方式为 `python -m swarmbalance console`，页面资源位于 `swarmbalance/web/static/`。详见[架构说明](../docs/ARCHITECTURE.md)。
