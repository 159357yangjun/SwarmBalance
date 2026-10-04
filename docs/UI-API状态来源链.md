# UI / API 状态来源链（Q2 审计）

> 取证方式：主线程逐条读原文。**背景须如实记**：本轮三次子代理宽审计全部撞上限中断、
> 零交付（Q1 177 工具、Q2 166 工具、上一轮 76 工具），故本文与 `docs/调度预测口径与执行口径.md`
> 均由主线程自读取得，行号为本人所见。HEAD `94e3816`，纯只读。

## 1. 数据链总览

```
Environment（Python 对象真源）
   ↓  console/sim_session.py  _drones_snapshot / _tasks_snapshot / map_static
Session snapshot（JSON 契约）
   ↓  console/server.py       GET /api/snapshot
前端   console/static/index.html   d.x / d.y / d.state / t.status / …
```

HTTP 面（`console/server.py`）：`/api/snapshot`、`/api/step`、`/api/reset`、`/api/tasks/inject`、
`/api/tasks/{id}/candidates`、`/api/drones/{id}/charge|incident`、`/api/nests/{id}/incident`、
`/api/map`、`/api/checkpoints*`、`/api/scenarios`、`/api/meta`、`/api/algorithms`。

## 2. 六类状态的来源链

| 状态 | Environment 真源 | API 字段 | 前端消费 | 单一真源？ |
|---|---|---|---|---|
| drone position | `drone.py:72-73` `self.x/self.y` | `sim_session.py:783-784` `"x"/"y"` | `index.html` `d.x`(5) `d.y`(5) | **是**（但只有两轴，无 z） |
| route / trajectory | `drone.scheduled_position`（计划航点队列） | `remaining_route_m`（`:773-778` 会话层现算折线长）；轨迹另存 `sim_session.py:189` | `d.remaining_route_m`(1)、`d.task_chain`(4) | **否**：计划(`scheduled_position`) 与历史描点(`trajectories`) 两套并存，且里程由会话层自己 `((cur-prev)**2)**0.5` 重算，未复用 `_dist_m` ⇒ 副本漂移风险 |
| battery | `drone.current_battery` | `battery` / `battery_ratio` / `battery_capacity` | `d.battery_ratio`(1) | **是** |
| **task status** | `Task.status`（`task.py:83`） | **四个不同来源**（见 §3） | `t.status`(10) | **否 — 即 F2** |
| station / berth | `ChargingStation.occupied/berths` | nests 段 + `map_static()` | `s.state`(9) | 部分：`nest_closed/reopened` 事件另有路径（`sim_session.py:263-280`） |
| metrics | `environment.get_statistics()` | snapshot metrics 段 | 图表 | **是** |

## 3. F2 现场：同一个 `status` 键的四种来源（亲验行号）

```
sim_session.py:863   "status": str(getattr(t, "status", "pending"))   ← 读 Task 真字段
sim_session.py:900   row.update({"status": "pending", ...})            ← 会话层直接造
sim_session.py:917   "status": "in_progress" if executing else "assigned"  ← 会话层推断
sim_session.py:936   "status": "completed"                             ← 硬编码字符串
```

叠加 `frontend/task.py:118-123` 的白名单只有 `pending/in_progress/completed/failed`
（无 created/loaded/delivered），且送达完成不回写状态（`environment.py:374-443` 内无
`update_status("completed")`）⇒ **"任务处于哪个阶段"这个问题在系统里有多个答案，
而它们只在当前数据下恰好一致。**

同类问题在无人机侧也有一份：`_drone_state(d)`（`sim_session.py` 内）用六个布尔字段
（`out_of_service` / `is_charging` / `swap_remaining_steps` / `awaiting_berth` /
`_manual_charge_requested` / `is_free`）**按顺序推断**出 `offline/charging/waiting_berth/to_nest/busy/idle`。
这是派生量而非状态字段 —— 前端 `d.state` 被用 12 次，说明它是事实上的对外契约，
但 Environment 里并不存在这个量。

## 4. 引入 StateStore / Telemetry 后，前端要不要改

**可以不改（前端只认 JSON 字段名，不碰 Python 对象）**：
`x, y, state, battery_ratio, battery, battery_capacity, speed, load, capacity,
executing_task, chain_len, task_chain, remaining_route_m, out_of_service(_reason),
type, idx, id` + tasks 的 `status`。
只要新 StateStore 产出同名字段，`index.html` 一行不用动。

**必须改**：
1. **任何新增维度**：前端解构写死二元组（`index.html:2485` `tr.map(([x,y]) => …)`、
   `:1886` `push([d.x, d.y])`）⇒ 上 z 时必须改（详见 `docs/二维假设清单.md` E/F 类）。
2. **伪高度**：`index.html:2472-2473` 的 `alt = (state==='busy'?64:…)*vx` 是按 state 硬编码的
   装饰值 ⇒ 一旦有真 z，这一行必须换成数据，否则界面继续掩盖模型缺口。
3. **若 status/state 语义要扩展**（比如加 `PICKUP_ENROUTE`）：前端有 `rank.get(r["status"], 9)`
   之类的排序映射与配色分支 ⇒ 需要同时登记，未知值会落到默认档而不是报错。

## 5. 对 Phase 1 的直接含义

- StateStore 的**最小可行形态**就是"把 `sim_session` 里那些派生函数搬进一个有名字的对象"，
  而不是新造一套数据 —— 因为字段名已经稳定，迁移成本主要在写入方。
- F2 的修法必须是**先定状态机再改派生**：`_drone_state` 与四路 `status` 都改成读单一真源，
  否则抽完 StateStore 仍然是"多处各算一遍"。
- `remaining_route_m` 这类会话层重算的里程，应与 §5.2 的 `RouteCostProvider` 合一 ——
  现在它既不是 A* 里程也不是环境累计里程，是第三种口径。
