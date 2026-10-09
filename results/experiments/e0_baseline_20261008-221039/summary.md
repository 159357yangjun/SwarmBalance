# 一键实验摘要

- 预设：E0 baseline（结构修改前基线 · C-1/C-2 配对 seed）
- 成功运行：6/6
- 生成时间：2026-10-08 22:10:56
- 公平性：同一实验条件下不同算法使用相同 Seed。
- 隔离性：每次运行使用独立 simulation.json 副本，未改写主配置。

## 结果解释边界

- `algorithm_comparison.csv` 是多次运行均值；`algorithm_comparison_stats.csv` 进一步给出标准差和中位数。
- `paired_ga_vs_greedy.csv` 只比较相同 Seed 下的描述性差异，不替代统计显著性检验。
- 若某指标不支持主推方案更优，应在结项报告中如实呈现，不应倒推结论。

## 输出文件

- raw: `raw_runs.csv`
- reproducibility: `reproducibility.json`
