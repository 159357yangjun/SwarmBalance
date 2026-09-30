# Changelog

## [Unreleased]

### 2026-09-30：`results/compare/` 混口径门禁（commit bae9523 / 1224506）

`VERSION` 保持 `1.0.0` 未动，未打 tag、未发 release、未 push。

**问题**：上一轮我把口径声明做在 `/api/compare` 的字段里，层次错了 —— 这个仓是给结项与
交接用的，拿 CSV 的人在 Excel/WPS 里打开或粘进论文表格，API 字段一行都帮不到他。
**不受控的那一份是文件本身。** 盘上实测七份 CSV 混着三种口径：

| 文件 | 列数 | `keep="last"` 选中行 | 完成率 |
|---|---|---|---|
| `frontend_greedy_metrics.csv` | 20 | 2000 步 / 58–60 任务 | 0.9667 |
| `backend_si_metrics.csv` | 20 | 2000 步 / 58–60 | 0.9667 |
| `backend_ortools_metrics.csv` | 20 | 2000 步 / 57–60 | 0.9500 |
| `backend_ga_metrics.csv` | 25 | **600 步 / 23–30** | **0.7667** |
| `one_click_latest.csv` | 25 | 2142.6（5 次均值）/ 60–60 | 1.0000 |
| `hetero_vs_homo_{hetero,homo}.csv` | 13 | 无总步数列（另一实验族） | — |

**处置**：
- `results/compare_gate.py` 门禁，判据取**磁盘实测**（表头指纹 + 总步数取值集合 + 生成任务数取值集合），
  不是手抄标签。判别式用例把 `quarantined` / `not_comparable_with` 标签全删掉后仍要求拒绝。
- 同目录 sidecar：`manifest.json`（机器可读单一真源）+ `README.md`（由 manifest 渲染，
  测试断言两者一致），逐文件写清能与谁并列、不能与谁并列。
- 两个生成入口默认拒：出图入口 `SystemExit 1` 并打印分组原文；`/api/compare` 不 500，
  改为 `comparable=false` + 拒绝原文，前端据此不高亮"最优算法"、不画对比图。
- `index.html:2712` 的 `r[m] ?? 0` 是假胜利的直接来源（缺列被补成 0），改为保留 null。
  浏览器实测 ECharts 对 `[null,null,0.4994,null]` 原样保留 null（断柱，不是 0 高柱）。

**重复行归因**：`backend_ga_metrics.csv` 第 2/3/4 行逐字节相同。全仓 22 份 tracked CSV 扫描，
**只有这一个文件**有重复行 → 不是导出通病。导出每次调用只写 1 行，而 `run_ga.py` 同参数
连跑两次产出逐字节相同的行（两次 md5 `c839329c`），结合同 seed 方差为 0 的实测，
重复行可由重复执行自然产生，不需要"手工粘贴"假设。真正的缺陷是**行里没有 seed/时间戳列**，
所以"跑 3 次"与"粘 3 遍"在盘上无法区分。

**顺带修 4 处失效引用**（行号对、路径过期）：`paper/main.tex` → 真路径
`paper/AAMAS-2023 Formatting Instructions/main.tex`；`simulation.json:191` → `:166`；
`index.html:2260` → `:2285`；`environment.py:901` → `:896`。三个 6b8c4c8 删除的文件
不删结论，改按 `path:line 已移除@<sha>` 约定标注并附取回命令（逐条 `git show` 验过内容），
并把该约定做成 `CitationIntegrityTests` 机器断言。

**仍未闭合**：论文图**不能靠重新生成一次就算修好** —— `paper/figure/*.png` 9 张与当前重跑产物
md5 全不一致，归档 `combined_compare_metrics.csv` 里 ga 记 2000 步、而该文件全部已提交修订的
`总步数` 只出现过 200/300/400/600，从未有 2000。要出对外的 GA 柱状图，得先按 3600/5/seeds
重跑对齐口径（本轮未跑，属需要你确认的交付变更）。

### 2026-09-29 晚：回合步数单一真源 + 指标方向判据 + 门禁自证 + 文档命令副作用（commit 01ce4da / 8d8a60f / eea30a9 / c686064 / 本轮新增）

`VERSION` 保持 `1.0.0` 未动，未打 tag、未发 release、未 push。

**① 单回合步数收成单一真源（01ce4da）** — `frontend/environment.py:79` 与 `command_console.py:95`
各留一份 `1200` 字面量，改主配置对 ad-hoc 评测入口无效。现由
`config/config_loder.get_episode_max_steps()` 唯一决定，**缺 `environment.episode_max_steps`
直接 RuntimeError**，不再悄悄退回 1200。顺带查清归档里哪些用了别的步数：
结项归档 68 次全部 3600 步（不是论文用的 1200/2000），`results/compare/` 那批手工评测是
400/600/2000/1200 混合口径 —— 后者才是论文表 `main.tex:285`「Greedy 完成 58/60」的来源，
与 3600 步的结项数据不同源（R1 遗留，仍在等你拍板）。

**② 指标方向判据（8d8a60f）** — `reporting.py:29` 把「机巢周转率」「泊位利用率」当
"越高越好"是**定义性错误**而非措辞问题：泊位 1→2→4 时排队 359s→0→0、完成率
0.85→0.9167（真改善），但周转率 1.80→0.70→0.35、利用率 0.1526→0.0700 同向下跌。
现移入 `DIRECTION_AMBIGUOUS`，胜/平/负留空并加「方向」列。权威侧判定为**代码**
（`main.tex:112` 的 `Δ_j=max(0,c_j−d_j)` 与 `total_delay/total_completed` 一致；
论文全文 0 次提及 utilization/turnover）。
**同一轮只修了一半，随后补齐（d21756c）**：`console/static/index.html:1408` 的
`compareBestRow` 用"命中越小越好关键词取最小，否则取最大"，这两个指标不含关键词，
于是落到默认分支继续被高亮"最优算法" —— 同一份数据，实验报告写「不判」、网页写"这个最好"。
现名单只留 `reporting.py` 一份，由 `/api/compare` 下发 `direction_ambiguous`、前端消费。
真跑验证：切到 机巢周转率 时 `.cmp-row.best`=0 且提示变为「不判最优」，
切回 完成率 时 best=1（反面对照，防改成永远不判）；删掉前端短路 → 对应用例变红。

