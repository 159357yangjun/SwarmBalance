# Phase 1B-2 设计 —— ETA-aware scheduling（reachability 分量）

状态：**设计已批准（2026-10-04），进入实现**。§F 两问已由用户点定：公式取 slack 形式、
H0 改写为"变化幅度与 1B-1 同量级（≤4 单任务）"；权重默认 0.0 亦被采纳。
本文所有数字均为本轮现测（复算命令见 §E），不是推断。

---

## 0. 用户判定 → 本设计的约束

| 判定 | 落地为 |
|---|---|
| ETA 放 provider 层，加 `eta(a,b,speed)` | §A |
| 只动 Greedy，不动后端 ⇒ GA 保持阴性对照 | §C 实验矩阵的"另一面必须逐位不变" |
| 新增独立分量 `reachability`，不合成 slack | §B |
| 不改任何已有分量的计算方式；权重=0 可退化为基线 | §B.4 + 门 G11 |

---

## A. provider 接口变更（新旧对比）

### A.1 现状（1B-1 交付）
```python
class EuclideanRouteCostProvider:        # frontend/route_cost.py:30
    name = "euclidean"
    def distance(self, a, b) -> float            # :39
    def batch(self, origin, targets) -> List[float]   # :43
    def stats(self) -> Dict[str, int]            # :47

class PlannedDistanceRouteCostProvider:  # :51
    name = "planned_distance"
    def distance(self, a, b) -> float            # :86  走 RoutePlanner，自带 _cache
    def batch(self, origin, targets)             # :115
    def stats(self)                              # :118
```
类型上就限定了"provider 只提供距离"——这句注释（`route_cost.py:54`）在 1B-2 要**改写**，
不能留着变成假注释。

### A.2 1B-2 新增
```python
def eta(self, a, b, speed_m_per_s: float) -> float:
    """从 a 到 b 的预计耗时，单位 = env-step（当前 STEP_SECONDS=1.0 ⇒ 数值等于秒）。"""
```
两个实现各自定义，**不允许共用默认实现**（否则两面在 ETA 上退化成一个，1B-2 就没有对照了）：

| 实现 | eta 返回 | 与 distance 的关系 |
|---|---|---|
| `EuclideanRouteCostProvider` | `_euclid(a,b)/speed` | 恒等：ETA_euclid ≡ distance_euclid/speed |
| `PlannedDistanceRouteCostProvider` | `self.distance(a,b)/speed` | 复用同一份 `_cache` ⇒ **不增加一次 A\* 调用** |

关键推论（这是 1B-2 与 1B-1 的本质区别，必须写清）：
`eta` 是 `distance` 的**单调仿射函数**（同除一个 speed）。⇒
- **候选集内部的相对排序**：ETA 与 distance 完全一致 ⇒ 单看 proximity/reachability 的"组内谁更好"，1B-2 ≈ 1B-1。
- **跨候选集/跨机型的可比性**：`remaining_time` 是绝对量、speed 有机型差异（实测 fleet 只有 `{14.0, 20.0}` 两档）⇒ reachability 引入了 distance 没有的信息。
⇒ **所以 1B-2 的判别式不能是"排序变了"**（那和 1B-1 重复），必须是"同一个候选在 euclid 面与 planned 面的 reachability 值不同，且该差值进入总分"。G10 按此设计。

### A.3 兼容性
`make_provider(kind, planner=None)`（`route_cost.py:124`）签名不变；未知 kind 仍抛 `[UNKNOWN_COST_PROVIDER]`。
Greedy 取数点从 3 处增至 4 处（多一处读 `cap['speed']`），全部保持 `provider is None` 时走原欧氏分支。

---

## B. reachability 分量的数学定义与归一化

### B.1 先否掉用户给的原始形式
提议：`reachability = ETA / remaining_time`。实测（C-1 seed=40901 初始观察空间，12 个真任务，drone_0 speed=20）：

| 量 | min | P25 | P50 | P75 | max |
|---|---|---|---|---|---|
| `remaining_time` (s) | 281.0 | 475.9 | 584.0 | 785.8 | 897.0 |
| `ETA` drone→pickup (s) | 38.0 | — | 59.0 | — | 80.3 |
| **比值 `ETA/rt`** | — | — | **0.1074** | — | **0.2857** |

