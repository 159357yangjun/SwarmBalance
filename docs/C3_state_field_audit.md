# #69-C3：current_load / is_free 状态职责审计（零代码改动）

基线 `d493b6f`。目标：量"三个问题共用一个字段"的风险，并给三选一结论。
**结论先说：`is_free` 单语义、无风险；`current_load` 确实一名多义，但唯一会出错的消费方向已被 `_is_carrying` 隔离、且该口径早在本仓 M4 条目里被专门证伪过一次 ⇒ 本轮判"不需要拆"，只补一条防复活的断言建议。**

## 1. 全仓读写点清单 + 每处在问哪个问题

三个候选语义：**Q1 机子上有货吗（物理）** / **Q2 这架机可接单吗** / **Q3 服务已终结吗**。

### 1.1 `current_load`（写 8 处 / 读 12 处，真实行号）

| 位置 | 读/写 | 语义上在问 | 备注 |
|---|---|---|---|
| drone.py:82 | 写(初值0) | Q1 容器 | — |
| drone.py:244 `return_to_base` | 写 0 | Q1 | 回基地清货 |
| drone.py:249 `add_load` | 写 +=weight | **不是 Q1，是"已指派重量"** | ⚠ 关键：调用发生在**派单时刻**（env:1109/1121/1818），此时还没飞去取货 |
| drone.py:343 | 写 0 | Q3 伴生 | 航线跑空即卸货（drone.py 三段之一，禁改） |
| env:544 / :581 | 写 0.0 | 复位 | 故障注入/停飞路径 |
| env:1215-1217 / :1224-1226 | 写 −=weight | Q3 伴生 | dest 弹出即扣减 |
| env:1065 | 读 | **Q2 前置（容量校验）** | `planned_total_weight = current_load + task.weight` 比 capacity ⇒ 问"还能塞多少"，用"已指派"是对的 |
| env:1797 | 读 | Q1′（能耗预测） | `load_ratio` 进 chain 电量可行性 |
| env:1751 `_is_carrying` | 读（仅作下界筛） | Q1 | 见 §2 |
| env:1678 / :1693 | 读 | UI 展示 | 'current' / remaining_capacity |
| drone.py:170 `consume_battery` | 读 | Q1′（载重惩罚） | 本步实际耗电模型 |
| drone.py:253 `get_remaining_capacity` | 读 | Q2 前置 | 容量算术 |
| observer:129 `payload_at_reach` | 读 | 想问 Q1 | **实测无区分力**，见 §3.2 |
| observer:269 `load_at_consumption` | 读 | Q1（飞行中采样） | 有区分力，见 §3.2 |
| sim_session:793/:1006 | 读 | UI | — |
| pso_scheduler:195/211/575…653 | 读 | **局部变量，非同一字段** | 打包模拟内的自持累加器，不碰 Drone.current_load |
| test_wind_energy/test_wind_injection/test_command_console | 写 | 夹具注入 | — |

⇒ `current_load` 一名至少两义：**"已指派重量"（Q2 容量算术用，正确）** 与 **"机上物理有货"（Q1，误用会错）**。

### 1.2 `is_free`（写 14 处 / 读 20+ 处）

| 位置族 | 语义上在问 |
|---|---|
| drone.py:88/213/231/239/245/279/281/291/336/342/356/359、env:545/590/636/654/751/754 | 全部 **Q2「可接单吗」** |
| env:1044 / :1584 / :1636 / :1656、greedy/scheduler.py:75/89/302、pso_scheduler:981/995/1010/1030/1274/1320/1659、scheduling_interface.py:19 | 读，全部 **Q2** |
| env:1233 cleanup 入口、:1250 prev 快照、:1258 done-by-exhaustion | 读，**Q2**（转换检测） |
| observer:209/:262 DRONE_BECAME_FREE | 读，**Q2** |

⇒ **没有任何一处把 `is_free` 当 Q1 或 Q3 用**。需要问"下一个航点是取货还是送货"时，代码一律现读 `scheduled_position`（env:1044-1048、:1584-1590、`_is_carrying`:1752-1758），不从 is_free 猜。

## 2. 判别式：两个语义分叉后哪个读数会错，落到具体执行路径

分叉点在 **飞往取货点那一段**：`add_load` 于派单时已置 `current_load>0`（env:1109→drone.py:249），但货还没上机。
- 若拿 `current_load > 0` 当 Q1 ⇒ 该段被判"载货" ⇒ **空载率被低估**。
- `_is_carrying`（env:1741-1758）正是为此而写：先看 `current_load<=1e-9` 作下界短路，再按航线里下一个任务航点标签定夺（source→空载 / dest→载货）。其 docstring 明写"不能直接用 current_load>0"。

实测分叉规模（seed102 / 3600，逐步采样）：
```
busy_leg_samples=12414   load>0 & 航线判空载=6906   航线判载货 & load==0=0
```
⇒ 分叉真实存在且量大（约一半忙碌步），但**危险方向为 0**（不存在"真带货却读成空")。