**③ 门禁必须能自证（eea30a9 / c686064）** — 两条门禁原先都能"自己满足自己"：
配置哑键门禁的语料集若不排除自身源码，在门禁文件里写出键名就等于"该键已被读取"
（**失效方向是变绿不是变红**）。现各加变异用例，且实测过红：删排除行 → 哑键用例 FAIL；
`if drift:` 退回旧的"两路径相等" → 8 条里 4 条 FAIL；缺基线从 `return 1` 改 `return 0` → 对应用例 FAIL。
osmnx 漂移的手工验证也已固化为 `unittest discover` 用例，并处理了"聚合跑里静默 skip"
（`test_environment_incidents.py` 注入假 osmnx 会污染判定）—— 改为契约用例 + 子进程，
现在全量 `discover` 里 9 条全部执行、`skipped=0`。
**过程中自己写出一条空转断言并当场发现**：第一版 patch 的是 `Path.is_file`，
而 `check_loader` 用 `os.path.isfile(字符串)`，探针没生效、门禁照读真基线返回 0。

**④ 照 README 跑一次就把仓库弄脏（本轮）** — 评审/新用户照文档走一遍，工作区立刻脏，
这比"离了作者机器跑不通"更贴 R1。一手证据：

```
$ cd frontend && python evaluate_metrics.py --policy ga --episodes 1 --episode-steps 600 --seed 100
$ git status --porcelain
 M results/compare/backend_ga_metrics.csv        # 7 行 → 8 行
```

写入面清点（全部实测或按代码路径核过）：
`evaluate_metrics.py` 默认**追加**入库的 `results/compare/<算法>.csv`；
`plot_compare_metrics.py` 以 "w" **截断重写** `results/compare/plots/` 下 15 个已入库产物；
`run_conclusion.py --preset conclusion` **截断重写** `results/compare/one_click_latest.csv`
（那是 `/api/compare` 按 `keep="last"` 实际展示的那份答辩数据源）。
归档实验目录本身安全：`<preset>_<秒级时间戳>` 每次新建，不会覆盖任何一轮归档 —— 已查，不是缺陷。
另发现 README 第二条示例命令里有个**字面 `\n`**，照抄直接 `error: unrecognized arguments: n`（已修）。

处置：三者默认都改成只写 `results/adhoc/`（已 gitignore），写入库必须显式
`--record-into-evidence` / `--publish-latest`；Web「实验」页签内部自带发布开关，
页面行为不变；`.gitignore` 补 `results/experiments/<新时间戳目录>` 与 `web_status.json` /
`web_runner.log`，并写明"已跟踪文件不受 gitignore 影响，所以证据改动照样看得见"。
新增 `console/test_readme_command_side_effects.py`（6 条）：真跑文档命令后要求
porcelain **增量**为空 + 比对 `results/compare/**` 的**内容指纹**（增量法在"文件本来就已脏"
时会假绿），并先证明脏检测探针本身不是空转。三条变异均实测过红。

**⑤ 那个 0.001 已归因，不是噪声也不是文档陈旧（本轮）** — README 逐 episode 行写
`利用率=0.705 / 空载率=0.498`，同一条命令末尾的 Mean Metrics 写 `0.7045 / 0.4984`。
同一命令连跑 5 次：`逐位不一致字段数 = 0 / 24`，方差为 0；CSV 里存的全精度是
`无人机利用率=0.7045`（`.3f`→`0.705`）、`空载率=0.49840552356370954`（`.3f`→`0.498`）。
所以差值纯粹是同一个数的两种打印精度，**不存在**需要同 seed 解释的运行不稳定。
固化为 `console/test_run_determinism.py`（2 条，共用同一批运行，12.5s），
并已用 1e-4 级扰动验证过红。详见登记表第七点五节。

**本轮未验证 / 待你拍板**：

- `results/compare/plots/` 的**归档缺口**：出图脚本现在实际生成 **20** 张图，仓库只入库 **15** 张。
  我跑 `--record-into-evidence` 验证开关是否真的接线时，多出 5 个未跟踪 PNG
  （`bar_chain_insertions/drone_utilization/empty_load_ratio/no_fly_detours/total_flight_distance`）。
  它们是我这次的运行产物，**已删除**，未替你决定是否作为正式交付物入库。在该决定之前，
  请不要对该目录用 `git add -A`。
- R1 论文表与 CSV 的矛盾（`main.tex` 用 2000 步数据、结项用 3600 步）本轮**未改**。
- `frontend/environment.py:89` 的 `DEFAULT_NUM_DRONES = int(ENV_CFG.get("num_drones", 3))`
  是同一类"第二套默认"，本轮**未动**（不在你点的三件事里，且改它要一并核对前端读数）。
- `--record-into-evidence` 与 `--publish-latest` 的**正向**写盘我只在临时目录/可回滚前提下验证过，
  没有真正刷新入库证据。

### 2026-09-29 下午：两个守门门禁 + 文档数字口径对齐 + 评审视角首次运行（commit fd5ede9 / dfb3dcf / 66016b7 / 0ded28f）

本轮修的是四类**"看起来正常、其实没人读/说错了"**的问题，不是一个具体 bug。
`VERSION` 保持 `1.0.0` 未动，未打 tag、未发 release。

