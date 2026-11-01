# 统一接口与扩展方式

## 调度器

```python
from swarmbalance.scheduling.registry import create_scheduler, list_algorithms

scheduler = create_scheduler("ga", num_drones=10, seed=100)
action = scheduler.act(observation, current_time=0)
statistics = scheduler.get_stats()
descriptors = list_algorithms()
```

`observation` 是 Environment 产出的既有字典；`action` 保持 `{drone_index: [task_id, ...]}`。字段约定和 `SCHEMA_VERSION = "1.0"` 位于 `swarmbalance/contracts/scheduling.py`。算法只读取观测并声明动作，不持有 Environment。

统一方法为 `act()`、`get_stats()` 和 `synchronize(observation, active_tasks)`。无状态策略的 synchronize 默认无操作；事件驱动策略用它同步忙碌机与执行中的任务。每次会话 reset 和每个评测 episode 都创建新实例，不依赖复用旧实例清空状态。

`list_algorithms()` 返回不可变描述对象，字段为 key、label、available、reason；HTTP 层通过 `as_dict()` 转成原响应格式。未知算法在工厂抛 ValueError；可选求解器不可用时抛 RuntimeError。HTTP 适配保留原状态码与错误结构。

增加策略时实现 Scheduler，在 registry 的单一策略表中登记名称/模块/类，并补契约和真实运行测试。共用事件驱动算法可继承 EventDrivenScheduler，覆盖 `_build_optimizer()`；优化器输入/输出继续采用当前任务与无人机数据结构。

## 仿真与会话

```python
from swarmbalance.application.session import SimSession

session = SimSession()
session.reset("greedy", seed=100)
snapshot = session.step()
session.save_checkpoint("example")
session.load_checkpoint("example")
```

会话门面保留 reset、step、step_many、snapshot、map_static、任务/事故接口，以及检查点和演示方法。快照、检查点、事件、场景模块函数显式接收同一 session；Environment 的 incidents/handoff 函数同样接收原 Environment，不创建第二套状态。

检查点记录完整动态对象及 RNG，恢复后保留当前静态地图。环境代际不匹配会拒绝恢复；同名覆盖和第六个槽位的淘汰信息沿用原响应。

## 数据源与路由

`contracts/data_source.py` 定义 DroneSpec、NestSpec、TaskSpec、DataSource。具体实现位于 `infrastructure/data_sources/`，工厂为 `build_data_source(config)`。

DataSource 方法维持 `load_drones()`、`load_nests()`、`load_tasks(current_time)`、`build_task_source()`。任务源维持 generate_initial_tasks、step、unassigned_tasks、reset、set_seed、is_exhausted 约定。导入模板、企业数据和随机生成均转换为相同规格。

`contracts/routing.py` 定义 RouteRequest、RouteResult 和 RouteCostProvider 协议。规划器不写业务指标，调用方根据结果记账；成本提供者保留 distance、batch、eta、stats 方法和原时间单位。

## HTTP 与命令行

HTTP URL、方法、请求模型和响应字段未做版本升级；冻结契约在 `tests/fixtures/http_contract.json`。请求模型集中在 `web/schemas.py`，路由仅承担传输适配，共用 `web/dependencies.runtime`。

应用服务不依赖 web。配置、场景流程通过 ApplicationError 表达既有失败状态，由 HTTP 统一转换；接口不增加另一层响应包裹。

命令行统一通过 `python -m swarmbalance console|evaluate|selfcheck`。所有评测入口调用 `application/evaluation.py`，统一工厂、种子顺序和仿真循环；旧 Greedy 专用 CSV 的 15 列仅作为兼容投影保留。
