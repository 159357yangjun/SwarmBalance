# 归因 (iii) 二分读数（2026-10-08，第四十一笔）

方法：`git worktree add --detach <tmp> <commit>` ⇒ **主工作树全程未碰**；每个点用同一 venv 解释器跑
`python -m experiments.runner --preset experiments/presets/e0_baseline.yaml --output-root <TMP>`（6 run，约 17s/点）。
比较范围与门自身一致 = `list(raw_runs header)[10:]`（24 列 × 6 行 = 144 格），`耗时秒` 不在其中。

| 生成的 commit | 该点 manifest 自录 git_commit | vs OLD `e0_baseline_20261002-235335` | vs NEW `e0_baseline_20261008-210053` |
|---|---|---|---|
| `c0af7c7` | c0af7c7 | **0 格** | **12 格** |
| `3f80a17` | 3f80a17 | **0 格** | **12 格** |
| `f1e3a5b` | f1e3a5b | 12 格 | **0 格** |
| `9b1cd15` | 9b1cd15 | 12 格 | **0 格** |

参照物本身的可复现性（同命令重跑第二遍）：NEW vs NEW2 = 比较区间内 **0 格**差，只有 `耗时秒` 6 格漂。
OLD vs OCT3（两批历史产物互比）= **0 格**差，同样只有 `耗时秒`。

⇒ 差异集合稳定、方向一致：**翻转发生在 `c0af7c7 → 3f80a17`**。

## 但那两个提交之间没有行为代码改动

`git show 3f80a17 -- frontend/environment.py` 的 9 增 6 删全部落在两处 docstring：
`a_star_pathfinding` 与 `heuristic` 被标为 LEGACY_REFERENCE_ONLY。其余三个钉住文件该笔未触碰。
`frontend/route_planner.py` 在两笔间哈希相同（`e13274b96b71`）。

## 因此本轮结论只能写到这一步

「只改注释的提交前后，产物在两个等待时间指标上系统性不同（12 格）」——机制未定。
候选 (i) 已被盘上事实支持为**方法论缺陷**：`experiments/reproducibility.py:35 SHARED_SOURCES` 不含
`frontend/route_planner.py`（三个产物的 pin 键集均 `has_route_planner=False`），
所以"pin 没变"从来不能证明"行为没变"，Phase 1A 抽出去的正是路径规划本体。

不得据此宣布"新旧不等价是预期后果"（批文里那条候选结论的前提是定位到合理行为变更，前提未成立）。