**① 配置哑键门禁（dfb3dcf）** — 治"模块删了、配置里的键留下没人读"这一类病。
新增 `console/test_config_keys_coverage.py`，由 `unittest discover -s console` 自动收集，
不需要有人记得跑。判据：全部源码的字符串字面量收成一个集合，配置叶子键不在其中即
"改了不起作用"；刻意偏保守（宁可漏报不误报，否则会被当噪声关掉）。覆盖 301 个叶子键
（`config/simulation.json` + `backend_si/config.yaml` + 三个实验预设）。
白名单 `ALLOWED_UNREAD` 强制写 reason（不足 12 字直接失败）。
两个实现教训：语料集必须**排除门禁自身文件**（否则"在门禁源码里写出键名"就等于
"该键已被读取"，门禁可自证通过 —— 第一版就栽在这，探针测试自己失败才发现）；
新增 `test_scanner_actually_detects_a_planted_orphan` 防止扫描器本身变成哑门禁。

**② 加载路径改为基线硬门禁（dfb3dcf）** — 回答"只是打印还是阻断"：
改之前它确实非零退出，但有个洞 —— 只比 `fallback` vs `当前路径` 是否相等，
而 **osmnx 整个消失时两条路径都退化成 fallback、数值都是 108、相等 → 返回 0 通过**。
已实测复现该洞（删掉 `ox.graph_from_xml` 模拟装坏）。现改为与 `provenance_baseline.json`
比对（mode + 两路径的 buildings/None/NaN/碰撞体），漂移即 `exit 1`；
`--allow-loader-drift` 显式放行但仍留 WARN；`--write-loader-baseline` 重采。
基线记的是实测值：osmnx 路径 2889 栋 / 25 有可用高度 / **18** 碰撞体；
fallback 2876 / 397 / **108**。判据是「与基线是否一致」而不是「两者是否相等」。

**③ README 数字逐条与代码对齐（dfb3dcf）** — 其中三处不是措辞问题而是**定义写错了**：
`Average Delay` 原写"超时任务平均超时时长"，代码是 `total_delay / 全部完成任务`；
`Drone Utilization` 原写"忙步数 / 总步数"，代码分母是 `仿真秒数 × 机队规模`，
**仅当 `time_step = 1` 时才巧合等价**；`Timeout Rate` 未说明是幸存者口径。
机型表加脚注区分「仿真输入」与「仅展示，不参与仿真计算」——
`full_load_range_km`（README「满载续航」列的 10/20/16）代码零读取，实际续航由
`battery_capacity` 与放电模型推导。删掉 `server.py 949 行` / `sim_session.py 1292 行`
这类一改代码就漂的声称（实测已漂到 964 / 1291）。badge `algorithms 5 families` → `4`。
示例输出按当前代码重测：利用率 0.706→0.705、空载率 0.499→0.498（载重 int→float 修复所致）。

**④ 两处日志标签病（66016b7）** — `environment.py:268` 把 `len(high_buildings)` 印成
"具有高度信息的建筑物"（实测 2889 / 25 / 18 是三个不同含义的数）；
`selfcheck.py:55` 把下发前端的**建筑环数 2893** 标成"高层建筑"，连 `_require` 的失败文案
也错。现三数分列。

**⑤ 缺依赖不再吐裸 traceback（0ded28f）** — 评审最可能的第一步是跳过 venv 直接跑。
根因是设计倒置：`import uvicorn` 写在 `console/run.py` 顶部，**早于**专门用来报告
缺依赖的 `run_checks()`，所以那份报告永远印不出来。现在预检先跑并列出具体缺哪些包；
`--skip-preflight` 时由 `_import_uvicorn()` 兜底给出 venv 与 requirements 两条安装路径。

**⑥ 删掉 4 个永不被读的 metrics 覆盖键（fd5ede9）** — `evaluate_metrics.py:65` 拼的是
`f"{policy}_file"`，policy 取值 greedy/pso/ga/ortools，实际查 `greedy_file`，而配置写的是
`frontend_greedy_file` 这类对不上的名字 → 5 个键里只有 `compare_dir` 生效。
同时删 `task_chain.detour_penalty_weight`（被 `max_detour_m` 绝对半径取代）。

**验证命令与实际结果**（均在 Python 3.10.11 完整环境）：

```
python -m unittest discover -s console -t .      → Ran 80 tests, OK   （原 77，+3 为门禁）
python -m unittest discover -s experiments -t .  → Ran 21 tests, OK
python release_check.py                          → exit 0，9 项全 OK，解码异常 0 次
python verify_data_provenance.py --loader        → exit 0，「环境与基线一致 mode=osmnx 碰撞体=18」
python -m console.selfcheck --steps 1            → exit 0，5.3s（冷启动 12.0s）
```

两个新门禁都**演示过红**（不是只跑绿）：种 `environment.zz_planted_dead_key` → 门禁 FAIL
并精确点名，还原 → OK；模拟 osmnx 不可用 → 5 项漂移 → exit 1，加 `--allow-loader-drift` → exit 0
且仍留 WARN。`release_check._run` 的编码修复也做了前后对照：旧写法子进程诊断捕获长度 **0**，
新写法完整捕获中文诊断。

评审视角首次运行用**真实克隆**验证（`git clone` 到临时目录、删掉 `.osm_cache` 后冷启动）：
克隆 81M、该有的都有；冷启动 selfcheck 12.0s exit 0 并自动生成缓存，
**证明不需要作者先手工跑一次**；Web 端首页 200、`/api/map` 818KB/0.32s、`/api/compare` 200、
启动日志 0 异常、截图渲染正常；跟踪文件里绝对路径/用户名泄露 0 处；
`.bat` 同时探测仓库内与上一级的 `.venv310`，都没有则告警。

**仍然没验证的东西**（不要当成已确认）：