## 3. 有没有实际消费者依赖那个歧义？（不为了立项而发明危害）

### 3.1 KPI 消费者：`empty_load_ratio`
唯一消费点是 env:1168 的 `if self._is_carrying(drone)` 分流 loaded/empty 里程 —— 它用的是**航线形状**，不是 `current_load`。所以 KPI 不吃这个歧义。

### 3.2 observer 的两个读数（我独立复算，未沿用旧断言）
```
DESTINATION_REACHED: 60 条，reach_has_load_evidence=60/60，payload_at_reach 非零=0/60
BATTERY_CONSUMED   : 10611 采样，load_at_consumption 非零=10583
```
⇒ `payload_at_reach` 在该时刻恒 0（record 于 :1212、扣减于 :1215，同帧先后），**无区分力**；observer 已在注释里拒绝拿它下结论，改用 `load_at_consumption` 作途中货物证人。这是"字段被读但结果不被消费"的正确处置。

### 3.3 能耗侧的量级（供判断是否值得动）
按"消耗为正"钳位后分叉段计量（充电步负增量不计）：
```
飞往取货段 109497.5 m / 7847.1 Wh 占加载能耗 48.7%
```
`consume_battery`(drone.py:170) 用 `current_load/carrying_capacity` 惩罚 ⇒ 这段空驶吃了载货惩罚。
但这属**能耗模型口径**（E1 情景系数、K 值为 assumption、无实测来源，见 docs/数据统计总表.md §E），
不是生命周期一致性缺陷，且落在本轮硬边界（drone.py 三段不得改）之内。

### 3.4 已有账：M4 曾专查过这条，并已定论
docs/数据来源与可追溯性登记表.md:331 记录：有人一度按 `current_load>0` 核对，得出"98.53% 空载里程其实带货"，**该结论已被撤回**，
并用"跟踪航线里被弹出的 source/dest 航点"重建物理货物重测，判 **`_is_carrying` 的口径是对的、代码不要动**。
本轮我用 route-pop 重建独立复算（seed102）：
```
agree=48.47%   carrying_but_counted_EMPTY=0.0 m (0.00%)   empty_but_counted_CARRYING=51.53%
reported empty_load_ratio=0.4843（与本探针一致）
```
⇒ **关键方向与 M4 完全一致：0.0 m 带货被算空载**（即报出的空载率只会偏保守、不会虚高）。
我的 51.53% 与 M4 的 3.40% 差在反方向的定义粒度（我这版按"任一在途任务"聚合、M4 按逐票货物重建），
不影响结论方向，故此处如实并列而非取其一。

## 4. 结论（三选一，明写）

**选「不需要拆」。** 论证：
1. `is_free` 实测单语义（Q2），~4100 步内 `free_with_load>0 / free_with_route_nonempty / free_with_service_waypoint` 全为 **0** ⇒ 不存在"is_free 替服务终结背书"的耦合，无需拆出 Q3。
2. `current_load` 虽一名多义，但**唯一会被误用的消费点已被显式挡掉**（`_is_carrying` 不吃 current_load 作真值，KPI 走航线形状），且误用方向经两次独立重建均为 0 m。
3. 剩下的两处"读 current_load 当 Q1"分别是(a)无区分力且已被拒绝消费的 `payload_at_reach`、(b)能耗模型的载重惩罚——后者属 E1 假设层口径、且落在本轮禁改边界内，不是靠拆字段能解的问题。
4. 拆字段要动 drone.py 的 add_load/consume_battery/return_to_base 与 env 的 6 处写入点，影响面横跨调度可行性、UI、能耗、observer ——**为一个已被证伪的风险付这个代价不成立**。

**触发重新评估的条件（登记，不在本轮做）**：
- 若将来引入"载货途中被召回/换货"使 `current_load` 与航线标签可能反向 ⇒ 第 2 条前提失效，需拆；
- 若要把 `payload_at_reach` 提升为正式证人（现在它是死读数）⇒ 必须同时给出"扣货早于记账"的顺序保证，否则该字段永远无区分力；
- 若 E1 能耗层要对外声称 Wh/km ⇒ 分叉段 48.7% 的载重惩罚归属必须先定口径（另轮，属 #65 Validation 面）。

**建议的最小加固（不在本轮实施，等裁）**：给 `_is_carrying` 配一条判别式断言——构造"已 add_load 但下一航点是 source"的机子，钉它返回 False；并把"禁止新代码用 `current_load>0` 当载货真值"写成一条扫描门。二者成本各一处，能把 §3.4 的人工结论变成机器守住的结论。

## 5. 硬边界遵守
未 push、未打 tag、paper/ 未碰、未用绝对坐标回退；drone.py 三段（:328-331 pop / :342-343 is_free+current_load / :362-366 单段直线位移）**零修改**；本轮 environment/drone 无任何改动（纯审计）。临时探针 5 个已同轮删除。citation --verify exit=0；README 计数不变。
