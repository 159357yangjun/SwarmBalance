# #69-H2 设计稿：行进线段消费谓词（纸面定义，待审后动码）

基线 c22802f。遵主控方法约束③：**先交纸面定义审批，通过前不改 environment.py、不动夹具**。本轮只出此文档。

## 1. 要解决的具名残余（来自 faceoff 一手数据）
当前已提交规则 `_consumed_prefix_len`（后缀 + 服务前缀）有两类错判，纯几何 `dist(end,prev[0])≤1m` 各修一半又引入另一半：
- **假阳性**（seed102 9 例）：mid-flight re-route，dest/source 从队首消失但无人机停在离它 85~961 m 处 ⇒ 旧"服务点消失即消费"误判为送达；几何能修（终点≠该点）。
- **漏计**（seed40907 t=521/572/659…）：一步内先弹普通 waypoint 再弹 dest，队首是 waypoint ⇒ 纯几何"遇首个不匹配就停"在 waypoint 处停住，漏掉更深的服务点；旧后缀规则反而对（curr 是 prev[k:] 后缀）。
- **多计反向**（seed40907 t=79/169…）：同帧追加致 curr 非后缀 ⇒ 旧后缀规则 k=0 漏，几何对。

⇒ 需要一把**同时**覆盖这三类的谓词，证人必须是几何位移事实，不能只看 curr 形状或只看队首一点。

## 2. 谓词定义（拟）
记本步无人机起点 `S = prev_positions[i]`、终点 `E = (drone.x, drone.y)`，弹出前航线 `prev`、弹出后 `curr`。

**候选消费数 k**：沿 prev 从队首向后扫描，累计"被本步路径经过"的航点，直到遇到第一个**未被经过且仍在 curr 队首**的航点为止。逐点判定：
```
passed(p) := dist_point_to_segment(p, S, E) <= TOL
```
其中 `dist_point_to_segment` 是点到线段 [S,E] 的最短距离（标准投影式，垂足在线段内取垂距、否则取较近端点距）。k = 满足 passed(prev[j]) 的最大前缀长度（连续，遇第一个 not passed 即停）。

**为什么这能三类全覆盖**：
- task_44 / t=79：dest 恰在 S→E 路径上（终点就是它）⇒ passed=True ⇒ 计入（修好"同帧追加漏计"）。
- 9 例 re-route：dest 不在 S→E 线段附近（无人机侧向改道去机巢，垂距 >> TOL）⇒ passed=False ⇒ 不计（修好假阳性）。
- t=521 多点弹：waypoint 与 dest 都落在同一条直线推进的 S→E 上 ⇒ 连续 passed ⇒ k 覆盖到 dest（修好几何"遇 waypoint 停"的漏计）。

## 3. 容差取值来源（约束要求引用真源或明写为何不同）
- **TOL := 1.0 m**，直接引用 `frontend/route_planner.py:160` 的 `euclidean(current, goal) < 1  # Close enough to goal` —— 这是系统里"算到达"的唯一既有几何定义，消费判据必须与之同尺，否则又是两套到达定义（#69-B/C1 反复消除的那类跨层不一致）。
- 用 `<= 1.0` 对齐 planner 的 `< 1`（边界差 1e-9 无实际样本，取闭区间只为数值稳健；若审为应严格 `<` 我改）。
- 不自造新容差值。

## 4. 与 curr 的一致性兜底（防"途经但没真弹出"）
仅 passed 不够——还要保证这些点确实离开了航线：加约束 `curr == prev[k:]` 或 `curr` 是 `prev[k:]` 去掉若干尾部后再追加（re-route 追加场景）。具体：
- 若 `curr == prev[k:]`：正常弹出 k 个，k 成立。
- 若 curr 不是 prev[k:] 后缀（同帧追加 nest）：只要 `prev[:k]` 全部 passed 且 `prev[k]`（若存在）未 passed，接受 k。
- 反例护栏：某点 passed 但它仍出现在 curr 里（异常）⇒ 截断在该点之前。

## 5. 验收三件（缺一不可，均实测非推断）
(a) seed102 九例 re-route 全判回 k=0；
(b) seed40907 冻结回放含 avg_delay=2.802632 逐字不变；
(c) t=521（多点弹含 waypoint 头）与 t=79（同帧追加）双向分歧样本各归其位。
三面**先红后绿留档**：先在旧规则(9b1cd15)上跑 (a)(c) 对应夹具，**实测报红**（旧规则 (a) 会误判 k≥1、(c) t=79 会 k=0），存档原始输出；再落 H2 转绿。禁止拿推断当红、禁止改夹具迁就规则。

### 5.1 (b) 基线的一手来源（把"冻结证人"从口头变可复算断言）
`avg_delay=2.802632` **不是对话里的口头读数**，有仓内一手产物，且已入库、与工作树逐字节一致：
- **源文件**：`docs/取证输出/c1_paired_replay_f654587_fixed.json`（git 跟踪，引入于 `aa75b5b #69-C1`，HEAD blob=`aecc5e6…` 与盘上 hash-object 相同）。
- **字段路径**：`metrics.mean_delay.before = metrics.mean_delay.after = 2.802632`，`metrics.mean_delay.delta = 0.0`。同文件另钉 `seed=40907 / steps=1200 / algorithm=greedy`、`timeout_rate=0.052632`、`completed=38`、`cleanup_completion.after=0`。
- **它记录的是哪一次**：`baseline_before=f654587 → after=working-tree #69-C1` 的配对回放里 mean_delay 保持不变 ⇒ 2.802632 是 **C1 提交态**的读数。
- **第二证人（独立复算）**：本轮把 environment.py stash 回 HEAD（含 H1′ 9b1cd15 的后缀+服务前缀规则），用生产入口 `experiments/worker.py --algorithm greedy --seed 40907 --episode-steps 1200` 实测 `平均时延=2.8026315789473686`，与 JSON 值在 6 位小数逐字一致 ⇒ 该基线在当前提交态可复现、未随后续 commit 漂移。
- **可复算门**：`console/test_h_b_baseline_provenance.py` 读上述 JSON 的 `metrics.mean_delay.{before,after}` 并断言二者相等且 =2.802632（六舍五入），同时校验文件 git 跟踪状态——把"冻结证人"钉成断言，而非引用文档正文里的数字。

> ⚠ 由此得出一条必须写清的口径修正：H2 线段谓词实测把 seed40907 avg_delay 变成 2.776316，**不等于**"旧基线是假阳性产物"。相反，2.802632 由 C1 提交态与 HEAD 两个独立时刻复算得到；是 H2 自身在 6 处 `prev==curr`（航点仍留在航线、未弹出）时因"途经即算"提前计账把它推离基线（见本轮具名证据）。**(b) 基线成立**，无需重定；不满足 (b) 的是谓词形状，不是参照数。

## 6. 风险与自限
- **单步运动模型已核实（不再是假设）**：`drone.py:355-360` 每步只朝 `scheduled_position[0]` 走一段直线位移（`x += dx/dist*max_distance`），一步内不折线 ⇒ 用线段 [S,E] 判"途经"在几何上成立。若将来 update 改成多段/曲线，passed 需改用真实轨迹采样——届时另议。
- 若实现后仍有两面不能同时过的样本 → 停下交具名证据，不改夹具。

## 7. 请你审的点
1. TOL 用 planner 的 1m 闭/开区间取舍；
2. §4 curr 一致性兜底的严格度是否够（会不会把合法 re-route 也算进去）；
3. §6 单步运动模型是否要先补一次取证再定 passed 的实现形态。
批准后我再动 environment.py + 夹具。
