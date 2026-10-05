# Phase 1B-2 inventory —— ETA / 时间维度 / 电池续航的现状（只读盘点，未改任何行为）

生成方式：逐文件 grep + `Environment` 实跑读数（见每行"复算命令"）。日期 2026-10-04。
本轮范围纪律：**只回答三个问题并停下**，不实现、不改评分函数。

---

## Q1 当前 RoutePlanner 能否算出"从当前位置到目标的预计到达时间"？

**不能。** 它只输出几何量，全类零个时间字段。

| 事实 | 证据 | 复算命令 |
|---|---|---|
| `route_planner.py` 内 `time` / `duration` / `speed` 命中数 = **0** | `frontend/route_planner.py` 全文 | `grep -n "time\|duration\|speed" frontend/route_planner.py` → 空 |
| `RouteResult` 字段只有 waypoints/feasible/direct/detour/fallback/**distance** | `frontend/route_planner.py:38-66` | 读该 dataclass |
| provider 接口只有 `distance` / `batch` / `stats`，**没有 eta()** | `frontend/route_cost.py:39,43,86,115,118` | `grep -n "def \|name =" frontend/route_cost.py` |
| 但距离→时间是**一行可导**的：ETA = 航路长度 ÷ (speed × STEP_SECONDS) | 位移模型 `frontend/drone.py:259 max_distance = v * time_step` | 见下"口径基准" |

### 口径基准（现测，非推断）
```
STEP_SECONDS = 1.0        # frontend/drone.py:22，来自 config.drone.time_step
drone_0      type=light_express speed=20.0 m/s ⇒ 单步位移上限 20.0 m
est_range    = capacity/base = 380.0/0.032 = 11875 m ⇒ 飞完需 593.75 s = 594 env-step
```
⇒ **env-step 与秒目前 1:1**，所以"ETA 用 step 还是秒"现在看不出差别；但 `matching.py` 的
urgency 阈值写死 `/300.0`、PSO 的 `_meters_per_step` 又独立算一遍 —— 三处各持一份换算，
一旦 `time_step≠1` 就会分叉（同族缺陷已登记在登记表 M5：利用率分子步/分母秒）。

### 仓内已有的两套 ETA 实现（都在后端，Greedy 用不到）
| 位置 | 做法 | 距离口径 |
|---|---|---|
| `backend_si/pso_scheduler.py:182 calculate_travel_time(distance, speed)` | `distance/(speed*env_step_seconds)`，返回 env-step | **欧氏** |
| `backend_si/pso_scheduler.py:371 _pd_route_arrival_times` / `:1162 _estimate_ready` | 逐航点累加，含 ready_time 起算 | **欧氏** |
| `backend_si/ortools_scheduler.py:122` | 注释自陈"与 PSOOptimizer.calculate_travel_time 同口径" | **欧氏** |

⇒ 结论：ETA 概念在后端**存在且成熟**，但**全部按直线算**；而 1B-1 刚把 Greedy 的距离换成绕障口径。
这正是总纲 §17.1 记下的那条自相矛盾：**预测用绕障、时效用直线**。

---

## Q2 Greedy 的 `_score_task` 有没有任何时间维度的考量？

**有，但只有一个入口，且它是"剩余时限"而不是"到达时刻"。**

| 项 | 现状 | 证据 |
|---|---|---|
| 唯一时间量 | `remaining_time = task.get('remaining_time', inf)` | `frontend/greedy/scheduler.py:183` |
| 它的来源 | `ttlj = deadline - current_time`（观察空间产出） | `frontend/environment.py:1540-1550` |
| 它去哪 | 原样传给 `compute_match(...)` 的 `remaining_time` 形参 | `scheduler.py:187-195` |
| 在里面做什么 | `urgency = 1 - remaining_time/300.0` → 速度-时效匹配分量 | `frontend/matching.py:34-46` |
| **没有**的东西 | ① 没有任何"飞过去要多久"的量 ② 不看 drone 何时空闲（无 ready_time）③ 不做下一步到达时间推演 | `scheduler.py:157-197` 全文仅上述一处 time 引用 |

⇒ 用户描述的"现在得分高但飞过去太远 vs 现在得分稍低但已在附近"——**当前只用 `proximity`
（候选集内归一化的直线/绕障距离）表达"远"**，其权重是 `DISTANCE_WEIGHT=0.4`；
而"要飞多久才能开始服务"这条**完全不存在**。
另外 S2 那轮已钉过：deadline 只进 greedy 打分，GA/PSO/OR-Tools 的 deadline 引用数为 0
（门 `test_sla_consumption_gate`），所以 ETA 若引入，Greedy 面与后端面会再次分叉。

---

## Q3 电池/续航模型是否已存在？ETA 要不要考虑剩余电量？

**执行侧模型完整存在；调度侧只有一个"门槛式"用法，没有"这趟飞得完吗"的前向核算。**

| 层 | 现状 | 证据 |
|---|---|---|
| 耗电公式 | `distance × base × (1 + 载重惩罚) × 风倍率`，载重惩罚=`(current_load/carrying_capacity)×factor` | `frontend/drone.py:148-172 consume_battery()` |
| 写入点 | 实际飞行时按段调用（两处） | `drone.py:322`、`:362` |
| 风的接入 | Environment 只注入风场、不计算能耗；默认中性 ⇒ E1≡E0 | `environment.py:364` 注释 |
| 调度侧用法 A | **门槛**：`current/capacity < min_battery_ratio(0.6)` ⇒ 该机本轮不接单 | `greedy/scheduler.py:81-86` |
| 调度侧用法 B | **打分**：`range_match(capacity, base, total_distance)`，其中 `est_range=capacity/base` | `matching.py:49-60`，由 `scheduler.py:192-193` 喂参数 |
| 缺口 | `est_range` 不含载重惩罚、不含风、**也不含"当前剩余电量"**（用的是满容量）⇒ 它答的是"这机型装得下这段路吗"，不是"这架机现在还剩多少电够飞" | `matching.py:52` 用 `battery_capacity` 而非 `current_battery` |
| 硬可行性 | `_is_feasible` 只按**重量**过滤，超载才拒；电量不参与拒绝 | `scheduler.py:144-155` |

⇒ 对 1B-2 的直接含义：**ETA 与续航是同一笔账的两面**（时间=距离÷速度，耗电=距离×系数）。
如果 1B-2 只改 ETA 不动 range，则会出现"按绕障 ETA 排了序、但续航仍按直线满容量估"的新裂缝；
而把 `current_battery` 接进 range 属 1B-3（energy/range feasibility）的范围，用户已冻结"不许一次全改"。

---

## 给 1B-2 的三个待定项（需要拍板，不在本轮自行决定）

1. **ETA 放哪一层？** 选项 A：扩 `RouteCostProvider` 加 `eta(a,b,speed)`（保持两面可切换、
   与 1B-1 同构，代价是 provider 开始吃 speed 参数）；选项 B：在 Greedy 里由
   `provider.distance()/speed` 直接导出（改动最小，但换算口径散落）。
2. **只换 Greedy 的 ETA，还是同时修后端的直线 ETA？** 后者会让 GA 不再是阴性对照面，
   失去 1B-1 那种"另一面必须逐位不变"的判别力。建议先只动 Greedy，后端留作后续单独一步。
3. **ETA 进打分的方式**：`remaining_time` 现在是"任务剩余时限"，ETA 是"我多久能到"。
   二者应组合成" slack = remaining_time − ETA"再喂 urgency，还是新增独立分量？
   前者改变现有分量语义（等价性门失效），后者要定新权重（引入新的敏感性面）。

---

## 复算命令（本表每个数字都能翻开）
```bash
# Q1
grep -n "time\|duration\|speed" frontend/route_planner.py            # 期望：空
grep -n "def \|name =" frontend/route_cost.py                        # 无 eta()
# Q2
sed -n '157,197p' frontend/greedy/scheduler.py | grep -n "time"      # 仅 remaining_time 一处入口
sed -n '1536,1552p' frontend/environment.py                          # ttlj = deadline - now
# Q3
sed -n '148,172p' frontend/drone.py                                 # consume_battery 公式
sed -n '49,60p' frontend/matching.py                                # est_range 用满容量
# 现测值（STEP_SECONDS / speed / est_range）
python console/_readme_counts.py >/dev/null 2>&1; \
SWARM_BALANCE_SIM_CONFIG=config/simulation.json python -c "..."     # 见本文口径基准代码块
```
