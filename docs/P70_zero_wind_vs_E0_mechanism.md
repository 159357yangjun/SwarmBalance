# P70 · zero-wind ≠ E0 那 12 格差异的机制（2026-10-08，第四十二笔）

## 0. 一句话

两个等待时间指标的系统性差异来自 **`d6b6c0b`（#69-B）把"取货时刻 `load_time`"的判据从「标签＋坐标双判据」改成「只有标签一条」**；
它是**守恒的重新归类**（同一批任务、同样的完成/超时结果，只是把一段时间从"送达段"挪进了"装载等待段"），
因此等价门相对 10-02/10-03 两批 E0 的不等价是**修正口径的正确后果**，不是缺陷、也不是回归。

## 1. 边界是怎么定下来的（以及我上轮报的那个点是错的）

上轮我用 `git rev-list a298d6d..d19d647 -- <四个钉住文件>` 得到候选序列，报出"翻转点在 `c0af7c7 → 3f80a17`"。
**那个边界是我自己造出来的假阳性**：`rev-list` 默认按**拓扑序**返回，而这段历史里混着几条日期更晚的提交
（`f1e3a5b` #65 产于 10-05，却排在 10-03 的 `3f80a17` 前面）。我把"顺序中的下一个"当成了"时间上的下一个"。

按提交日期重排后，实测形状是：

| commit | 日期 | 产物形态 |
|---|---|---|
| `c0af7c7` | 10-03 23:15 | OLD 形（vs 旧基线 0 差） |
| `3f80a17` | 10-03 23:56 | OLD 形（vs 旧基线 0 差） |
| `f1e3a5b` | 10-05 | NEW 形（vs 新基线 0 差） |
| `9b1cd15` | — | NEW 形 |

⇒ 真边界在 **`3f80a17`(10-03) → `f1e3a5b`(10-05)** 之间，其间唯一的生产改动是 **`d6b6c0b` #69-B**。
`3f80a17` 只改 docstring 这件事从头到尾都是对的——它本来就不该是翻转点。

⚠ 教训：**用 rev-list 定顺序时必须显式要求按日期**，拓扑序在有分支/回填的仓库里不等于时间序。

## 2. 机制：一行判据

`frontend/environment.py` 里航点弹出时给 assignment 记取货时刻。两处都按本轮实测的行号贴（旧侧行号取自 `git show a298d6d:frontend/environment.py`）：

```python
# ≤ a298d6d（旧）— environment.py:1152-1156
if (assignment.get('load_time') is None
        and assignment['task'].get_source() == source_pos):   # 标签 + 坐标 双判据
    assignment['load_time'] = self.current_time

# ≥ d6b6c0b（新）— 当前 environment.py:1199-1200
if assignment.get('load_time') is None:                        # 只有标签一条
    assignment['load_time'] = self.current_time
```

⚠ 这两处**不按绝对行号引用**，用上面的代码片段自证：本仓已经第七次被挪行咬到（见 README §行号引用口径）。

为什么要改（#69-B 的原话）：A* 以 <1 m 容差终止 ⇒ detour 路线的末点常常**不精确等于** `task.source`，
双判据并存时那条赋值**永远不触发** ⇒ 无人机没被记过"取货"，却在 dest 弹出时算作送达。

这两个指标共用同一个 `load_time`：

```python
assignment_to_load_wait = max(0, load_time - assigned_time)     # 「从分配到实际装载上机等待时间」
delivery_time           = max(0, completion_time - load_time)   # 「从上机到送达平均时间」
```

所以 `load_time` 一旦从"从未赋值→兜底成 `assigned_time`"变成"在服务航点真正弹出那一刻赋值"，
前者必然增大、后者必然减小，且**增量相等**。

## 3. 一手读数（六格完全镜像，单位秒）

| 格 | 从分配到装载等待 OLD→NEW | 从上机到送达 OLD→NEW | Δ 是否互为相反数 |
|---|---|---|---|
| C1/rep1 | 46.73 → 76.91 (+30.18) | 152.57 → 122.39 (−30.18) | ✓ |
| C2/rep1 | 42.72 → 78.57 (+35.85) | 145.95 → 110.09 (−35.85) | ✓ |
| C1/rep2 | 55.04 → 72.66 (+17.63) | 138.19 → 120.56 (−17.63) | ✓ |
| C2/rep2 | 51.57 → 67.01 (+15.44) | 136.13 → 120.69 (−15.44) | ✓ |
| C1/rep3 | 50.93 → 72.40 (+21.47) | 140.48 → 119.01 (−21.47) | ✓ |
| C2/rep3 | 57.15 → 74.40 (+17.25) | 136.00 → 118.75 (−17.25) | ✓ |

