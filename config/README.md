# 配置数据

- simulation.json：仿真场景与业务参数。
- schedulers.yaml：调度器超参数，原 backend_si/config.yaml 内容。
- positions.json：位置输入。
- import_templates/：CSV / GeoJSON 数据源模板。
- scenes/：用户保存的持久场景，文件名/格式保持兼容。

规范加载器位于 `swarmbalance/infrastructure/config/loader.py`，`config/loader.py` 只保留旧导入兼容。加载优先级为显式路径、SWARM_BALANCE_SIM_CONFIG、simulation.json；读取不缓存 JSON 内容。