⇒ 比值**全域远小于 1，且 >1 的比例 = 0%**。原因在 deadline 生成公式里：
`_sla_seconds() = distance/14.0 + 420 + weight×24`（`frontend/task.py:520-527`，配置 `config/simulation.json:72-74`）
——那个常数 **420 s 就是 sla_base_seconds**，它比航段项大一到两个数量级。
⇒ 裸比值把 ~420 s 的常数摊进了分母，**它实际测的是"SLA 常数有多宽松"，不是"这架机赶不赶得上"**。
这条必须在实现前说明，否则会做出一个"有实现、无信息"的分量（正是总纲 §17.0 反玩具感清单要拦的形状）。

### B.2 采用的形式（保留"独立分量"这一判定，只换分子分母的口径）
```
slack       = remaining_time − ETA                 # 还能等多久 vs 我要飞多久
reach_raw   = clamp(slack / REF_SLACK, 0.0, 1.0)   # ∈[0,1]，越大=越从容
score      += W_REACH * (1.0 − reach_raw)          # 越紧张的任务越该被就近快机接走
REF_SLACK   = 300.0                                # 与 matching.speed_match 的 urgency 分母同值
```
为什么这样而不是裸比值：
1. **量纲对齐现有分量**。`compute_match` 输出 ∈[0,1]、`proximity` ∈[0,1]，新分量也必须 ∈[0,1]，
   否则 `MATCH_WEIGHT/proximity` 的既有平衡会被一个尺度不同的量劫持（登记表 M5 同族教训：
   分子步/分母秒只在 time_step=1 时凑巧一致）。
2. **`REF_SLACK=300` 不是我拍的数**：`matching.py:44` 的 `urgency = max(0, min(1, 1 - remaining_time/300.0))`
   已经在用 300 做时限归一。复用同一个常数 ⇒ 新分量与既有时效分量同尺度，且日后能解释
   "两者是否重复计分"这件事（S2 已证 deadline 只进 greedy 打分）。
3. **`slack` 而非 `ratio`**：比值在 rt→0 时爆炸、rt 很大时趋 0，分布偏态严重；
   slack 减法是线性平移，clamp 后有界。

⚠ 这里我**偏离了用户字面写的公式**，但保留了她的三条结构性判定（独立分量、provider 层、不动后端）。
若坚持字面 `ETA/rt`，实现只需换 B.2 那一行；代价见 B.1 的实测。**请点定二选一。**

### B.3 边界与退化（必须先想好的三种输入）
| 输入 | 出现条件 | 处理 | 理由 |
|---|---|---|---|
| `remaining_time = inf` | padding 任务给 `-1.0`（`environment.py:1604`）已被过滤；真实任务无 deadline 时为 inf（`:1544`） | reachability 取**中性 0.5**，不参与奖惩 | 不能因"没时限"被判最优或最差 |
| `slack < 0`（注定赶不上） | 实测本轮 0%，但 SLA 调严（S2 Strict=300/18）后会出现 | clamp 到 0 ⇒ 该任务 reachability 得分最高（最该被快机抢） | 这是想要的行为，但要单独计数并打印，否则"有多少单已经注定超时"看不见 |
| `speed ≤ 0` | 配置异常 | 抛错，不兜底 | 静默兜底会让 ETA 变 0 ⇒ 全体 reachability 相同 ⇒ 分量悄悄失效 |

### B.4 权重与退化保证
```python
REACH_WEIGHT = float(_GREEDY_CFG.get("reach_weight", 0.0))   # 默认 0 ⇒ 逐字退回 1B-1 后的基线
```
- **默认 0.0**，不是 0.4。理由：约束要求"权重=0 可退化为基线"，而"基线"必须是当前签过字的行为；
  若默认 0.4，则本次改动本身改了生产行为，Gate B（零漂移）当场失效。
- 实验面通过 `SWARM_BALANCE_ROUTE_COST` 之外**再加一个环境变量**注入权重（沿用 1B-1 的进程级注入套路），
  不进 `config/simulation.json` 的默认值。
- 建议实验取值：`{0.2, 0.4}` 两档（0.4 = 与 `DISTANCE_WEIGHT` 同权，便于横向解读）。
  **本轮只做 0.4 一档的主实验**，0.2 作为敏感性附赠；不做网格扫描（那是 S1/S2 的方法，此处样本不够）。