1. `python -m venv .venv310` + `pip install -r requirements.txt` 这条建环境路径
   **完全没跑过**（不装东西是硬约束）。所以评审照 README 装环境能否成功、耗时多久、
   `pip==23.3.2` 的建议是否仍成立，全是未知。
2. `numpy 必须先装` 的顺序约束只在 requirements 注释里读到，**没实测违反会怎样**。
3. **Linux/macOS 一行都没测**；`.bat` 在非 Windows 全部不可用，是否存在等价 shell 脚本未查。
4. 门禁的 301 键里，`enabled` / `type` / `radius` 这类常见词是靠"名字在别处出现过"
   蒙混通过覆盖判据的，**它们各自真被读取没有逐个确认**。
5. `--write-loader-baseline` 只读了代码，**没实跑**。
6. 基线只覆盖地图加载路径；`ortools` / `fastapi` 版本漂移会不会改变仿真结果，**没有基线**。
7. R1（论文 `main.tex` 表格与仓库 CSV 矛盾）本轮**未动**。
8. `results/compare/` 里 4 份手写 CSV 是死数据（被 `one_click_latest.csv` 以
   `keep="last"` 全部覆盖，且其中 3 份是 20 列旧表头）—— 本轮只把副作用讲明白并加了
   `--output` 改道，**去留未决**，需要项目所有者拍板。

### 收敛为纯网页前后端（移除桌面端与 MARL）

项目形态明确为「Web 前端 + FastAPI 后端 + 无头仿真内核」，凡不在这条链路上的实现整体移除：

- **移除 pygame 桌面端**：`frontend/map_drawer.py`、`map_drawer_3d.py`、`task_shower.py`、
  `run_visual.py`、`test.py`（旧桌面主程序）与 `frontend/assets/`（8 张图，仅
  `charging_4.png` 被桌面渲染器加载）。`Environment` 的 `visualize` 参数、viewer 构建块与
  `viewer.render` 钩子一并删除 —— 此前 10 个调用点全部传 `visualize=False`，该参数是死 API。
  同步移除 `capabilities.py` 的 `desktop_visualization` 能力位、`preflight.py` 的 pygame 探测与
  依赖要求，以及 `requirements.txt` 的 `pygame==2.6.1`。
- **移除 MARL 侧**：`backend_wx/`（36 个 .py + 228 个 `.th` 检查点，约 33 MB）与
  `results/compare/backend_wx_metrics.csv` 六行，并从 `console/server.py` 的 `_CSV_FILES` 摘除。
  依据是登记表 R2 的逐格核对：54 个性能格中 **23 格优于该算法历史上最好的一局、
  0 格劣于最差一局、38 格与原始记录任何一行都不相等**，且训练产物从未进入版本库。
  这不是"结果不好"而是"数字从未对应过一次运算"，故不保留、不再引用。
- **移除随之失效的配置段**：`simulation.json` 的 `visualization`（仅桌面渲染器读）、
  `qmix_reward` 与 `qmix_assignment_repair`（仅 pymarl 读）。按行删除，其余字节不变。
- **规范同步收紧**：`docs/仿真软件设计规范.md` 的 **SA-5.4** 从「允许 Web + pygame 双实现」
  改为「仅 Web 单一实现，内核与后端不得为可视化引入 GUI 依赖」；`算法口径说明.md`
  删除 MARL 定位行、第八节改题「PSO 的扩展理由」、**第十节"答辩建议一句话"去掉 MARL**
  （那句话是当场要说出口的，留着即构成虚假陈述）；`结项最终验收清单.md` 同步。
- **保留的判定依据**：`experiments/worker.py` 虽不被任何模块 import，但 `runner.py:524-534`
  以 `subprocess.run(-m experiments.worker)` 拉起，属网页端"一键实验"链路 → 保留。
  测试文件由 `unittest discover -p test_*.py` 按模式收集，"零文本引用"对它们不构成死代码证据。


### 控制台修复与运维加固

- 修复 Web 控制台 3D 视图**黑屏**：`threeState` 是 Vue 响应式数据，THREE 的 scene/camera/renderer 被响应式 Proxy 包裹，渲染循环守卫 `threeState === st` 恒为 false（Proxy ≠ 原始对象），`render()` 从未执行。改用 `Vue.markRaw()` 让 Three 对象脱离响应式。
- 修复 3D **场景被裁**：根元素 `#app` 缺少 `class="app"`，导致 `.app { height:100vh }` 失效、`.main` 被右侧面板撑高到约 1401px，画布(999×1401)超出视口、场景中部落在可视区外。补上 `class="app"`，并给 `.side` 加 `overflow-y: auto`。
- 提升 3D **无人机可见性**：标记球半径 10 → 24，高度按状态调整为 28/46/64，避免默认视角下仅约 3px 而肉眼不可见。
- 视图切换改为下一事件循环再初始化 3D，并加 `ResizeObserver` 自适应容器尺寸。
- `start_console.bat` / `start_console_portable.bat`：虚拟环境改为「项目根 → 上级目录」两级查找（原先只查项目根会 fallback 到系统 Python，导致重复实例抢 8765 端口、页面一直加载不出来），并在启动前自动清理占用 8765 的旧实例。
- 新增 `stop_console.bat`：一键停止所有 `console.run` 进程并释放 8765 端口。
- 纳入 `run_conclusion.py --preset conclusion` 的 68 次结项实验输出（`results/experiments/`）。

### 仿真统计正确性（影响结项结论口径）

- 修复 `Environment.reset()` 漏归零 6 个按步累计量（`drone_busy_steps`、
  `total_flight_distance`、`total_empty_distance`、`total_loaded_distance`、
  `total_no_fly_detours`、`total_chain_insertions`）：控制台每点一次「重置」就叠加
  一轮，实测 `avg_drone_utilization` 走成 1.0 → 2.0 → 3.0（利用率 300%）。
  实验侧不受影响（worker 每 episode 新建环境），只有复用同一实例的 Web 会话会踩。
