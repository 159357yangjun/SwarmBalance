# 本目录已作废（VOID）—— 不要用于答辩、不要用于论文配图

**结论先说**：本目录里的派生表与图仍含**已被撤除的那批 MARL 算法**（件数不在这里记，见下面
"已实测"一节的运行行）：`iql` / `iql_u` / `vdn` / `vdn_u` / `qmix` / `qmix_u`。这些行的数字在
`docs/数据来源与可追溯性登记表.md` 第五节 R2 已被逐格证伪（54 个性能格里 23 个优于该算法
历史上最好的一局、38 个与任何 train/test 行都不相等），并于 6b8c4c8 从数据源与对比页撤除。
**撤除没到达本目录**，所以这里的图与表现在仍然是一批"结论已被否掉"的产物。

## 凭什么说它没被撤除覆盖（一手证据）

| 事实 | 实测方式 |
|---|---|
| 每张派生表的算法列都等于 `console/_rowsets.py` 的 `ALL_NAMED`（核心四个 + 上面点名的六个） | `csv.reader` 读第一列，断言写在 `console/test_plots_archive_void.py`；名单只有一份 |
| 目录里每一件产物（表 + PNG）**逐件**查最后一次入库改动，都是 `fcc7c5f`（2026-09-11） | `git log -1 --format=%H -- results/compare/plots/<每个文件>`，由 `console/test_plots_archive_void.py` 跑，件数印在 `[PLOT_VOID_ARTIFACTS]` 行上 |
| 这些提交都是 `6b8c4c8`（2026-09-29 撤除 MARL）的**祖先** —— 即撤除从未碰过它们 | `git merge-base --is-ancestor fcc7c5f 6b8c4c8` |
| 当前出图脚本在这批数据上**拒绝**出图（混口径），所以也不可能"顺手刷新"过这里 | `python results/plot_compare_metrics.py` → 退出码 1，原文以 `[REFUSED]` 开头 |

## 这个行集合分叉值多少（不是态度，是数）

`results/row_set_delta.py` 对本目录每张派生表逐个统计量算了两种行集合下的均值，产物在同目录
`ROW_SETS.md`：**哪几个统计量两读数不同、差多少，都以那份产物为准**
（`python results/row_set_delta.py --verify` 不一致退出码 1；手改一个数字就会被
`console/test_plots_archive_void.py` 抓到）。最刺眼的一行是 `Weighted Overall Score`：
只算核心算法与含已撤除算法两种读法差了一大截，方向确定 —— 混进来的恰好是较弱的那批，**拉低**。
这里刻意不再抄那几个读数：抄一次就多一处会漂的地方。

> 这里刻意**不**用“整个目录最后一次改动”当证据：本通知自己就是往这个目录里新加一个文件，
> 一旦以目录为准，"撤除没到达这里"会被这条通知的提交推翻。判据必须逐件问产物。

另有一处口径不一致值得记下：本目录 `combined_compare_metrics.csv` 里 `ga` 记的步数，与现已入库的
`results/compare/backend_ga_metrics.csv` 里 `ga` 的步数**不是同一个数** —— 两个读数由
`console/test_plots_archive_void.py::test_two_different_ga_calibers_coexist` 每次跑时印成
`[PLOT_VOID_GA_CALIBER] archived=… current=…`，纸面不再抄它。同目录并存两份不同口径的 GA，
谁也不知道图上那根 GA 柱是哪来的。

### 已实测 vs 尚未实测（别把推断当成核过）

- **实测**：本目录里**每一张**派生表的算法列都等于 `console/_rowsets.py` 的 `ALL_NAMED`
  （核心四个 + 下面点名的六个已撤除）；PNG 的最后一次入库改动**逐张**查过，全部是 `fcc7c5f`
  （与那些表同一次提交、同批产物）。件数不写在这里 —— 每次跑
  `python -m unittest console.test_plots_archive_void` 会印
  `[PLOT_VOID_CENSUS] csv=… png=…` 与 `[PLOT_VOID_ARTIFACTS] 逐件问祖先：… 件`，
  那是本轮真值；抄进纸面就必然漂（这一版之前正是这么漂过 15/12/10 三个数）。
- **未实测**：PNG 的**像素里**是否真画着 6 根 MARL 柱，没有单独核验 —— 位图无法像 CSV 那样
  读列核对，只能靠"同批、同一脚本、同一输入表"推断。要坐实这件事，只能按下面的顺序重跑
  生成器再逐张比对。作废判断不依赖这一条：只要派生表还带着那六行，这批产物就不能当证据用。

## 为什么默认不就地重生

出图入口默认只写 `results/adhoc/plots/`（已 gitignore）。要把结果刷进这里需要
`--record-into-evidence`，而它今天会先被口径门禁拒绝：GA 与三个 2000 步基线不同口径。
**补齐顺序**（不是改判据，是把数据补齐）：

1. 按结项口径重跑 GA：口径就是 `one_click_latest.csv` 在 `results/compare/manifest.json` 里那条
   声明（`episode_max_steps` / `episode_count` / `seed_set` 三个字段），**这里不抄它们的值** ——
   `python results/compare_gate.py --check-all` 会核这份声明与磁盘是否一致；
2. 确认 `python results/compare_gate.py --check-all` 通过；
3. 再跑 `python results/plot_compare_metrics.py --record-into-evidence`。

## 本文件由谁保证不失效

`console/test_plots_archive_void.py`：
① 断言本目录每张 `.csv` 的算法列都等于 `console/_rowsets.py` 的 `ALL_NAMED`——若有人清了 MARL 行
却忘了撤销本通知，测试会红并提示改这里（双向指纹，避免"作废声明"反过来过期）；名单只有一份，
本文件与用例都不许再抄第二份；
② 断言本文件确实写着"作废"并逐个点名 `WITHDRAWN` 里的每个算法（点名的个数由那份名单决定）；
③ 断言 `fcc7c5f` 是 `6b8c4c8` 的祖先（撤除未到达本目录这件事不能只靠人记）；
④ 判别式：喂一份“去掉 MARL 行”的表，判据必须不认它；
⑤ 本目录任何 `.csv`/`.png` 被文档引用时，**紧跟其后必须写** `行集=core4` 或
   `行集=all10`（`console/_citations.py` 强制）。声明 `all10` 的还要与表里的实际
   算法集合相符 —— 表哪天重生成只剩 4 行，这个标注自己就会变红（双向，
   不让作废声明永久挂在已经干净的产物上）。
