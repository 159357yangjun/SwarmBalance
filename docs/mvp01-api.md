# MVP-01 真实后端接口

基线：`master 2ab60c69a806a22d7ba20353dee0571752a0e8e5`。第一版只接通已有杨浦地图、random 数据源和真实 greedy 调度器。未修改物理模型、指标算法或历史结果。这里交付后端；工作台前端尚待 AI-B 接入，旧 `/` 页面仍是原交互控制台。

## 启动与检查

在仓库根目录，按 CONTRIBUTING.md 准备 Python 3.10 和 requirements.txt 后：

```powershell
$env:PYTHONUTF8='1'
.venv310/Scripts/python.exe -m console.run --no-browser
.venv310/Scripts/python.exe -m unittest console.test_mvp_backend -v
```

接口文档可直接在 `http://127.0.0.1:8765/docs` 操作。仅运行一个服务进程；此本地 MVP 暂不支持多实例共享存储、用户隔离或远程公开部署。

默认数据目录 `results/mvp/`（git ignored）。可在启动前通过 `SWARM_BALANCE_MVP_DATA` 设置独立绝对路径。项目与运行结果在服务重启后仍可读。每次运行独立 Python 子进程，先移除继承的全部 `SWARM_BALANCE_*` 环境开关，再仅注入该次 `SWARM_BALANCE_SIM_CONFIG`；因此旧实验的路线口径、REACH 权重及外部 dump 路径不会覆盖保存输入。不改写 `config/simulation.json`、scheduler YAML 或旧结果。

## API 契约

所有请求/响应为 JSON，前缀 `/api/mvp`。

| 方法 | 路径 | 成功响应 |
|---|---|---|
| GET | `/defaults` | 200：`simulation` 完整默认配置、`algorithms:["greedy"]`、`algorithm_parameters:{}`、`seed:100`、固定 map 元数据 |
| POST | `/projects` | 201：保存后的完整项目 |
| GET | `/projects` | 200：`{"projects":[...]}`，更新时间倒序 |
| GET | `/projects/{project_id}` | 200：完整项目 |
| PUT | `/projects/{project_id}` | 200：保存后的完整项目；提交字段更新，`simulation` 对已有配置深合并，数组整体替换 |
| POST | `/projects/{project_id}/runs` | 202：创建真实异步运行，返回 `run_id` 与状态；无请求体 |
| GET | `/projects/{project_id}/runs` | 200：`{"runs":[...]}`，创建时间倒序 |
| GET | `/runs/{run_id}` | 200：真实状态、步数、进度、错误和输入指纹 |
| POST | `/runs/{run_id}/stop` | 202：停止请求及当前状态；重复调用幂等 |
| GET | `/runs/{run_id}/result` | 200：持久完成结果（含输入快照、引擎实读参数、完整 SimSession 快照） |

项目保存示例：

```json
{
  "name": "MVP-01 演示项目",
  "algorithm": "greedy",
  "seed": 101,
  "algorithm_parameters": {"accept_probability": 1.0},
  "simulation": {
    "environment": {"episode_max_steps": 600, "num_drones": 3},
    "heterogeneous": {"enabled": false},
    "task_generation": {
      "mode": "realistic",
      "realistic": {"total_tasks": 5, "initial_task_count": 5}
    }
  }
}
```

创建时，`simulation` 对仓库默认配置深合并后持久化为完整配置；省略时保存默认配置。`algorithm_parameters` 仅接受已有 greedy 键，运行时覆盖保存的 `simulation.environment.greedy`，并记录引擎模块实际读取的常量。更新算法参数字典时整体替换字典；清空传 `{}`。如果保留异构机队，`fleet_mix` 总数必须等于 `environment.num_drones`。`drone.time_step` 固定为 `1.0` 秒，其他值在保存时拒绝，保持仓库既有时间口径。修改机型配置只改变该次运行输入，未改变模型实现。