- 修复实验聚合 `_mean_rows` 的键名错位（用 `r.get("ok")` 筛「成功」行）：过滤后恒空，
  导致 `algorithm_comparison.csv`、四张敏感性表、`summary.md` 与 8 张图**全部静默为 0**，
  而 `raw_runs.csv` 数据正常、进程返回码 0。已改为「有输入却全被过滤掉」时抛错。
- 任务生命周期视图不再恒空：快照原先读每步末尾就被 `clear()` 的临时缓冲，
  实测 400 步后 `total_completed_tasks=15` 而 catalog 里 completed 为 0 条；
  改为另存有界耐久日志（上限 120 行）。
- 待分配队列去掉影子字段：`Environment.unassigned_tasks` 曾在 reset 里填过一次就
  不再同步（实测跑 600 步后影子留 12 条、真实队列只剩 3 条），改为只读 property 转发。
- 侧栏两处恒为 0 的假数字：「禁飞区」读快照里不存在的 `snap.no_fly_zones`（该字段在
  `/api/map`），与同屏地图上画着的 2 块禁飞区自相矛盾；「低电」读
  `snap.health.low_battery_drones`，后端实际发的是 `critical_battery`。
  低电阈值标签原写「<30%」而真实值是 0.2，现由 `/api/meta` 下发、与计数同源。
- 步长→秒的映射改为显式代码常量 `STEP_SECONDS`（`frontend/drone.py`）并在状态栏声明，
  不再靠配置凑自洽。

### 性能

- OSM 解析结果落盘缓存：`Environment` 构建 5.01s → 0.20s（25×）。
- `is_path_clear` 结果缓存 + 按障碍几何指纹分桶共享 + 落盘跨进程复用：
  2000 步总耗时降 69%，重复回合 5.93s → 0.28s（19~21×），独立进程 7.63s → 0.38s。
- 静态地图几何与环境结构指纹记忆化：`map_static()` 首次 94.1ms → 命中 0.0002ms，
  `snapshot()` 稳态 0.415ms → 0.202ms。
- 播放节拍随倍速收紧（每拍 1 步、间隔 `max(45, 350/倍速)` ms）：10x 重绘率从
  2.9fps 提到约 22fps，步速比例保持不变。
- 批量步进改为逐步放锁：快照最长排队从 7284ms 降到 325ms（30 秒压测，无失败请求）。
- 2D 画布不再每帧重分配后备存储。

### 控制台可用性与可访问性

- 前端三库（Vue / ECharts / Three.js）**本地化**到 `console/static/vendor/`，优先本地加载、
  失败回退 CDN，完全断网时显示诊断卡而非白屏。
- 界面不再谎报当前算法：改下拉不点「重置」时，原先四处展示都读本地选择值，
  表现为「选了 PSO 满屏写 PSO、跑的还是 Greedy」。改为展示读快照真值，
  未生效的选择显式标「待生效」。
- 回合结束不再留下死按钮：原先播放/单步静默无反应且界面无任何「已结束」提示。
- 检查点不再被静默销毁：误点「保存并应用」曾会清空用户存的答辩快照且无法撤销；
  现保留快照、跨环境代恢复被拒并给出可执行提示、显示「已用 N / 5」。
- 配置弹窗加载失败时不再回填硬编码默认值（避免一次失败保存把真实配置覆盖成默认值）。
- 算法对比页加「口径守卫」：分母（生成任务数）不一致时提示，每行标出来源 CSV；
  并隔离 `quick` 预设，使其无法覆盖答辩对比页的共享数据源。
- 灰阶文字对比度提到 WCAG AA（`--muted` 从 2.93~3.16:1 提到 4.99~5.55:1）；
  承载整句中文的 10px 文字抬到 11px；状态色加形状冗余（●◆■▼△ 且字形本身着色）；
  补 `:focus-visible` 焦点环与 `.tiny-btn:disabled` 禁用态。
- 5 个弹窗支持 Esc 关闭（按层叠只关最上面一层）并补 `role="dialog"` / `aria-modal`。
- 3D 视图声明「竖向放大约 4 倍、非真实比例」，避免评委按画面判断实际高差。
- 平均时延单位标签从「步」改为「s」（该量纲本就是秒）；算法对比表列名补单位后缀。
- 窄屏 ≤1150px 导航收为 64px 图标栏而非直接隐藏，5 个分层页入口不丢失。

### 交付与运维

- 复现清单 `reproducibility.json` 升级 schema v2：按算法登记实现源码哈希
  （原先 8 个哈希全是 GA 侧依赖，greedy / PSO / OR-Tools 三行零源码证据），
  文件缺失或未登记算法改为抛错而非静默记 `null`；路径一律相对仓库根，
  不再把开发机绝对路径（含用户名）打进结项证据。
  **注意**：已归档的 `conclusion_20260911-043701` 仍是 v1，未回改 —— 事后补哈希
  等于把今天的源码伪装成产出那批数字的源码；要拿 v2 证据须重跑正式实验。
- 结项证据包白名单缺文件时抛 `FileNotFoundError`（原先 `if exists: copy` 静默漏文件、
  返回码 0）；补入 `结项最终验收清单.md`（它此前不会进包）。
- `start_console*.bat` 启动前清理端口时**只终止命令行含 `console.run` 的 Python 进程**；
  原先无条件 `Stop-Process -Force` 会误杀占用 8765 的无关程序（数据库、其他 dev server）。
- 调度器配置的空保存不再抹掉 `backend_si/config.yaml` 的 111 行注释
  （`safe_load`+`safe_dump` 是破坏性往返；真改动仍会丢注释，需 round-trip 解析器才能根治）。
