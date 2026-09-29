# 一键实验摘要

- 预设：标准结项实验
- 成功运行：68/68
- 生成时间：2026-09-29 12:44:56
- 公平性：同一实验条件下不同算法使用相同 Seed。
- 隔离性：每次运行使用独立 simulation.json 副本，未改写主配置。

## 核心算法对比

- **贪心调度**：完成率 100.00%，超时率 5.33%，无人机利用率 49.87%，空载率 49.39%，机巢周转率 0.9600。
- **OR-Tools**：完成率 100.00%，超时率 8.00%，无人机利用率 50.68%，空载率 44.80%，机巢周转率 0.8600。
- **GA**：完成率 100.00%，超时率 7.67%，无人机利用率 50.84%，空载率 44.98%，机巢周转率 0.8600。
- **PSO**：完成率 100.00%，超时率 8.00%，无人机利用率 49.91%，空载率 44.69%，机巢周转率 0.8800。

## GA 与 Greedy 的配对 Seed 描述性比较

> 下表只做描述性比较，不等价于统计显著性检验；正的“平均改进”表示 GA 按该指标方向更优。
> 方向为「视运营目标」的指标不判优：它们的数值随容量配置同向变化（泊位变多则周转率与泊位利用率同时下降，而真实排队与完成率在改善），因此胜/平/负留空，避免被读成结论。

| 指标 | 方向 | Greedy 均值 | GA 均值 | 平均改进 | 相对改进率 | 胜/平/负 |
|---|---|---:|---:|---:|---:|---:|
| 完成率 | 越高越好 | 1 | 1 | 0 | 0.00% | 0/5/0 |
| 超时率 | 越低越好 | 0.0533333 | 0.0766667 | -0.0233333 | -43.75% | 1/2/2 |
| 从生成到完成总时间平均 | 越低越好 | 197.533 | 195.64 | 1.89333 | 0.96% | 3/0/2 |
| 无人机利用率 | 越高越好 | 0.498699 | 0.508413 | 0.00971436 | 1.95% | 2/0/3 |
| 空载率 | 越低越好 | 0.493942 | 0.449767 | 0.0441747 | 8.94% | 5/0/0 |
| 泊位利用率 | 视运营目标（不单向判优） | 0.0763057 | 0.0730539 | -0.0032518 | -4.26% | 不判 |
| 机巢周转率 | 视运营目标（不单向判优） | 0.96 | 0.86 | -0.1 | -10.42% | 不判 |
| 平均泊位排队等待 | 越低越好 | 0 | 0.2 | -0.2 | 0.00% | 0/4/1 |
| 总能量消耗 | 越低越好 | 13984.9 | 13800 | 184.911 | 1.32% | 3/0/2 |
| 总飞行距离 | 越低越好 | 168563 | 164124 | 4438.85 | 2.63% | 3/0/2 |

## 结果解释边界

- `algorithm_comparison.csv` 是多次运行均值；`algorithm_comparison_stats.csv` 进一步给出标准差和中位数。
- `paired_ga_vs_greedy.csv` 只比较相同 Seed 下的描述性差异，不替代统计显著性检验。
- 若某指标不支持主推方案更优，应在结项报告中如实呈现，不应倒推结论。

## 输出文件

- raw: `raw_runs.csv`
- algorithm_comparison: `algorithm_comparison.csv`
- task_scale: `task_scale.csv`
- task_density: `task_density.csv`
- nest_berths: `nest_capacity.csv`
- fleet_mix: `fleet_mix.csv`
- algorithm_comparison_stats: `algorithm_comparison_stats.csv`
- paired_ga_vs_greedy: `paired_ga_vs_greedy.csv`
- figure: `figures\algorithm_completion_rate.png`
- figure: `figures\algorithm_empty_load_ratio.png`
- figure: `figures\algorithm_timeout_rate.png`
- figure: `figures\algorithm_utilization.png`
- figure: `figures\sensitivity_fleet_mix.png`
- figure: `figures\sensitivity_nest_berths.png`
- figure: `figures\sensitivity_task_density.png`
- figure: `figures\sensitivity_task_scale.png`