同一批里其余列全部相同：`超时率`、`完成任务数`、`生成任务数` 三列六格逐字相等
⇒ **没有任何任务因此变好或变坏**，只是延迟在两个桶之间重新归类。总账不变：
`generation_to_completion = generation_to_assignment + assignment_to_load + load_to_delivery` 仍然闭合。

## 4. 磁盘缓存为什么**不是**成因（先取证再改期望，没有按原计划删缓存）

裁定要求"先冻结 OSM 磁盘缓存这个混淆源再做下一步消融"。查下来分两层：

**(a) 混淆源确实存在，结构上是真的。**
`frontend/tools/osm.py:250 _CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / ".osm_cache"` 与
`frontend/environment.py:34 _PATH_CLEAR_DIR = Path(__file__).resolve().parent / "data" / ".osm_cache"`
都按 `__file__` 解析。本轮实测：在一个临时 worktree 里 import 该模块，打印出的 `_CACHE_DIR` **指向主仓目录**
⇒ 不同 commit 的 worktree 会落到同一份缓存，跨代复用是真的。
开关有两个：`SWARM_BALANCE_OSM_CACHE`（解析缓存）、`SWARM_BALANCE_PATHCLEAR_CACHE`（通行判定缓存）。

**(b) 但它解释不了这 12 格，两条独立反证：**
1. **OLD vs OCT3 逐格相同**，而两者之间隔着 `c0af7c7` —— 正是 A\* 本体搬家的那一笔。若缓存能改变判定，
   这一对最该先表现出不一致。
2. **仿真几何桶首写于今天 21:23**（我这轮第一次跑之前树里根本没有这个文件），
   而 OLD 那批产于 10-02 ⇒ OLD 不可能读到今天的桶内容。
   现算三个 commit（`c0af7c7` / `3f80a17` / HEAD）的桶指纹同为 `90753a7a442897a4` ⇒ 几何本身也没变过。

⇒ 结论：缓存是**潜在**混淆源（值得隔离），但不是本次差异的成因。消融因此不必执行，
我没有为了走流程而删一份 19 MB 的共享缓存（那只会让下一次跑变慢，不产生任何新读数）。

## 5. 顺带查出的一件独立事项（登记，不在本轮修）

仿真几何桶 `pathclear-90753a7a442897a4.pkl` 里有 **2 条合成坐标键**：`((0,0),(1,0))`、`((0,0),(2,2))`，
来自避障探针而不是仿真任务流（真实键的坐标量级在 3.5e5 / 3.4e6）。
值都是 `True`、对仿真无害（那些点对不会在真实回合里出现），但**测试写入与仿真持久状态共用同一个命名空间**这个形状本身要记：
将来若有探针用与仿真重合的坐标写不同判定值，就会串味。属新范围，待裁（残余边界 iv）。

## 6. 这对既有结论的影响

- `docs/P70_E1_equivalence_gate_ablation.md` §3 那句"[夹具失效]⇒不可判定"、§7 补的"生产侧差异未归因"，
  现在都由本文给出因果 ⇒ 参照物过期是真、但红的主因是 #69-B 的口径修正。
- `docs/模型真实结构修订.md:20` 那句"作废为不可判定"**本轮不改写**：它的定性已经落后两次实测，
  改成什么属于对外口径/作者权事项，交回裁定。
- 等价门的参照物已换成 `e0_baseline_20261008-221039`（pin 含 `frontend/route_planner.py`，17/17 相符）。
  门绿表示的是"**当前树上 zero-wind 自洽**"，不再表示"与 E1 之前的世界等价"。

## 7. 复算

```bash
# 边界（必须按日期，不要信拓扑序）
git log --format="%h %ad %s" --date=format:"%m-%d %H:%M" a298d6d..HEAD -- frontend/environment.py

# 机制那一行的两种形态
git show a298d6d:frontend/environment.py | sed -n '1144,1156p'
sed -n '1195,1202p' frontend/environment.py

# 六格镜像（比较区间 = 门自己的 keys[10:]）
python - <<'PY'
import csv, io
def rows(p): return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))
A = rows("results/experiments/e0_baseline_20261002-235335/raw_runs.csv")
B = {(r["取值"], r["重复"]): r for r in rows("results/experiments/e0_baseline_20261008-221039/raw_runs.csv")}
for r in A:
    s = B[(r["取值"], r["重复"])]
    print(r["取值"], r["重复"],
          round(float(s["从分配到实际装载上机等待时间"]) - float(r["从分配到实际装载上机等待时间"]), 2),
          round(float(s["从上机到送达平均时间"]) - float(r["从上机到送达平均时间"]), 2),
          "超时率同" if r["超时率"] == s["超时率"] else "超时率异")
PY

# 桶指纹（三个 commit 应同为 90753a7a442897a4）
#   见 docs/取证输出/p70_p6_attribution/E_bucket_fingerprint_replay.md
```
