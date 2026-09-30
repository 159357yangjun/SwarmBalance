# `results/compare/` 口径声明（自动生成，勿手改）

> 本文件由 `python results/compare_gate.py --render-readme` 从同目录的
> `manifest.json` 生成。**机器可读的那份是 `manifest.json`**；本文件只是它的展开，
> 供在 Excel/WPS/论文表格这些**不走 `/api/compare`** 的读者看。
> 一致性由 `console/test_compare_gate.py` 断言：手改本文件或改了 CSV 不改 manifest，测试就红。

**一句话**：这个目录里的文件分属三种口径，不能随手并到一张表或一张图里。`backend_ga_metrics.csv` 的 GA 是 400/600 步、22/30 个任务的短跑，其余三个基线是 2000 步 / 60 个任务 —— 完成率 0.7667 与 0.9667 的差里混着 episode 长度，不全是算法差异。

## 为什么这个目录危险

- 这个目录是给**结项与交接**用的。拿 CSV 的人是在 Excel/WPS 里打开、或把它粘进论文表格，`/api/compare` 的 `口径` 字段一行都帮不到他 —— 所以口径声明必须做成同目录的文件，而不是只做在 API 层。
- 25 列与 20 列混放时，Excel 按列对齐会把基线的机队 5 列留空，图表工具常把空值当 0。
- `results/plot_compare_metrics.py` 与 `console/server.py` 读的是**不同的文件清单**（只有后者带 one_click_latest.csv），所以同一批文件在图和页上会选出不同的行。

## 逐文件口径

| 文件 | 实验族 | episode 步数上限 | episode 数 | 随机种子集 | 生成任务数 | schema 指纹 | 总步数列实际取值 |
|---|---|---:|---:|---|---:|---|---|
| `backend_ga_metrics.csv` | algorithm_comparison | 400 或 600（同一文件内两种） | unknown | unknown | 22 或 30（同一文件内两种） | `n25-e5c7244bc840` | ['400.0', '600.0'] |
| `backend_ortools_metrics.csv` | algorithm_comparison | 2000 | unknown | unknown | 60 | `n20-75f2e8bdb73e` | ['2000.0'] |
| `backend_si_metrics.csv` | algorithm_comparison | 2000 | unknown | unknown | 60 | `n20-75f2e8bdb73e` | ['2000.0'] |
| `frontend_greedy_metrics.csv` | algorithm_comparison | 2000 | unknown | unknown | 60 | `n20-75f2e8bdb73e` | ['2000.0'] |
| `hetero_vs_homo_hetero.csv` | hetero_vs_homo | unknown（本族 CSV 没有总步数列） | 3 | unknown | unknown（只有比率列与 total_generated） | `n13-566c12dc2ab5` | None |
| `hetero_vs_homo_homo.csv` | hetero_vs_homo | unknown（本族 CSV 没有总步数列） | 3 | unknown | unknown | `n13-566c12dc2ab5` | None |
| `one_click_latest.csv` | conclusion_experiment_summary | 3600 | 5 | 101,102,103,104,105 | 60 | `n25-e5c7244bc840` | ['2112.6', '2118.4', '2142.6', '2270.4'] |

## 逐文件并列许可

（这一节直接展开 manifest 里每个文件的 `comparable_with` / `not_comparable_with`：在 Excel 里接线的人要的是「这个文件能不能跟我手上那张表并排」这种逐文件答案，不是分组叙事。）

| 文件 | 可与谁并列 | 不可与谁并列 |
|---|---|---|
| `backend_ga_metrics.csv` | **无**（已被隔离） | 不可与 `frontend_greedy_metrics.csv`、`backend_si_metrics.csv`、`backend_ortools_metrics.csv`、`one_click_latest.csv`、`hetero_vs_homo_hetero.csv`、`hetero_vs_homo_homo.csv` 并列 |
| `backend_ortools_metrics.csv` | `frontend_greedy_metrics.csv`、`backend_si_metrics.csv` | 不可与 `backend_ga_metrics.csv`、`one_click_latest.csv`、`hetero_vs_homo_hetero.csv`、`hetero_vs_homo_homo.csv` 并列 |
| `backend_si_metrics.csv` | `frontend_greedy_metrics.csv`、`backend_ortools_metrics.csv` | 不可与 `backend_ga_metrics.csv`、`one_click_latest.csv`、`hetero_vs_homo_hetero.csv`、`hetero_vs_homo_homo.csv` 并列 |
| `frontend_greedy_metrics.csv` | `backend_si_metrics.csv`、`backend_ortools_metrics.csv` | 不可与 `backend_ga_metrics.csv`、`one_click_latest.csv`、`hetero_vs_homo_hetero.csv`、`hetero_vs_homo_homo.csv` 并列 |
| `hetero_vs_homo_hetero.csv` | `hetero_vs_homo_homo.csv` | 不可与 `frontend_greedy_metrics.csv`、`backend_si_metrics.csv`、`backend_ortools_metrics.csv`、`backend_ga_metrics.csv`、`one_click_latest.csv` 并列 |
| `hetero_vs_homo_homo.csv` | `hetero_vs_homo_hetero.csv` | 不可与 `frontend_greedy_metrics.csv`、`backend_si_metrics.csv`、`backend_ortools_metrics.csv`、`backend_ga_metrics.csv`、`one_click_latest.csv` 并列 |
| `one_click_latest.csv` | （跨文件：**无**）本文件内部各行彼此可比；同文件内 greedy/pso/ga/ortools（四个算法各一行） 共用同一口径 | 不可与 `frontend_greedy_metrics.csv`、`backend_si_metrics.csv`、`backend_ortools_metrics.csv`、`backend_ga_metrics.csv`、`hetero_vs_homo_hetero.csv`、`hetero_vs_homo_homo.csv` 并列 |