- 四个 bat 脚本统一虚拟环境探测（项目根 → 上级目录 → 系统 python 并告警）。
- 文档：删除 3 份零独有内容的重复文档；修正 5 处与代码相反的陈述（含一处指向
  不存在文件的引用）；README 项目结构树与文档索引重写为与目录一致、可双向校验。

### 测试

- 新增 `console/test_server_guards.py`（41 → 43 个用例）与实验聚合、复现清单、
  配置写盘等回归测试。全仓 76 console + 21 experiments + 3 打包 = 100 个用例。

## [1.0.0] - 2026-09-11

### 结项冻结 / Reproducibility

- 正式一键实验新增 `algorithm_comparison_stats.csv`：关键指标保留均值、样本标准差、中位数，不再只展示均值。
- 新增 `paired_ga_vs_greedy.csv`：按相同 Seed 对齐 GA 与 Greedy，给出方向归一化的描述性改进与胜/平/负计数；明确不等价于显著性检验。
- 新增 `reproducibility.json`：记录 Python/平台/关键依赖版本、输入配置/算法配置/OSM/preset 的 SHA-256 与算法列表。
- 新增 `build_conclusion_package.py`，自动打包最新 `conclusion_*` 正式实验、关键配置/文档和 `CHECKSUMS.sha256`。
- Web“实验”页增加“下载结项证据包”；只基于最近一次正式 conclusion 实验生成，不拿 quick 自检冒充正式数据。
- 新增 `finalize_project.bat`：严格发布检查 → 标准结项实验 → 证据归档，一步完成最终结项流水线。
- 新增 `VERSION` 和 `结项最终验收清单.md`，版本号进入单一事实来源，交付口径进入冻结阶段。
- `release_check.py` 扩展为发现全部 `experiments/test_*.py`，并验证结项证据包可构建。
- 发布包移除本地 `_review/` 申请书解析缓存并加入 `.gitignore`，避免把团队联系电话/邮箱等申请材料个人信息带入公开源码交付。

## [0.9.0] - 2026-09-11

### 离线便携与真实端到端验证

- `frontend/tools/osm.py` 新增**内置离线 OSM XML 回退解析器**：完整环境继续优先使用 OSMnx；OSMnx 缺失时，Web/headless 仿真可直接解析项目自带 `.osm`，不访问网络。
- `frontend/environment.py` 将 pygame 2D/3D Viewer 改为真正需要桌面窗口时再延迟导入，Web 控制台不再因为缺少 pygame 在 import 阶段失败。
- 新增 `console/capabilities.py`，统一识别地图后端、桌面渲染与算法可用性；OR-Tools 缺失时 Web 选项明确禁用，而不是点击后才给长 traceback。
- `python -m console.run --portable` / `start_console_portable.bat` 提供答辩应急模式；页面顶部会显示“离线便携”，不会把降级环境伪装成正式实验环境。
- 新增 `python -m console.selfcheck`：使用真实本地 OSM、真实 Environment、人工 P3 插单、真实 Greedy 调度与运行态快照完成端到端自检。
- 新增 `release_check.py` / `release_check.bat`，统一执行 compileall、38 项单元测试、Web JS 语法、实验计划 dry-run 和真实端到端自检；正式机器可加 `--strict` 强制检查 Python 3.10 + 完整依赖。
- 在缺少 OSMnx / pygame / OR-Tools 的 Python 3.13 开发环境中，已真实启动 FastAPI Web 服务，并完成 Greedy 300 步、GA 1 步、PSO 1 步的 headless 集成验证。上述验证只证明系统链路可运行，不作为论文算法对比数据。

## [0.8.0] - 2026-09-11

### 产品化收口

- 新增 **持久化场景库**：可把当前 `simulation.json`、算法/Seed 以及可选 `backend_si/config.yaml` 保存为可复现场景；支持 JSON 导入、导出、删除和一键应用。场景库与运行态快照明确分工：前者复现初始配置，后者恢复当前服务内动态节点。
- Web 顶部新增“场景库 / 使用引导”，首次进入显示推荐操作流程；“指标”页统一改为“态势”页，并新增调度策略、任务压力、机队资源、地面资源四项运行摘要。
- 态势页根据 P3 积压、停飞无人机、关闭机巢、低电和泊位排队动态生成**操作建议**，减少答辩/演示时临场判断成本。
- 新增 `start_console.bat`；`python -m console.run` 启动前执行环境预检，检查 Python 3.10、关键依赖、机队配比、机巢与 SLA 等配置一致性，并在本地启动后自动打开浏览器。
- 新增共享 `console/config_validation.py`，Web 配置保存、场景导入和启动预检使用同一套轻量配置校验，避免“界面保存成功、运行时才报错”。

### 稳定性与审计

- 修复 Web 热重建后 `environment.episode_max_steps` 仍沿用旧值的问题；现在每次 `rebuild()` 都重新读取 `simulation.json`。
- 场景库文件使用受控随机 ID，拒绝路径穿越式 ID；导入大小限制为 2 MiB，场景应用失败自动回滚仿真/算法配置。
- 补齐 `FitnessEvaluator` 中两个预留指标的实际实现，移除显眼 TODO；默认权重不启用它们，因此不改变既有实验口径。
- 更新文档口径：明确当前 Web 控制台采用 REST 轮询/批量步进，而不是尚未实现的 SSE/WebSocket；明确故障演示属于调度层资源事件，不表述为真实飞控容错/故障诊断。
- 新增场景库单元测试；控制台、事故机制、演示预设、场景库、实验编排合计 **33 项轻量单元测试通过**。

本项目采用语义化版本号（Semantic Versioning）。

## [0.7.0] - 2026-09-10

### 新增