### B.5 与"不改已有分量"的一致性
`_score_task` 现有形状（`scheduler.py:197`）：
```python
return MATCH_WEIGHT * match_score + DISTANCE_WEIGHT * proximity
```
改为：
```python
return MATCH_WEIGHT * match_score + DISTANCE_WEIGHT * proximity + REACH_WEIGHT * reachability
```
`match_score`、`proximity` 的计算一字不动；`REACH_WEIGHT=0` 时表达式与原来**代数等价**
（这是 G11 要断言的：权重 0 的两面 KPI 必须逐位相同）。

---

## C. 实验矩阵与产出格式

### C.1 主实验（与 1B-1 同构，同格式，可直接横向比）
| 维度 | 取值 |
|---|---|
| fixture | C-1, C-2（与 e0/S1/S2/1B-1 同一份定义） |
| algorithm | greedy（实验面）、ga（**阴性对照面**，必须逐位不变） |
| seed | 40901, 40902, 40903 |
| provider | euclidean, planned_distance |
| reach_weight | 0.0（基线）, 0.4（实验） |

⇒ 格子数 = 2 × 2 × 3 × 2 × 2 = **48 worker cells**（1B-1 是 24）。
每个 cell 仍是"独立子进程 + 环境变量注入"，两面除被切变量外配置字节相同。

三组比较（每组都是配对差分，逐 seed，再汇总符号）：
- **M1 距离面**：`planned+0.4` vs `euclid+0.4` ⇒ 与 1B-1 同问题，看加了 ETA 后距离口径的影响是否放大。
- **M2 时间面**：`euclid+0.4` vs `euclid+0.0` ⇒ **纯 ETA 效应**（距离口径固定）。这一组是 1B-2 的新知识。
- **M3 交互面**：`(planned+0.4)−(planned+0.0)` 与 `(euclid+0.4)−(euclid+0.0)` 之差 ⇒ ETA 是否依赖距离口径才起作用。

KPI 列与 1B-1 完全相同（`metrics_schema.METRIC_COLUMNS` 里的 10 项），产物同名格式：
`docs/取证输出/phase1b2_paired_experiment.txt`。

### C.2 预注册假设（先看数还是先写？——先写，锁在本文件提交里）
- **H0（已按 §F 定稿）**：加入 reachability（W=0.4）后，greedy 核心 KPI 的变化幅度与 1B-1
  同量级 —— 以「完成任务数 |Δ| ≤ 4」为量化上界（1B-1 实测 |Δ| ∈ {1,2,3,4}）。
  超上界即触发 H1。~~原"逐值不变或 <1 单任务"~~ 已被 §B.1/B.2 的实测推翻并作废。
- **H1**：若完成率/超时率变化 ≥ 2 单任务，必须能追溯到具体一次评分改变。
  ⚠ **1B-1 的教训直接适用**：事件级归因需要每面独立 Random 实例，而 `scheduler.py:89` 的
  `random.random()` 消耗全局 RNG ⇒ 共享进程重放必然产生假分歧（缺陷 g，已记入总纲 §17.1）。
  1B-2 **不在生产 Greedy 里注入 Random**（那是行为改动）。因此本轮归因承重方式是：
  **L2 消融**（把 `REACH_WEIGHT` 置 0 ⇒ Δ 必须消失）+ **静态评分对照**（同一候选集、同一
  provider、只切权重，比较各候选的 `_score_task` 数值与 argmax；这条路径**不调用 Greedy、
  不消耗随机数** ⇒ 不受缺陷 g 污染）。放弃"episode 内首分歧步"这种事件级声称。

### C.3 门（继承 + 新增）
| 门 | 内容 | 判据来源 |
|---|---|---|
| G1–G4 | provider 通道两面各测 / 真被调用 / 判别式 / 未知 kind 报错 | 1B-1 已有，扩展到 `eta()` |
| G5 | 后端零引用 provider ⇒ GA 仍是阴性对照 | 已有，须扩到 `eta` 关键字 |
| G8 | planned 面的 `eta` 必须真的不同于 euclid 的 `eta`（防恒真证人） | 1B-1 新增，本轮复用 |
| G9 | 交叉对账用**本轮现算** witness，合法盲点只打印不拦退码 | 1B-1 新增 |
| **G10** | reachability **必须实际影响排序**：至少一个 cell 的 top-1 任务在 W=0.4 与 W=0 下不同 | 用户指定 |
| **G11** | `W=0` 时代数等价 ⇒ 同 seed 同 provider 两面 KPI 逐位相同（保护 Gate B 语义） | §B.4 承诺 |
| **G12** | 单位一致性：ETA 的时间口径必须与 `remaining_time` 同源。断言方式——把 `time_step` 改成 2.0，reachability 的 ETA 必须随之减半（若实现里偷偷用了"秒"而没除 STEP_SECONDS，这条会红） | 登记表 M5 同族缺陷 |