项目响应字段：`project_id`（32位 hex）、`name`、`simulation`、`algorithm`、`algorithm_parameters`、`seed`、`created_at`、`updated_at`（UTC ISO-8601）。

运行响应示例（数值为结构示意，实际由运行写入）：

```json
{
  "run_id": "0123456789abcdef0123456789abcdef",
  "project_id": "abcdef0123456789abcdef0123456789",
  "project_name": "MVP-01 演示项目",
  "algorithm": "greedy",
  "seed": 101,
  "status": "running",
  "step": 50,
  "total_steps": 600,
  "progress": 0.08333333333333333,
  "error": null
}
```

`status` 转换：`queued → running → completed/failed`，请求停止后 `stopping → stopped`。进度每5个真实引擎步更新；首次地图加载时可以为0。初始化完成后提供 `engine_input`（真实机队数、步数、算法、seed、greedy常量和配置/项目 SHA256）。指标只来自 `result.snapshot.stats`：`completed`、`generated`、`completion_rate`、`timeout_rate`、`energy` 等为既有 SimSession 口径，完整任务情况在 `snapshot.tasks` 与 `snapshot.task_catalog`。`completed` 表示配置规定的回合结束，并不保证所有任务都已送达。

结果响应：`run_id`、`project_id`、`project`（启动时完整不可变输入）、`engine_input`、`snapshot`、`finished_at`。项目后续更新不会重写历史运行输入。刷新或重启后按同一 `run_id` 读取同一结果。

## 错误与停止

- 400：未知算法/greedy字段、非法名称、数值/场景结构、非法 ID。`{"detail":"具体原因"}`。
- 404：合法 ID 对应项目、运行或结果文件不存在。
- 409：已有运行中实例（第一版一次运行一个），或运行未完成却请求完成结果。
- 422：非 JSON 对象、缺请求体等 FastAPI 请求结构错误。
- 引擎初始化或执行异常：运行状态变 `failed`，`error` 包含异常类型/消息，完整 traceback 在该运行 `worker.log`。进程非正常退出也由监视线程落盘为 failed。
- 停止：每个步之间检查停止标志；10秒未响应则终止子进程并标记 stopped。已停止运行没有完成结果。
- 服务重启：遗留 queued/running/stopping 写入停止标志并标记 `interrupted`，明确提示重新运行；完成的历史记录不变。正常服务关闭会请求停止本次子进程。

运行目录为 `runs/{run_id}/project.json`、`simulation.json`、`status.json`、`result.json`（仅完成后）、`worker.log`。JSON 采用同目录临时文件、flush/fsync、原子 replace；JSON 读与原子替换遇 Windows 短暂文件共享冲突时最多重试50次、每次10ms，持久权限错误仍明确抛出。父子进程通过 `status.lock` 协调状态读取和读改写，防止运行进度覆盖停止或中断状态，并避免高频轮询读句柄与替换竞争。不要手动编辑运行目录；故意破坏文件不属于正常恢复保障。

## 可复现的 HTTP 操作

```powershell
$api = 'http://127.0.0.1:8765/api/mvp'
$payload = @{name='MVP-01'; algorithm='greedy'; seed=101; simulation=@{environment=@{episode_max_steps=600; num_drones=3}; heterogeneous=@{enabled=$false}}} | ConvertTo-Json -Depth 20
$project = Invoke-RestMethod "$api/projects" -Method Post -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
$run = Invoke-RestMethod "$api/projects/$($project.project_id)/runs" -Method Post
Invoke-RestMethod "$api/runs/$($run.run_id)"
# status 为 completed 后：
$result = Invoke-RestMethod "$api/runs/$($run.run_id)/result"
$result.snapshot.stats
# 重启服务后仍可读取：
Invoke-RestMethod "$api/projects/$($project.project_id)"
Invoke-RestMethod "$api/runs/$($run.run_id)/result"
```

验收证据应额外保留实际请求、运行 ID、完整 HEAD、输出和日志；文档示例数字不属于执行证据。
