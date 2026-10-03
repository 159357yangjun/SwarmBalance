# Critical Fixture 定义（已冻结）

> **本轮冻结的是"场景定义"，不是"场景统计真值"。**
> 下面每档的 timeout / delay / unfinished 读数是 n=2 的**探索阶段读数**，不得引用为基准值：
> 同一格两个重复之间最大差到 **0.12**（`is0.40×f6` 超时率 0.398 vs 0.518），这个宽度不足以支撑任何算法比较。
> 正式基准值等 seed 数提高后另行签字。

## runner 的 grid 块行为契约（一行一条，改动须同步此处）

| 输入 | 行为 | 谁在守 |
|---|---|---|
| `axes` ≥ 1 个、每轴 values 非空 | 产出笛卡尔积全部格 | G1 / G2 |
| **单轴** | **允许**（一维情景列表就是单轴 grid；E1 的 wind 三档即此形状） | G2 |
| `axes` 为空 | `[GRID_AXES_EMPTY]` 硬失败 | G2b |
| 某值缺 `patch` | `[GRID_PATCH_MISSING]` 硬失败 | G3 |
| 某轴 values 为空 | `[GRID_AXIS_EMPTY]` 硬失败（不静默吞掉整张网格） | G4 |
| 每格 patch | 必须**同时**含所有轴的键；标签与 patch 由同一段代码核对 | G5 |
| 兄弟格之间 | deep-merge 不得互相污染；输入轴定义不得被就地改写 | G6 |
| 同一 repeat 跨格 | 共用 seed ⇒ 跨格比较是配对的 | test_repeats_pair_same_seed |

> 变更记录：G2 原为"单轴禁止"，在 e0_baseline（单轴 fixture）真实使用时被自己的守卫绊倒，
> 判定属把判据写窄 ⇒ 改为"只禁 0 轴"。这是 runner 的行为契约，不只写在测试 docstring 里。

## 为什么必须是这三个旋钮组合

上一轮用 `total_tasks` 当压力轴是错的：realistic 模式每次只生成 1 个任务、平均到达间隔 40.625 步，
episode 固定 3600 s ⇒ 实际生成量被到达过程钉在 ~103（理论 100.6 + variance 抖动）。
所以 `120/150/180/240 tasks` 四档跑的是同一个实验。真正的负载维度是**到达强度**，见下。

## 三个 fixture

| ID | 角色 | interval_scale | fleet_size | L:S:H | arrival_intensity (tasks/min) | 探索读数（n=2 均值） |
|---|---|---|---|---|---|---|
| **C-1** | Primary Critical（主测试台） | 0.70 | 6 | 3:2:1 | **2.467** | generated 148.0 · unfinished 41.5 · timeout 0.235 · on_time 0.765 · delay 96.2 s · swaps 22.5 |
| **C-2** | High Stress（放大效应检查） | 0.55 | 4 | 2:1:1 | **2.967** | generated 178.0 · unfinished 103.5 · timeout 0.497 · on_time 0.503 · delay 373.2 s · swaps 16.0 |
| **S** | Severe（边界/崩溃趋势，不做精细比较） | 0.40 | 4 | 2:1:1 | **4.000** | generated 240.0 · unfinished 159.0 · timeout 0.599 · on_time 0.401 · delay 560.7 s · swaps 15.0 |

用法约定：**C-1 看小变化，C-2 看放大效应，S 看系统边界。**
C-2 不当主 Critical 用它——它已经很靠近严重拥塞（on_time 0.50），小的模型改动可能把它直接推进饱和区，反而看不出差异。

## 每档共同的固定项（不随 fixture 变）

```yaml
load_dimension: arrival_intensity          # 不是 task_count —— 见上文原因
requested_total_tasks: 240                 # ⚠ 仅生成上限保险，不代表 episode 内真有 240 单
episode_max_steps: 3600                    # 1 step = 1 s（config/simulation.json environment.time_step）
algorithm_under_probe: greedy              # 搜索阶段单算法；四算法比较是下一阶段的事
repeats: 2                                 # 探索阶段最小值，正式基准须提高
seed_base: 900                             # grid 块偏移 40000 ⇒ 实际 seed 40901 / 40902
heterogeneous.enabled: true                # 沿用结项口径
nest_berths: 2 / charging_stations: 5      # 未动
consumption_base / load_penalty_factor / 电池容量 / 机型参数 / SLA 系数   # 全部未动
```

`arrival_intensity = actual_generated_tasks / actual_episode_seconds × 60`。
注意本批 **20/20 次运行全部撞到 3600 s horizon** ⇒ `总步数` 不是有效负载读数，
而 arrival_intensity 退化为"设计到达速率"而非"结果"。这一点在读结论时必须带上。

## 复算命令

```bash
# 重放这批网格（约 20 次运行；preset_key != conclusion ⇒ 双闸门拒写答辩数据源）
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -m experiments.runner \
    --preset experiments/presets/arrival_pressure.yaml

# 只看某格的原始逐次记录（不重跑）
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -c "
import csv,pathlib
rows=list(csv.DictReader(open('results/experiments/arrival_pressure_20261002-230513/raw_runs.csv',encoding='utf-8-sig')))
print([r for r in rows if r['取值']=='is0.70×f6'])"

# grid 量具自身的夹具（G1–G6 + 配对 seed）
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -m unittest experiments.test_grid -v
```

## 已知未定位项（不影响 fixture 定义，影响后续解读）

1. **f4 的换电次数（15–16）系统性低于 f6（21–22.5）**，而 f4 明显更忙。
   可能是机队小 ⇒ 单机里程少，也可能是"任务根本做不完 ⇒ 没机会触发换电"。
   这条会直接影响加风/加能耗后的读数解释 ⇒ **未定位，不得写进结论**。
2. `is1.00×f4` 超时率 0.291 高于 `is0.85×f4` 的 0.245 —— **非单调**。两重复差 0.044，
   提示 n=2 定不出形状，不能据此说"低负载更差"。
3. `completion_rate` 的分母是 `total_generated_tasks`（`frontend/environment.py:840-842`），
   且 `timeout_rate` 的分母是 `total_completed_tasks`（:921）⇒ **完成 ≠ 按时完成**。
   因此这三档一律以 `on_time_rate / timeout_rate / mean_delay / unfinished_at_end` 为主 KPI，
   不再引用 completion_rate 判压力。