## 能与谁并列、不能与谁并列

### A 组 · 正式结项实验（唯一可直接对外的一组图/表）

- 可并列成员：`one_click_latest.csv`
- 3600 步上限 / 每算法 5 次重复 / seeds 101–105 / 60 个生成任务，四算法同口径。
- `/api/compare` 今天显示的正是这一组（keep="last" 恰好让它盖住其余文件），所以**当前页面读数是全 1.0 完成率**、不是 0.9667。
- 口径可查：results/experiments/conclusion_20260911-043701/（raw_runs.csv 68 行、reproducibility.json）。

### B 组 · 2000 步 ad-hoc 基线（三者内部可比，但不得与 A 组或 ga 短跑并列）

- 可并列成员：`frontend_greedy_metrics.csv`, `backend_si_metrics.csv`, `backend_ortools_metrics.csv`
- 2000 步 / 60 任务，完成率 0.9667、0.9667、0.9500。
- 缺机队 5 列，所以任何用到那 5 列的图对这一组都不成立（见「缺失列」一节）。
- episode 数与种子集当年没写进 CSV，所以这一组只能给描述性读数，不能声称可复现。

### C 组 · 已隔离：backend_ga_metrics.csv

- 可并列成员：`backend_ga_metrics.csv`
- 400/600 步、22/30 任务的短跑，与 A、B 两组都不同口径。
- **不得单独成图，也不得与 A/B 并列**。要拿 GA 的对外柱状图，必须按 3600/5/seeds 重跑，或直接用 A 组里已有的 GA 行。
- 留在目录里不删，是为了保住"论文图当年是怎么生成的"这份物证；隔离靠门禁拒绝并列，不靠人的记性。

### D 组 · hetero_vs_homo_*（独立实验族，自成一组）

- 可并列成员：`hetero_vs_homo_hetero.csv`, `hetero_vs_homo_homo.csv`
- 只与同族另一文件并列；与前 5 个文件没有任何共同口径列。
- 两个生成入口都不读它们，放在这里是防止接手的人在 Excel 里把它们接成一张表。

## 缺失列必须渲染为「空」，不是 0

- `无人机利用率`、`空载率`、`总飞行距离`、`顺路接入次数`、`禁飞区绕飞次数` 这 5 列**只存在于 25 列 schema**（backend_ga_metrics.csv、one_click_latest.csv）；三个 2000 步基线是 20 列 schema，根本没有这 5 列。
- `pd.concat` 按列对齐后，缺失方是 **NaN**，不是 0。渲染规则：**必须显示为空/断口，绝不能补 0**。补 0 会把"没测"变成"测了且为 0"，在越低越好的指标上直接制造假胜利（空载率 0 优于 GA 的 0.4994 就是这种假胜利）。
- Web 表格 `cmpFmt()` 已按此渲染成「—」（正确）；柱状图原先写的是 `r[m] ?? 0`（错误），已改为保留 null 让 ECharts 断柱。
- matplotlib 侧 NaN 是"不画这根柱子"，视觉上像"只有 GA 有数据"，同样构成误导 —— 所以缺列时必须由门禁拒绝该指标成图，而不是出半张图。

## 门禁

```bash
python results/compare_gate.py --check-all
python results/compare_gate.py --check-group frontend_greedy_metrics.csv backend_si_metrics.csv
python results/compare_gate.py --selftest   # 证明拒绝逻辑真的会拒
```

拒绝时退出码非 0。入口（`results/plot_compare_metrics.py`、`console/server.py` 的
`/api/compare`）默认调用本门禁，混口径直接拒。