- 新增 **答辩演示场景预设**：应急医疗高峰、机巢拥堵与优先级仲裁、故障韧性与局部重规划、标准综合演示四套场景；加载时自动应用配置 patch、固定算法与 Seed，并可一键恢复进入演示前配置。
- 新增 **“下一幕”可复现演示剧本**：剧本只自动编排现有 step / inject / incident / charge 控制接口，实际任务分配仍由当前 Greedy / GA / PSO / OR-Tools 完成。
- 新增 **运行态快照**：当前服务进程内最多保存 5 个检查点，可恢复无人机/机巢/任务、Scheduler 缓存、observation、Python/NumPy 随机数状态、事件、轨迹和统计趋势；结构性热重建时自动清空不兼容快照。
- 新增 **运行态势摘要**：集中提示 P3 积压、泊位排队、低电、停飞无人机、关闭机巢与在线机队规模。
- 指标趋势改为服务端持久采样，展示完成率、超时率、机队利用率和待调度任务数；浏览器刷新后不再丢失趋势。
- 新增 `console/scenario_presets.py` 与 `演示场景与运行态快照.md`。
- 多个演示预设之间切换时始终以“进入演示模式前”的原配置为基线重新应用 patch，避免上一预设的泊位数、任务密度等参数污染下一预设；加载失败会回滚到点击前配置。

### 稳定性与测试

- 演示场景首次加载时保存主配置还原点；场景加载失败会回滚 `simulation.json`，不会留下半生效配置。
- 运行态快照不复制 OSM 建筑几何，控制内存占用；地图结构变化后强制失效，避免跨结构恢复。
- 新增预设深拷贝、机队配比一致性、快照恢复、随机序列恢复、运行态势与剧本状态测试；控制台 / 事故机制 / 演示预设 / 实验编排合计 **26 项单元测试通过**。

## [0.6.0] - 2026-09-10

### 新增

- 新增 **场景布局编辑器**：在 Web 端直接增删/移动机巢、调整泊位数，并可新增/移动/删除圆形禁飞区；地图取点与数值编辑共存。
- 场景布局保存时进行地图边界、重复机巢 ID、换电时长、禁飞区冲突和建筑物内部等保护性校验；重建失败会自动回滚 `simulation.json`。
- 新增 **自动任务流暂停 / 恢复**：只冻结随机订单生成，不影响当前待调度任务、人工插单和无人机继续执行。
- 新增 **待调度任务运行时编辑**：可修改优先级、剩余 SLA、重量和任务类别；支持“一键升为紧急任务”，下一步直接进入当前算法的滚动重调度。
- 新增 **人工补能调度**：可将指定无人机调往最近开放机巢；若正在执行任务，则挂起剩余航线，按真实有限泊位/动态优先级排队换电后恢复任务。
- Web 指挥台新增“订单流”状态、任务运行中调整表单和无人机“调往机巢补能”操作；人工补能状态以 `to_nest` 独立展示。

### 稳定性与测试

- 场景布局编辑仅对 `random` 数据源开放；CSV / GeoJSON 场景明确提示应修改原始导入文件，避免“看似保存但运行不生效”。
- 场景编辑采用“保存后热重建”语义，与运行时任务/故障/补能控制分离，避免把结构性场景变更伪装成无重置热插拔。
- 新增自动任务流、任务编辑、人工补能的轻量测试；控制台 / 事故机制 / 实验编排共 19 项单元测试通过。

## [0.5.0] - 2026-09-10

### 新增

- 新增运行时无人机事故注入：可对指定无人机“故障停飞 / 恢复上线”，停飞后不再参与调度和移动。
- 故障机未完成任务自动回收到待调度池，并立即刷新 observation；PSO/GA/OR-Tools 事件调度缓存会安全重建，下一步由当前算法重新分配。
- 新增机巢“临时关闭 / 重新开放”：关闭机巢不再接收新补能请求，等待中的无人机及尚未抵达的补能改道会转向最近开放机巢；正在换电的无人机允许完成当前服务。
- 保护性约束：不允许关闭最后一个开放机巢，避免场景进入无补能点死锁。
- Web“调度”页新增场景事件注入卡片，可一键随机制造无人机故障、随机关闭机巢或恢复全部；地图对象详情也提供精确事故控制。
- 2D/3D 状态可视化新增“停飞无人机 / 关闭机巢”表达，事件日志新增故障、任务回收、机巢关闭、改道、恢复等事件。
- 候选无人机解释层会把故障机标记为不可行，并明确显示“故障停飞”阻塞原因。

### 稳定性与测试

- `frontend/drone.py` 新增 `out_of_service` 状态，冻结故障机的移动/换电逻辑。
- `frontend/charging_station.py` 的最近机巢选择自动忽略关闭站点。
- 新增 `console/test_environment_incidents.py`，在不加载 OSM 的情况下验证“故障回收任务 / 关闭机巢改道 / 最后机巢保护”。
- 控制台与实验编排合计 13 项轻量单元测试通过。

## [0.4.0] - 2026-09-10

### 新增

- Web 控制台升级为可点击“调度指挥台”：2D 地图可命中无人机、任务轨迹与机巢，3D 视图通过 Raycaster 直接选择对象。
- 新增地图浮动详情面板：无人机展示机型、电量、速度、载重、剩余航线、当前任务链与换电状态；机巢展示泊位占用、换电时长、仲裁策略和排队顺序。
- 新增任务生命周期 `task_catalog`：统一呈现待调度、已分配、执行中和最近完成任务，完成任务保留执行无人机、完成时刻和是否准时。
- 新增 `/api/tasks/{task_id}/candidates` 解释接口：对待调度任务给出候选无人机能力匹配、预计 ETA、估算距离、电量和约束阻塞原因。该排名仅用于解释，不替代各算法真实决策。
- “调度”页新增按剩余时限排序的待调度任务列表；无人机、机巢、任务和事件日志均可点击联动详情。
- 人工注入新任务后自动选中该任务，可立即查看候选机解释，再单步观察真实算法最终分配。

