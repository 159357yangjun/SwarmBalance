# 两种行集合下的统计量差异（本文件由代码生成，禁止手改）

- 生成：`python results/row_set_delta.py --write`
- 核对：`python results/row_set_delta.py --verify`（不一致退出码 1）
- 行集合定义：`console/_rowsets.py` 的 `CORE` / `WITHDRAWN`（唯一一份）
- 被作废的产物：本目录 3 份派生表 + 12 张图，作废理由见同目录 `README.md`（R8）

| 表 | 统计量（列） | n(核心) | n(含撤除) | 均值(核心4) | 均值(含撤除10) | 差 | 两读数是否相同 |
|---|---|---|---|---|---|---|---|
| `combined_compare_metrics.csv` | Total Steps | 4 | 10 | 2000.000000 | 1349.600000 | -650.400000 | **不同** |
| `combined_compare_metrics.csv` | Completed Tasks | 4 | 10 | 57.500000 | 59.000000 | +1.500000 | **不同** |
| `combined_compare_metrics.csv` | Generated Tasks | 4 | 10 | 60.000000 | 60.000000 | +0.000000 | 相同 |
| `combined_compare_metrics.csv` | Completion Rate | 4 | 10 | 0.958333 | 0.983333 | +0.025000 | **不同** |
| `combined_compare_metrics.csv` | Generation-to-Assignment Wait | 4 | 10 | 13.098760 | 27.954504 | +14.855744 | **不同** |
| `combined_compare_metrics.csv` | Assignment-to-Loading Wait | 4 | 10 | 52.014217 | 52.565687 | +0.551470 | **不同** |
| `combined_compare_metrics.csv` | Loading-to-Delivery Time | 4 | 10 | 127.526316 | 106.900526 | -20.625789 | **不同** |
| `combined_compare_metrics.csv` | Avg Generation-to-Completion Time | 4 | 10 | 192.639292 | 187.420717 | -5.218575 | **不同** |
| `combined_compare_metrics.csv` | Max Generation-to-Completion Time | 4 | 10 | 467.500000 | 481.400000 | +13.900000 | **不同** |
| `combined_compare_metrics.csv` | Timeout Rate | 4 | 10 | 0.047716 | 0.139087 | +0.091370 | **不同** |
| `combined_compare_metrics.csv` | Average Delay | 4 | 10 | 2.655815 | 11.860659 | +9.204844 | **不同** |
| `combined_compare_metrics.csv` | Priority-1 Average Delay | 4 | 10 | 0.000000 | 9.705890 | +9.705890 | **不同** |
| `combined_compare_metrics.csv` | Priority-2 Average Delay | 4 | 10 | 0.000000 | 11.578571 | +11.578571 | **不同** |
| `combined_compare_metrics.csv` | Priority-3 Average Delay | 4 | 10 | 6.511075 | 14.640768 | +8.129692 | **不同** |
| `combined_compare_metrics.csv` | Total Energy Consumption | 4 | 10 | 13699.873415 | 61220.859198 | +47520.985783 | **不同** |
| `combined_compare_metrics.csv` | Berth Utilization Rate | 4 | 10 | 0.080725 | 0.080725 | +0.000000 | 相同 |
| `combined_compare_metrics.csv` | Nest Turnover Rate | 4 | 10 | 0.975000 | 0.975000 | +0.000000 | 相同 |
| `combined_compare_metrics.csv` | Avg Berth Wait Time | 4 | 10 | 0.000000 | 0.000000 | +0.000000 | 相同 |
| `combined_compare_metrics.csv` | Total Swap Sessions | 4 | 10 | 9.750000 | 9.750000 | +0.000000 | 相同 |
| `normalized_capability_scores.csv` | Completion Rate | 4 | 10 | 0.166667 | 0.666667 | +0.500000 | **不同** |
| `normalized_capability_scores.csv` | Generation-to-Assignment Wait | 4 | 10 | 0.891363 | 0.526753 | -0.364610 | **不同** |
| `normalized_capability_scores.csv` | Avg Generation-to-Completion Time | 4 | 10 | 0.180784 | 0.350955 | +0.170171 | **不同** |
| `normalized_capability_scores.csv` | Max Generation-to-Completion Time | 4 | 10 | 0.722222 | 0.678095 | -0.044127 | **不同** |
| `normalized_capability_scores.csv` | Timeout Rate | 4 | 10 | 0.877820 | 0.511496 | -0.366323 | **不同** |
| `normalized_capability_scores.csv` | Average Delay | 4 | 10 | 0.945721 | 0.594622 | -0.351099 | **不同** |
| `normalized_capability_scores.csv` | Total Energy Consumption | 4 | 10 | 0.995398 | 0.431821 | -0.563576 | **不同** |
| `weighted_overall_score.csv` | Weighted Overall Score | 4 | 10 | 0.833768 | 0.588907 | -0.244861 | **不同** |

合计 27 个统计量，其中 **22 个在两种行集合下读数不同**；引用这些表的每一行都必须声明用的是哪一种（标注写法见 `console/_citations.py`）。
