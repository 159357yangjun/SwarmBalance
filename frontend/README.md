# 旧 frontend 兼容入口

此目录不再包含仿真内核实现。现有文件仅把旧导入和命令转发到同一份 `swarmbalance` 规范模块。

仿真代码位于 `swarmbalance/simulation/`，算法位于 `swarmbalance/scheduling/`，页面位于 `swarmbalance/web/static/`。新评测命令为 `python -m swarmbalance evaluate --policy ga`。

保留旧脚本以兼容既有启动方式；新开发请直接使用规范包。详见[迁移说明](../docs/MIGRATION.md)。