### 稳定性

- 配置热重建后会安全销毁并重建 Three.js 场景，避免机队数量变化后 3D mesh 与快照错位。
- Three.js 重建时移除全局鼠标监听并停止旧 animation frame，避免重复重建造成事件/渲染循环泄漏。
- 新增 `console/test_command_console.py`，无需 OSM/osmnx 即可验证任务生命周期与候选机解释逻辑。

## [0.3.0] - 2026-09-10

### 新增

- Web 控制台新增“＋ 新任务”：可在不重置场景的情况下向当前任务池人工插入普通、重货或紧急任务。
- 支持随机合法起终点，以及在 2D 地图上依次点击起点 / 终点进行任务取点。
- 新增“调度”页：实时查看无人机任务链、剩余航线、机巢泊位占用与排队、动态优先级。
- 新增调度事件流：任务到达、任务分配、任务链插入、任务完成、泊位等待 / 获准、换电完成均可追踪。
- 快照补充任务类别、体积、deadline、剩余时间、任务链和机巢队列详情。

### 稳定性

- `step/reset/rebuild/inject` 在服务端串行执行，避免高倍速播放时出现并发推进。
- 2x/5x/10x 播放改为单请求批量推进多步，减少前后端 HTTP 压力；前端增加 stepping 锁，避免慢请求重叠。
- 人工任务会立即刷新 observation，保证下一调度步能够看到新任务，而不是延迟一轮。
- 注入任务校验载重、地图边界、禁飞区、起终点重合与截止时间，避免人为制造不可完成订单污染指标。

## [0.2.0] - 2026-09-10

### 新增

- `ExperimentRunner` 一键结项实验编排器：算法对比 + 任务密度 / 机巢泊位 / 异构配比敏感性分析。
- `quick / conclusion / paper` 三套 YAML 预设，支持 `--dry-run` 先生成运行计划。
- 每个 episode 独立子进程 + `SWARM_BALANCE_SIM_CONFIG` 配置覆盖，批量实验不改写主 `simulation.json`。
- 自动输出 `raw_runs.csv`、各类汇总 CSV、实验图和 `summary.md`。
- Web 控制台新增“实验”页签，可一键启动预设并查看进度；与 CLI 共用同一编排器。
- Windows `run_conclusion.bat` 一键入口。

### 测试

- 新增 `experiments/test_runner.py`，验证同条件算法 Seed 对齐、异构配比/机队规模一致、环境变量配置隔离。
- 当前构建环境缺少 `osmnx`，真实 OSM episode 会被预检直接阻止并给出安装提示，不会静默生成伪结果。

## [0.1.0] - 2026-09-08

首个对外发布的版本，覆盖项目申请书承诺的核心仿真能力与算法对比框架。

### 新增

**调度算法**

- Greedy 贪心基线（距离 / 优先级 / 紧迫度 / 电量 / 载荷 实时打分）
- PSO 粒子群批量分配 + 事件驱动双通道框架
- GA 遗传算法，支持 `permutation`（排列编码 + 贪婪分割解码）与 `assignment`（分配矩阵）双编码
- OR-Tools CP-SAT 经典求解器基线
- MARL 多智能体强化学习（IQL / VDN / QMIX 及其 `-U` 改进版）

**任务链与顺路接入**

- `backend_si/chain_codec.py`：排列编码 → 贪婪分割解码，输出每机有序任务链
- 在途无人机按绕行半径 / 载重 / 电量 / 时间窗约束顺路追加任务
- `frontend/ab_chain_test.py`：任务链机制开/关 A/B 对照脚本

**禁飞区**

- `frontend/no_fly_zone.py`：circle / polygon 禁飞区，含安全余量外扩
- 接入 `is_path_clear()` 与 A\* 可见图，实现真绕飞
- 任务取送货点自动过滤，避免生成不可达任务

**仿真环境**

- 异构机队三种机型（参数取自公开产品规格）
- 机巢有限泊位 + 动态优先级仲裁，整组换电 180 秒
- 可插拔数据源：random / CSV / GeoJSON / 企业 REST 网关

**评估与可视化**

- `frontend/metrics_schema.py`：统一指标落盘 schema（单一事实来源，自动备份不覆盖）
- 新增机队利用率、空载率、总飞行距离、顺路接入次数、禁飞区绕飞次数指标
- 原生 pygame 三维软件投影窗口（`frontend/run_visual.py`）
- Web 可视化控制台（`console/`，FastAPI + Vue3 + Three.js）

### 修复

- **送达即卸货**：此前 `current_load` 仅在整条航线跑完时清零，在途机永远「满载」，
  导致追加任务必被载重检查拒绝、任务链无法生效
- **异源航线追加**：此前只有同源任务能追加到在途航线，异源任务会覆盖整条航线导致前序任务丢失
- 统一四类算法的随机种子（`seed = 100 + episode_id`），此前 Greedy 未传 seed 导致场景不对齐
- 统一 CSV 表头口径，修复汇总脚本 `KeyError: Missing algorithm column`
- 表头不兼容时自动备份旧 CSV，不再静默覆盖历史实验结果

### 新增：申请书对齐增强

- GA 贪婪分割后新增链内 swap / 2-opt 与跨链 relocate 局部搜索，邻域解统一进行载重、电量、时间窗可行性校验
- 新增 `backend_si/matching.py` 共享异构能力匹配函数，并将匹配奖励正式接入 GA 解码代价
- `backend_si/config.yaml` 新增 `chain.w_match`、`chain.local_search`、`chain.local_search_passes` 可复现实验参数

### 已知局限

- 尚未实现 Or-opt / ALNS 等更大邻域局部搜索
- 禁飞区为静态配置，未实现时变管制
- `frontend/nest.py` 为未被环境引用的冗余死代码
