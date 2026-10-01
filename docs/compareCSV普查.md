# `results/compare/*.csv` 形状普查（每个数都由代码现算，禁止手填）

- 生成：`python console/_citations.py --csv-census --write`
- 核对：`python console/_citations.py --csv-census --verify`（不一致退出码 1）
- 扫描器：`console/_csvcensus.py`；判据用例：`console/test_compare_csv_census.py`
- **这份产物不声明谁对谁错**：它只数出磁盘上现在长什么样。
  口径能不能并列是 `results/compare_gate.py` 的事；本产物被 `--verify` 逐字节核。

## 恒等式与分桶

| 量 | 值 | 怎么算的 |
|---|---|---|
| 磁盘上的 CSV | 7 | `sorted(glob(results/compare/*.csv))` |
| 两份清单声明的条数（并集去重） | 6 | 从源码解析，不抄第二份名单 |
| ├ 两边都有 | 5 | 交集 |
| ├ 磁盘有但两份清单都没声明 | 2 | `hetero_vs_homo_hetero.csv`, `hetero_vs_homo_homo.csv` |
| └ 清单声明但磁盘没有 | 1 | `backend_wx_metrics.csv` |
| 恒等式 | 成立 | `两边都有 + 只在磁盘 = 磁盘份数`，`两边都有 + 只在清单 = 声明条数` |
| 扫描可用 | 是 | 现数 7 对下限 5；低于下限 ⇒ 整轮不作数（`[CSV_CENSUS_RANGE]`），而不是报一句"没问题" |
| 读不出表头的 | （无） | 0 字节或被截断 ⇒ 记一条问题（不抛异常：抛了就没人看得见它） |
| 出现的列宽 | 13, 20, 25 | 各文件表头字段数去重后排序 |
| 含 UTF-8 BOM 的份数 | 7 / 7 | 逐文件读首三字节 `efbbbf` |
| 没有 BOM 的 | （无） | 逐文件判，不问目录 |
| 含 seed 列的 | （无 —— 一份都没有） | 列名含 `seed`（不分大小写） |

## 逐文件

| 文件 | 列数 | 数据行数 | BOM | 首列 | 有`算法`列 | seed 列 |
|---|---|---|---|---|---|---|
| `backend_ga_metrics.csv` | 25 | 6 | 是 | `算法` | 是 | — |
| `backend_ortools_metrics.csv` | 20 | 1 | 是 | `算法` | 是 | — |
| `backend_si_metrics.csv` | 20 | 1 | 是 | `算法` | 是 | — |
| `frontend_greedy_metrics.csv` | 20 | 1 | 是 | `算法` | 是 | — |
| `hetero_vs_homo_hetero.csv` | 13 | 3 | 是 | `mode` | 否 | — |
| `hetero_vs_homo_homo.csv` | 13 | 3 | 是 | `mode` | 否 | — |
| `one_click_latest.csv` | 25 | 4 | 是 | `算法` | 是 | — |

## 两份清单各自声明了什么

- `console/server.py:_CSV_FILES`：`frontend_greedy_metrics.csv`, `backend_si_metrics.csv`, `backend_ga_metrics.csv`, `backend_ortools_metrics.csv`, `one_click_latest.csv`
- `results/plot_compare_metrics.py:CSV_FILES`：`frontend_greedy_metrics.csv`, `backend_si_metrics.csv`, `backend_ga_metrics.csv`, `backend_ortools_metrics.csv`, `backend_wx_metrics.csv`

## 与登记表 R4 的关系

R4 原先手写的那几个数（份数、列宽、BOM 例外、seed 列）**全部由本产物代管**：
登记表里那行只留结论与指路，不再留数。数一旦写进文档就会漂 —— 上一轮它漂了四条，
而漂了的注释比空白更危险，因为它看着像有依据。


## 待你定夺（只报不改，**不进退出码**）

- `backend_wx_metrics.csv` 被清单声明、磁盘上没有（`6b8c4c8` 删的） —— 摘不摘那一行是改 `CSV_FILES` 的决定，不归这道门。
**两份清单都没声明**：`hetero_vs_homo_hetero.csv`, `hetero_vs_homo_homo.csv` —— 它们仍被 `pd.concat` 之类的方式读进来时，口径就绕过了清单。