G10/G11 都要跑变异测试证明有牙（摘掉 `+ REACH_WEIGHT * reachability` ⇒ G10 红；
把 `reachability` 写成常量 0.5 ⇒ G10 红）。

### C.4 flip witness 升级（步骤 4）
1B-1 留下的两个缺陷在 1B-2 的处理：
- 缺陷 f（共享 provider 缓存）：**已修**，两面各独立实例。
- 缺陷 g（共享全局 RNG）：**不靠"独立 Random 实例"修**，因为那要改生产代码。
  替代方案 = witness 改为**纯静态评分对照**：给定一份真实候选集快照，直接调
  `GS._score_task(..., provider=X)` 两次（W=0 / W=0.4），全程不 `env.step`、不触发
  `accept_probability` ⇒ 无随机数消耗 ⇒ 两面严格可比。
  代价：witness 只能回答"这一步会不会换冠军"，不能回答"整局因此少/多了几单"——后者由 C.2 的 L2 消融承重。

---

## D. 风险与不做的事

| 风险 | 缓解 |
|---|---|
| reachability 与 `speed_match` 的 urgency 重复计时效（同一信息两遍） | 产物里印出两者的相关系数；若高度相关，如实登记"分量冗余"，不硬凑收益 |
| `REF_SLACK=300` 是借用别人家的常数，未必适配 ETA 尺度 | 由 G12 + B.1 的现测分布背书；并在报告里给出"若改成 X 会怎样"的一句话 |
| 48 cells 时长：GA 单格 18–86 s ⇒ 约 25–40 分钟 | 与 1B-1 同法后台跑；门默认 skip，需显式开关 |
| 引入新权重 = 新的敏感性面 | 本轮只报 0.4 主档 + 0.2 附档，**不宣称找到最优权重** |

明确不做：不改后端 ETA、不把 `current_battery` 接进 range（属 1B-3）、不动 SLA/swap 默认值、
不加依赖、不 push、不出包。

---

## E. 复算命令（本文每个数字都能翻开）
```bash
# B.1 的 remaining_time / ETA 分布（C-1 seed=40901 初始观察空间，drone_0）
SWARM_BALANCE_SIM_CONFIG=config/simulation.json python - <<'PY'
# Environment.reset(seed=40901) 后读 unassigned_tasks[i]['remaining_time']，
# 用 PlannedDistanceRouteCostProvider(env.route_planner).distance(d0.pos, t.source)/d0.speed
PY
# deadline 公式与常数：frontend/task.py:520-527；config/simulation.json:72-74
# urgency 的 300 分母：frontend/matching.py:34-46
# 机型 speed 档位实测 = {14.0, 20.0}；STEP_SECONDS=1.0：frontend/drone.py:22
# 现有打分形状：frontend/greedy/scheduler.py:157-197
```

---

## F. 拍板结果（2026-10-04 用户确认，本文件不再改动此节）
1. **公式**：采纳 `clamp((remaining_time − ETA)/300, 0, 1)`（slack 形式）。裸比值否掉的理由是
   B.1 实测——deadline 生成式里 420 s 常数主导，比值测的是 SLA 宽松度而非赶得上与否。
2. **H0**：改为「加入 reachability(W=0.4) 后，greedy 核心 KPI 的变化幅度与 1B-1 同量级
   （完成任务数 |Δ| ≤ 4）」。**不是**"不变"——slack 形式组内有方差，拿已知会变的量预言不变是自欺。
   H1 保持：若 |Δ| > 4，须由 L2 消融（W→0 时 Δ 消失）+ 静态评分对照解释，不得引用 episode 内事件链。
3. **权重默认 0.0** 被采纳（用户原话："这个我没想到"）⇒ 本次实现不改生产默认行为。
