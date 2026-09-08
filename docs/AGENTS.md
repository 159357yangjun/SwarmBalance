# AGENTS.md — AI 协作硬约束（必读）

> 本文件对 AI 代理有**最高约束力**。任何 AI（含 IDE 内置助手）修改本项目前，
> 必须先读本文件与《项目模块划分.md》。违反约束的修改一律视为错误，应撤销。

---

## 一、项目四模块（只能改被授权的模块）

| 模块 | 目录 | 关键文件 |
|---|---|---|
| ① 仿真环境 | `simulation/` 环境核心 + `config/` | environment.py、drone.py、task.py、charging_station.py、no_fly_zone.py、data_source.py、tools/osm.py |
| ② 调度算法 | `scheduling/` + `scheduling/greedy/` | pso_scheduler.py、ga_scheduler.py、chain_codec.py、ortools_scheduler.py |
| ③ 强化学习 | `backend_wx/pymarl-master/` | env_drone.py、algs 配置 |
| ④ 可视化评测 | `console/` + `app/evaluate_metrics.py` + `results/` | server.py、index.html、metrics_schema.py、plot_compare_metrics.py |

## 二、AI 的硬性禁令（无条件遵守）

1. **禁止擅自移动 / 重命名 / 删除文件或目录**（包括"顺手清理死代码"）。除非用户明确指示，且先在 git 提交前确认。
2. **禁止改动任务模块之外的文件**。若任务只涉及模块②，不得碰 ①③④ 的任何文件。
3. **禁止修改指标字段**。`metrics_schema.py` 的列定义、`get_statistics()` 的 key 是跨模块红线，改之前必须先全局评审并在 PR 说明。
4. **禁止改动物理口径**。1 env-step=1 秒、距离用米、耗电公式 `base×dist×(1+penalty×载重比)`、低电量阈值 0.2、换电 180 秒，这些是实验一致性的根基。
5. **禁止"顺手重构"**。即使发现代码可优化，未获授权也不得重构。可写入《项目自评报告.md》的改进清单，等用户决策。
6. **禁止删除注释 / 文档**。文件头部的 `[模块 X]` 归属标记、docstring、README 说明是协作的契约。

## 三、AI 修改的标准流程

1. 明确任务属于哪个模块；
2. 只读 + 只改该模块的文件；
3. 跨模块改动 → 停下，向用户说明"这涉及模块 X 和 Y"，等确认；
4. 改完跑最小回归（`python -m unittest tests.test_chain_codec tests.test_no_fly` 或短评测）；
5. 不自行 git commit，除非用户明确说"提交"。

## 四、文件头部归属标记（示例）

每个源码文件头部应有如下标记（缺失时按目录归属判断）：

```python
# ============================================================
# [模块 ① 仿真环境] 本文件属「仿真环境」模块
# 职责：XXX
# 禁止：修改指标字段 / 物理口径；不得被其他模块直接 import 内部实现
# ============================================================
```

## 五、常见违规示例（务必避免）

- ❌ 修算法 bug 时"顺手"改了 environment.py 的耗电公式
- ❌ 觉得 `nest.py` 是死代码，直接删了
- ❌ 在 evaluate_metrics.py 里新加一个 CSV 列，没改 metrics_schema.py
- ❌ 把 `simulation/` 整个目录重命名为 `simulation/` 而不更新所有 import
