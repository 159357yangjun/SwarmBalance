# 旧 backend_si 兼容入口

此目录的 Python 模块只转发到 `swarmbalance/scheduling/`。算法配置已归位至 `config/schedulers.yaml`，依赖版本仍以根目录 requirements 为准。

新代码从 `swarmbalance.scheduling.registry` 创建算法；类实现为 pso.py、ga.py、ortools.py，共用 dispatch.py。旧模块导入仍指向同一规范模块对象。

详见[接口说明](../docs/INTERFACES.md)和[迁移说明](../docs/MIGRATION.md)。
