# Changelog

## [Unreleased]

### 2026-10-02：配对实验的"可判性"做成一条会算的量（顺带抓住我自己一个公式错）

上一轮我说"GA 没稳定超过 Greedy"是**定性说法**，仓里没有任何东西把它变成可核对的量，
也没有任何东西保证 `paired_ga_vs_greedy.csv` 那句"不代表统计显著性"的免责被兑现。
新增 `console/_paired_readout.py`（+ 常驻用例 `test_paired_readout.py` 5 条）：读某次实验的
`raw_runs.csv`，按同 seed 配对后印逐 seed 差值、胜/平/负、**穷举 2^n 符号置换的精确双侧 p**，
以及**这组重复次数在数学上能达到的最小 p**。方向集合从 `experiments/reporting.py` 用 AST 解析，
不抄第二份；`n>8` 直接拒绝而不是偷偷近似。

本轮真数据读数（新那批，greedy vs ga，n=5）：超时率 win/tie/loss = 0/3/2、精确 p=0.5000；
无人机利用率 3/0/2、p=0.6875；平均时延**未登记方向** ⇒ 只印两侧均值 4.3017(sd 2.573) vs
5.4000(sd 5.386)，不产出胜负。**最小可得 p = 0.0625 > α=0.05** ⇒ 结论不是"这次没测出显著"，
而是"**这个重复次数在设计上给不出显著性**"；首个可判的 n 是 **6**。要方向就加 seed。

**我自己的一个公式错被这条门抓住**：第一版写的是闭式 `2·C(n,⌊n/2⌋)/2^n`，它在偶数 n 上高估
（n=2 给 1.0，真值 0.5），我据此把"0.625"写进了结项包文案。是常驻用例里那条
"与穷举逐个 n 对齐"的断言当场报红才发现的 —— 现在改成直接按统计量分布枚举，
文案同步改为 0.0625。教训：**比率类判据先跟独立实现逐点对齐，再往文档里写数**。

复算：`python console/_paired_readout.py --metric 超时率 --metric 无人机利用率 --metric 平均时延` rc=0；
`console.test_paired_readout` 5 条 OK；全套 `Ran 236 tests in 130.653s OK`；
`build_conclusion_package.py` 仍能构建（写到临时目录，未出包）。VERSION 仍 1.0.0、无 remote、
paper/ 未碰、对外产物未动。README 命令块与 `_readme_counts` 计数同步（28 文件 / 236 用例）。

### 2026-10-02：`release_check.py --strict` 在本机跑过一次并通过（把"从未跑过"这条欠账划掉）

之前几轮的"未验证清单"里一直挂着"`--strict` 只在非完整环境跑过"。本轮实测：
`.venv310`（Python **3.10.11**，正是项目锁的版本）下先探一次 `run_checks(portable=False)` ——
`errors=0 warnings=0`、`optional={osmnx:True, pyproj:True, ortools:True}` ⇒ 这台机器**就是**
官方完整环境，那条欠账是记账过严而不是环境不满足。随后真跑 `python release_check.py --strict`：
rc=0，12 行 `[OK]`、`[FAIL]` 计数 **0**，含 `[OK] 官方完整环境预检`、
`[OK] console 单元测试 · Ran 231 tests（failures=0 errors=0 skipped=0）· OK`、
`[WARN_CENSUS] … 带出处=0 suite=231`、`[OK] 便携 Web 端到端自检`、`[OK] 结项证据包构建`。

边界与代价说清：这一步会构建证据包，但走的是 `build_conclusion_package.py --output <临时目录>`
（`tempfile.TemporaryDirectory()`），跑完 `git status` 仍为空、`deliverables/` 里没有新 zip
（只有 9-29 那个旧的）⇒ **没有产出任何交付包**，不构成出包。耗时约 3 分钟。
所以"未验证清单"里这一条改为已闭合；其余各项（新旧两批的对外指向、PNG 像素、A2 仓外取值、
论文十七处、`fcc7c5f..HEAD` 全量行为扫描）原样挂着。

### 2026-10-02：`6b8c4c8` 行为中性升到四算法证据；给 `4d956e6` 那个载重修复补上它欠的回归门

**① "行为中性"不能靠一格读数。** 上一轮我只比了 greedy 一格就说 `6b8c4c8` 两侧相同。
本轮把父提交 `4d956e6` 与子提交各跑**四个算法**（greedy/ortools/ga/pso，同 seed=101、steps=3600），
24 个数值列取到 1e-9 逐格比：**四组指纹全部相同**（`[VERDICT] 四算法逐格相同(行为中性)=True`）
⇒ 这次不是单点采样，是覆盖四个算法面的读数。耗时那一列照旧只当旁证（A/B 差 ±7% 以内、无方向性）。

**② 顺手发现：`4d956e6` 那个修复当时没有留任何断言。** 全仓搜 `carrying_capacity` 只有别的测试自造的
capacity 值 —— 也就是说谁把 `frontend/drone.py:48` 的 `float(` 改回 `int(`，**没有一条用例会红**，
而这一处一旦退回，同 seed 的结项指标会整批漂移（实测跳变：总步数 2274→2049、超时率 0.0833→0.0667、
平均时延 4.7250→2.5833）。所以补了常驻用例 `console/test_carrying_capacity_is_float.py`（5 条）：
配置前提（确有整数机型 + 小数机型才继续测）、运行时逐位等于配置、默认值那条路也是 float、
源码级扫描不许残留 `int(...carrying_capacity...)`、以及判别式（扰动一个字节必须被点名）。

**变异演示（真做在盘上，还原有 sha 证人）**：把 `frontend/drone.py` 那行改成 `int(` ⇒
`FAILED (failures=3)`（三条各自红：源码扫描、判别式的"当前源码应为 0"、运行时 2.4→2）；
还原后 `sha256[:12]` 前后同为 `6ab6ff3321b7`、`git status` 只剩新增测试文件。
途中我自己踩了一次加载约定：先写 `from frontend.drone import Drone` 撞上平铺兄弟模块
（`ModuleNotFoundError: charging_station`），改用本仓既有的 `_preflight.load_frontend_module`
+ `require("numpy","shapely")` 才对 —— 这条约定不该靠记忆，所以按 `test_environment_incidents.py` 的形状抄齐。

复算：`python -m unittest console.test_carrying_capacity_is_float` rc=0
（`[CAP_CONFIG] 小数载重机型={"light_express": 2.4}`、`[CAP_RUNTIME] light_express=2.4 default=10.0 hetero=True`）；
全套 `Ran 231 tests in 89.899s OK`；README 计数由 `_readme_counts --fix` 更新为 27 文件 / 231 用例。
VERSION 仍 1.0.0、无 remote 故未 push、paper/ 未碰、对外产物未动。

### 2026-10-02：同 seed 指标变化的来源定到 `4d956e6`（机型载重 int→float），我上一轮记在 `6b8c4c8` 名下是错的

稀疏采样会骗人。上一轮那张按 ref 排的单格表里，我把"总步数 2274→2049、超时率 0.0833→0.0667"
这一跳归给了采到的那一点 `6b8c4c8`。本轮补跑它的**父提交**做对照：

| ref | 做了什么 | 总步数 | 超时率 | 平均时延 |
|---|---|---|---|---|
| `638cffe` | 桶落盘（只改缓存） | 2274 | 0.0833 | 4.7250 |
| `4d956e6` | **载重 `int()`→`float()`**（light_express 2 kg → 2.4 kg） | **2049** | **0.0667** | **2.5833** |
| `6b8c4c8` | 移除桌面端与 MARL 侧 | 2049 | 0.0667 | 2.5833 |

⇒ 跳变在 `4d956e6`，`6b8c4c8` 两侧逐格相同、被排除。机制也对得上：那次把
`frontend/drone.py:26/48` 两处 `int(_DRONE_CFG.get("carrying_capacity", …))` 换成 `float`；
配置里 `light_express` 是 2.4 kg（README 与两份文档印的也是 2.4），运行时此前实测拿到 2 ——
0.4 kg 直接改变"这个任务 light 机型接不接得了"的判定边界，于是同 seed 下分配序列、
总步数与时延全变。

**对旧那批的意义（这才是"要不要换对外指向"的真正分量）**：归档实验钉的是 `fcc7c5f`（2026-09-11），
早于 `4d956e6`（2026-09-29）⇒ 旧那 68 次运行里的每一次都在**与配置和文档都不一致的载重参数**下跑的，
不只是"旧内核"。登记簿「再切一层」一节写了同一张表与这条推论；三处把该跳写成 `6b8c4c8` 的旧表述已就地改正，
改正说明留在原句里（不静默覆盖自己上一笔写下的话）。

复算：`git archive 4d956e6 | tar -x -C <临时目录>` + 同一份单格预设（greedy / seed=101 / steps=3600）。
门复算：`_citations --verify rc=0`、console 全套 `Ran 226 tests OK`、`release_check.py rc=0`。
VERSION 仍 1.0.0、无 remote 故未 push、paper/ 未碰、对外产物未动。

**并且这条更正过程自己抓出了上一笔新加的那道门的 bug**：改完文档后 `_citations --verify` 变红，
`test_live_repo_table_is_self_consistent` 报"现况有问题条目 1"—— `06eb5a2` 又掉回"未归类"。
根因是我把判据②写成了"活对端**现在仍是分支头**"：仓往前走了一笔之后，被 amend 的那条早就不在 tip 上了
⇒ **一条会在健康仓上自己变红的门**。改成"活对端曾在 reflog 里当过分支头"（并遍历所有 `refs/heads/*`
的 reflog，不只主分支），夹具里的反例①同步换成测这个真形状：tip 前进之后仍须认出来；
反例②保留"从未上头的对象不许认"。修完 `problems=0`、`Ran 9 tests OK`、
`[REWRITE_MAP_MATCH] objects=152 reachable=129 unreachable=23 pairs=18 problems=0`。
教训：**给分类器加放行条件时，"当前状态"类谓词要问一遍"仓往前走一笔它还成立吗"** ——
不成立的就是自毁型判据，我上一轮刚在另一条门上写过同类错误（目录最后一次改动 vs 逐件问）。

### 2026-10-02：`detour_penalty_weight` 用受控重跑证明不承重；顺带把我自己 amend 造出的悬空对象认出来

**受控重跑（单变量）**：A 面 = 仓内 `config/simulation.json` 原样，B 面 = 只往 `task_chain`
加回一个叶子键 `"detour_penalty_weight": 1.0`。前置门先证两侧只差这一个键
（`[AB_INPUTS] added={"task_chain.detour_penalty_weight":1.0} removed=0 changed=0 ok=True`，
不满足就退出码 2 不比），同一棵树、同一 `greedy / seed=101 / steps=3600` 各跑 3 次，
比的是**指标指纹**（24 个数值列取到 1e-9 后逐格相等）而不是耗时 —— 耗时被几何缓存冷热污染过
（同树三连测 12.35/2.81/1.91 s），这里只当旁证（A 1.62–1.70、B 1.62–1.63）。
读数：`[AB_VERDICT] 两面各自稳定=True 指标逐格相同=True` ⇒ **该键不承重**，
上一条里"`simulation.json` 哈希差解释了新旧指标差"这句话**作废**，登记簿已改。
仓内配置一个字节未动（跑完复核 sha 仍是 `8a2f254c5cbe`、`git status` 只剩本轮文档改动）。

**顺手修掉我自己撞出来的门失效**：上一笔 amend（改提交信息里的失实措辞）把旧 tip 变成不可达对象，
而它按 subject 配不上对 ⇒ `--rewrite-report --verify` 报 `[REWRITE_MAP_STALE]` + "未归类"问题 1 条。
不能靠手改产物消红，所以给 `_rewrites.py` 加了第四类具名归类 `classify_amended_tip()`，判据锁三条：
同 tree+parent+作者时间戳、subject 不同、活对端仍在分支头、且旧 sha 在 reflog 里当过头。
夹具 `test_amended_tip_is_named_not_swallowed` 两个反例都在：**非 tip 位置**的同类对象不许放行、
**从未上头**的对象不许放行 —— 否则这条归类就成了能装下任意历史重写的口袋。
现在映射表印 `消息改写 | 06eb5a2 | bd704db | 在 | …`，`problems=0`。

复算：`python console/_citations.py --rewrite-report --verify` rc=0
（`objects=151 reachable=128 unreachable=23 pairs=18 pending=0 problems=0`）。
全套 `Ran 226 tests in 96.273s OK`；`release_check.py rc=0`（117.8 s，`[FAIL]` 计数 0，
`WARN_CENSUS warnings=ResourceWarning:0 带出处=0 全文提及=3 suite=226`）。
VERSION 仍 1.0.0、无 remote 故未 push、paper/ 未碰、对外产物未动。

### 2026-10-02：结项 68 次重跑了一遍 —— "不可比"的证据一半是我自己的测量错误

`run_conclusion.py --preset conclusion`（`.venv310` / Python 3.10.11）rc=0、68/68 成功，
落在 `results/experiments/conclusion_20261001-234945/`（gitignored）。**没加** `--publish-latest`、
**没加** `--record-into-evidence` ⇒ `one_click_latest.csv` 与 plots 那 15 个入库产物原样未动。

核验走的是 `verify_data_provenance.check_experiments` **自己的判据**（把它的 `EXP_DIR` 临时指到
新目录，不抄第二份实现）：新旧两目录各自 rc=0 —— raw 68 ↔ plan 68 一一对应、失败运行 0、
四算法配对 seed 均 101–105、stats 120 格逐位可重算（最大偏差 2.2e-16）。

但按 (算法,seed) 配对的 480 格里只有 **203 格相等、277 格不等**。我当场给了三条"盘上证据"，
第二天复查时**第 ③ 条被我自己推翻**（下面这段就是那次更正）：

① `config/simulation.json` 哈希不同（旧 `548579a…` / 新 `8a2f254…`），差异是 `dfb3dcf` 删掉的
   `detour_penalty_weight`；**该键已用受控重跑证明不承重** —— A 面当前配置、B 面只往 `task_chain`
   加回这一个键（两侧先过前置门：`added={"task_chain.detour_penalty_weight":1.0} removed=0 changed=0`），
   同一棵树同一 `greedy/seed=101/steps=3600` 各跑 3 次，指标指纹（24 个数值列到 1e-9）逐格相同
   ⇒ **这条哈希差不能用来解释新旧指标差**。仓内 `config/simulation.json` 一个字节未动
   （跑完复核 sha 仍是 `8a2f254c5cbe`、`git status` 空）。
② 每 run 耗时从 11.77–39.28 s（合计 1672 s）变成 1.53–1.85–4.94 s（合计 139 s）。
   **我先给的"未解释"、再给的"每步快 11.9–12.1 倍"，两个版本都不成立 —— 后者已作废。**
   归一化确实排除了"终止早晚"（两批 68 个 worker 的 `episode_steps` 全部恒为 3600），
   但同一个 `HEAD` 树连跑三次是 12.35 → 2.81 → 1.91 s（冷桶/温桶差 6.5 倍），
   而批次里**第一格是冷的、后面全是温的** ⇒ 我那个比值吃的是混合态，不是干净测量。
   单格消融（`git archive <ref> | tar -x` 解到 `%TEMP%`，同一份 greedy/seed=101/steps=3600 预设，
   不动 `.git`、不建 worktree）留下两句逐位证实的话：
   `dc5c2b0 31.82s → a57f83a^ 31.11 → 3c8f782 20.53（×1.52，进程内几何指纹共享桶）
   → 638cffe 15.44（×1.33，桶落盘跨进程）`；以及"同 seed 的指标换了"这一跳
   （总步数 2274→2049、超时率 0.0833→0.0667）⇒ 旧那批测的不是当前代码的行为，这条从线索升为实测。
   **注：这一跳当时被我记成 `6b8c4c8`，那是错的** —— 补跑父提交后定到 `4d956e6`，见本节开头。
   "哪一次改动让它快 N 倍"这种单点指认不再给：加速来自两次缓存机制叠加 + 一个不可比的环境态。
③ ~~地图解析计数变了（2876/397/108 → 2889/25/18），OSM 文件字节相同 ⇒ 环境漂移~~
   **撤回。** 真相是**打印那三个数的代码在两批之间改过**：旧批钉 `fcc7c5f`，那时那一行是
   `print(f"加载了 {len(self.high_buildings)} 个具有高度信息的建筑物")` —— 只印一个数且标签是错的；
   `66016b7`（2026-09-29 12:01，提交信息正是「两处日志把『避障碰撞体数』说成『具有高度信息的建筑数』」）
   换成现在的三数行（`frontend/environment.py:276`）。那两套数分别是 **fallback** 与 **osmnx**
   两条加载路径的计数，而 `provenance_baseline.json`（measured_at 2026-09-29）**两套都钉着** ——
   我没读它就先下了结论。本轮实测 `python verify_data_provenance.py --loader` **rc=0**
   （`mode=osmnx：fallback 碰撞体=108，当前路径=18；基线 108 / 18`）⇒ **环境没有漂移**。
   中间那版归因（`.osm_cache` 陈旧缓存复用）也作废：缓存键含源文件 `mtime_ns`
   （`frontend/tools/osm.py:_cache_path`），四个 `osm-*.pkl` 都不是本轮算出的键，跑完也没有新增。

**教训落在判据上**：跨时间比读数之前，先确认产生这行读数的代码是不是同一份
（`git log -S<那行文案>` 一条命令就能查出标签变更）。旧批 manifest 是 `schema_version: 1`，
不含 loader 读数 ⇒ "旧批走的哪条加载路径"**盘上无证人**，只能记为未记录，不许反推。
因此"新旧不可比"现在只剩第 ① 条支撑，且它自己还没被证明承重 —— 登记簿里那句"要不要替换对外指向"
的判断依据比上一版弱，别按原话拍。

读数形状（GA vs Greedy，各 5 seed）：完成率都 1.0000；超时率 0.0733 vs 0.0533；
平均时延 5.400±5.386 vs 4.302±2.573；**GA 平均时延优于 Greedy 的 seed 数 = 3/5（旧那批也是 3/5）**
—— 标准差大于均值的五样本，撑不起"稳定更优"。全部细节与复算命令写在
`docs/数据来源与可追溯性登记表.md` 新增的「R3 的重跑轮」一节，三件待拍事项（要不要换对外指向、
要不要先查 ③ 的成因、`verify_data_provenance.py:38` 的 `EXP_DIR` 换不换）都在那一节里，我没替拍。

边界：`VERSION` 仍 `1.0.0`、未 push（本仓无 remote）、无新依赖、未动 DDL、`paper/` 未碰、
`.git` 内未动、那 5 张未入库 PNG 未删、未结束他人进程。

### 2026-09-30：引用门禁自己就是半盲的那一道门（承 2026-09-30 上午那条）

`VERSION` 保持 `1.0.0` 未动，未打 tag、未发 release、未 push。

上一轮加的引用门禁（判 `路径:行号` 能不能翻到）跑在全绿，但我照它扫不到的地方一查，
**它自己就是假绿灯的那一类**：

1. **旧正则只认 `:123`。** 登记簿里 `:118-121`、`:141-145,153,195` 这类写法一条都没进断言。
   把 HEAD 的文档喂给新判据：`58 条引用里 5 条立刻红`，其中 1 条指向 6b8c4c8 已删除的
   `frontend/map_drawer_3d.py` 却不带 `已移除@` 标注 —— 旧门不是"没报错"，是**根本没看见**。
2. **只判"文件存在 + 行号不越界"挡不住行号在范围内却指向别处。** 逐条对着盘上内容核，
   参数表 / 指标表几乎每行都中招：P1 抄 `:112` 实为 `:88`（`:112` 是另一台机型的续航）、
   M1 抄 `:926` 实为 `:921`、M5 抄 `:861-863` 实为 `:857-859`（`:861` 是空载率不是利用率）、
   `server.py:911-923` 实为 `:849-855`，且那一行宣称的"6 份 CSV / 目录 8 份"现为 **5 / 7**。

**对策（`console/_citations.py`，判据只留一份实现，用例按路径加载它）：**
引用支持区间与多段；新增 `#锚点` —— 被引行必须含这段字，
`config/simulation.json:88#carrying_capacity` 这种写法在行号漂走时会红。
汇总行印「扫到几条 / 其中几条带锚点」，没带锚点的仍只判越界，**不把这条门当全覆盖**；
`release_check.py` 现在每次发布检查都把它跑一遍，`--verify` 不一致退出码 1。

**顺带清掉两笔自己的欠账：** MARL 撤除（6b8c4c8）后 README 还剩两处「五类」，
而 `experiments/runner.py` 的合法算法集合只有 greedy/ga/ortools/pso 四个，第五类是被移除的
MARL —— 那句"四类算法统一评测"当时改对了，这两处漏了，现已改为四类；
`frontend/environment.py` 那句"加载了 N 个具有高度信息的建筑物"（把 >20 m 碰撞体数
说成有高度建筑数）也早已改成三数分印，登记簿里指它的那两处记载（第三节建筑高度的第 2 条、
P2 清单第 10 条）与"待你拍板"那条 MARL 处置，都就地标注为已完成。

**同一轮里更糟的一条：数字可能来自盘上不存在的代码。** 收尾复跑时系统 python 报
`console/test_run_determinism` 7 个错，栈里那一行 `env = _load()` 在当前源文件里 grep
命中 0 次 —— 它跑的是一个 `cpython-313.pyc`。CPython 默认按 **(源文件 mtime, size)**
判缓存过期：内容改了但 mtime 被按回旧值（`cp -p`、还原备份、部分同步盘就是这么干的）、
长度又没变，旧字节码就"仍然相符"。于是 README 的用例数、skip 归因、`release_check` 的 OK
全可能是在测缓存而不是代码。
现在计数/skip 归因/发布检查起的子进程统一走 `console/_preflight.py:isolated_env()`
（`PYTHONPYCACHEPREFIX` 指到树外 + 不写字节码），读不到旧缓存就只能从源码编译；
`console/test_stale_bytecode.py` 先用一个等长改写的探针**复现**"旧缓存盖住现源码"
（不复现就不知道这扇门在防什么），再断言 `isolated_env()` 挡得住它。
清掉那个旧 pyc 后同一条命令 `OK (skipped=2)`；两个解释器的用例数在缓存隔离下重测过，
与隔离前报的一致 —— 也就是说本轮印出去的那些数不是缓存产物（具体条数以
`python console/_readme_counts.py --verify` 现印为准）。

**没有验证的**：锚点目前只覆盖部分引用（条数以 `python console/_citations.py` 现印为准，
抄进文档就又会过期），其余仍是只判越界；论文图仍拿 600 步 GA 与 2000 步基线并列，
未按要求重跑 3600 步 / 5 回合 / seed 101–105 前不可重生成。


### 同日续一：把输入地图本身钉住（此前只钉结论、没钉输入）

`provenance_baseline.json` 早就钉住了加载器在 `frontend/data/map/part_of_yangpu.osm` 上
跑出来的观测值（2889 栋 / 2864 个 NaN / 18 个碰撞体），登记簿那一整片"实测"数字也都来自它，
但**没有任何地方钉住被读的那个 .osm 本身** —— 上一轮我回答"基线里钉的是什么哈希、谁来断言"时
说清了观测值有断言、输入文件没有，这条欠账本轮补上：

- `verify_data_provenance.py` 新增 `check_mapfile` / `--mapfile` / `--write-mapfile-baseline`，
  分块现算 sha256（文件 11,098,582 字节，不整份进内存）与基线比；不一致就 FAIL 并**把实测哈希印出来**，
  同时写清后果：地图类结论全部需重跑。默认全量核对里已占一格。
- `console/test_mapfile_pinned.py` 5 条，其中三条专门证明这道门不是空转：
  把基线里的哈希改错一位 -> 必须红且红字里含实测值；删掉该字段 -> 红且报警直接给出采集命令；
  拿同一张图的**前半截**当核对对象 -> 必须红（若 `check_mapfile` 只是把基线值抄回来，这里就会绿）。
- 登记簿第五节加 R7 行记录这件事本身（"原先没钉"是缺陷，不是遗漏的细节）。

现况：`python verify_data_provenance.py` 退出码 0，输出含
`[OK] MAPFILE frontend/data/map/part_of_yangpu.osm sha256=72c3ef9ca19c…（11098582 字节）与基线一致`。




### 同日续二：6b8c4c8 撤除 MARL 时漏了 `results/compare/plots/`，该目录已就地标作废

追"plots 归档 20 与 15 的差额"时挖出来的，比差额严重：

- 那 3 份派生表的算法列是 **10 个** —— greedy/pso/ga/ortools 之外还带
  `iql` / `iql_u` / `vdn` / `vdn_u` / `qmix` / `qmix_u`，正是登记表 R2 逐格证伪、
  并在 6b8c4c8 从数据源与对比页撤掉的那六行；12 张 PNG 同批。
- "撤除没到达这里"不是我推测的，是 git 自己说的 —— 但**按 15 件产物逐件问**
  （3 份派生表 + 12 张 PNG，最后一次入库改动都是 `fcc7c5f`，2026-09-11，
  且 `git merge-base --is-ancestor fcc7c5f 6b8c4c8` 成立）。
  一开始我写的是问"整个目录"的最后一次改动，结果把作废通知提交进那个目录之后
  这条断言立刻自翻 —— 目录的最新提交变成了"写这张纸"本身。判据问的是产物还是记录动作，
  这是本轮自己踩到的一次，`console/test_plots_archive_void.py` 里留了注释。
- 同目录还并存**两份口径不同的 GA**：归档表里 `ga` = 2000 步 / 60 任务，
  入库的 `backend_ga_metrics.csv` = 400/600 步、22/30 任务 —— 图上那根 GA 柱说不清来源。
- 顺带纠正 README 的一处说法：原文写"加 `--record-into-evidence` 跑一次"就能补齐，
  实测今天这条**先被口径门禁拒绝**（`plot_compare_metrics.py` 退出码 1，`[REFUSED]` 开头），
  必须先按结项口径重跑 GA 才谈得上重生。已把顺序写进 `results/compare/plots/README.md`。

处置按"要么重生、要么标注作废，不许两边共存"走作废那条路（重生今天做不到）：
目录里放 `README.md` 逐个点名六个算法 + 证据 + 补齐顺序，并由
`console/test_plots_archive_void.py` 5 条断言盯住。**双向**：归档还是那 10 行时绿；
哪天清掉 MARL 行重生了目录，测试红并指名要撤销这份作废通知 —— 单向断言会把"作废"
永久钉在已经修好的产物上，那也是一种过期。另有一条断言把"撤除未到达"这件事本身
交给 `git merge-base` 去证，不靠人记。

登记簿第五节新增 R8 记录本条。



### 同日续三：锚点补到全覆盖，新约定当场被自己的门抓了一个 bug

把剩下 9 条没带锚点的引用补完（4 条指向已删文件的历史引用补锚点、3 条历史行号、
2 条 README 里的历史提及）。其中那 3 条 `environment.py:282` 更难看：
**它在任何修订里都不是那行** —— `4d8ac93` 是 :195，修复前的 `66016b7^` 是 :268，
说明这个行号从写下那天起就是抄错的，而旧门只会判"282 在文件行数以内"。
为此加了 `已失效@<sha>` 约定（文件还在、但引的是那次修复之前的行号，
正文按 `git show <sha>^:<path>` 核对，且**必须**带锚点 —— 历史行号没法跟磁盘比）。

新约定写完第一件事就被门自己判红 3 条：标注原先按**整行**找，一行里同时有
"历史行号"和"现状行号"时，历史标注会连坐到现状那条头上，把它判去跟旧修订比内容，
于是报出**假的失效**。改成"标注只对它紧跟的那条引用生效"后，68/68 全覆盖、退出码 0；
`test_obsolete_marker_is_bound_to_its_own_citation` 钉住这条连坐 bug，
`test_obsolete_marker_branches_go_red_when_wrong` 钉住四种错法都该红。

另一条 README 里的深行号引用（`README.md:449#四类算法`）在同一轮里被 README 插行
漂走、当场判红 —— 说明**正文深行号天生不适合当引用目标**，已改成按节描述，
同处保留 `README.md:13#四类调度方法` 与 `experiments/runner.py:95#valid` 两条可核对的证据。

### 同日续四：字节码纪律只覆盖了一半，补另一半时又踩出一个把仓库弄脏的 bug

`isolated_env()` 只治**子进程**。同进程里的 `import` 与
`importlib.util.spec_from_file_location` 不受它影响 —— 而按路径加载内核的
`load_kernel_environment()` 走的正是后者。夹具实测（A 编译出 `.pyc` -> 保留 mtime
写入内容不同的等长 B）：

```
① 同进程 importlib（默认环境）   -> 读到 A   ← 缺口是真的，不是想象
② 子进程带 PYTHONPYCACHEPREFIX   -> 读到 B
③ 同进程先设 sys.pycache_prefix  -> 读到 B   ← 这才是该补的地方
```

于是纪律改成两半都有：7 个入口脚本（`release_check.py`、`verify_data_provenance.py`、
`console/_preflight.py`、`console/_citations.py`、`console/_readme_counts.py`、
`results/compare_gate.py`、`results/plot_compare_metrics.py`）在任何本仓 import **之前**
各写两行裸赋值。为什么宁可复制 7 份也不抽函数：抽函数就意味着先 import 本仓某个模块，
而那次 import 本身就可能吃到过期缓存 —— 先有鸡的问题，只能就地写。

补的过程中我自己造了第二个 bug，被自己新加的断言抓到：前缀原先指在 `ROOT/.pyc-offstage`，
而 `release_check` 第一件事是 `compileall.compile_dir` —— **它显式写缓存，
`dont_write_bytecode` 挡不住它**，于是在仓库里长出 77 个 `.pyc` 的深层目录
（git 都被 "Filename too long" 噎住）。前缀改为系统临时目录下**每次运行唯一**的子目录：
读必 miss、写下的不会被下一次当成"相符"的旧缓存、仓库也不再被弄脏。
固定路径那种写法等于把同一个坑换个地方挖，所以唯一性也有一条断言（两次运行前缀不同）。

`console/test_stale_bytecode.py` 从 4 条涨到 8 条，新加的问的都是行为而不是文本：
① 复现同进程缺口，再逐个入口真跑一遍证明它关上了；
② 读解释器**当前的** `sys.dont_write_bytecode` / `sys.pycache_prefix`，
   不看启动命令里写了什么（被 `-E` 或 sitecustomize 改回去照样红）；
③ 真跑一次带纪律的 `compileall`，再数仓库里有没有多出文件；
④ 入口清单设 6 条下限 —— 两处循环都遍历它，清单被清空时断言会"零次通过"。

`python release_check.py` 多印一行「字节码纪律（跑绿的前提）」，实测
`dont_write_bytecode=True pycache_prefix=树外；子进程回报=True|True`。另外把错值**真写进**
`provenance_baseline.json` 跑过一次：sha256 与 `paths.osmnx.buildings` 各自都能让
`verify_data_provenance.py` 退出码变 1 并把实测值印出来，跑完按字节还原（cmp 一致）。
结论一句话：**没声明字节码纪律的"跑绿了"，只能算未验证。**

### 同日续五：一条永不运行的门 + 一个把真兜底洗白的散文豁免

回答「这些断言删掉哪个行为会变」时，顺手把那条门自己测了一遍，结果两条都是真的：

① **`test_every_entry_point_resolves_to_the_same_number` 在两个解释器下都 skip。**
   上一轮把 `import environment` 改成按文件路径加载之后，内核自己的扁平 import
   （`from drone import ...`）找不到同级模块，报 `ModuleNotFoundError: No module named 'drone'`，
   而 except 分支一律 skipTest —— 于是**它从来没跑过**，venv 里也一样。修法是加载时临时把
   `frontend/` 放进 sys.path（用完还原，仍断言 `module.__file__` 就是那个文件），并把 skip
   收窄成只在缺**第三方依赖**时成立，缺本仓模块就是 fail。现在 venv 6 例全跑、无 skip；
   系统 python 因缺 numpy 才是 skip。「一条总是绿的门」和「一条总是 skip 的门」是同一件事：
   都在假装把关。

② 静态扫描器原先按整行放行：`if "原先" in line or "历史上" in line or "不再" in line: continue`。
   放一行 `PROBE_A = cfg.get("episode_max_steps", 1200)   # 不再使用` 进被扫目录，扫描**照样 OK**
   —— 一个词就能洗白一条真兜底，正是「修完假红换来假绿」。改成按语法事实放行：用 ast 只抹
   **作为语句出现的字符串**（docstring 与孤立文本）和 tokenize 的注释列，代码里的字符串字面量
   原样保留（`cfg.get("episode_max_steps", 1200)` 的键名本身就是字符串，抹了它就是漏检）；
   解析失败退回整行，宁可多报不可漏报。`_samples()` 的 11 条样本走的是与真文件完全相同的判据，
   含「含 `#` 的字符串不该截断后面的兜底」与两条 docstring 散文放行。本文件也不整文件豁免：
   豁免范围由 ast 现算成 `_samples()` 的函数体行号。

③ 顺带回答那两个下界：`assertGreater(nfiles, 0)` / `assertGreater(ntests, 10)` 删掉之后，
   「发现机制全坏 + 恰好跑过一次 `--fix`」这条路径会让 README 抄成 0/0 且门永久绿；
   `test_no_numeric_fallback_left_in_sources` 的 `nfiles > 50` 同理（清单为空时
   offenders 必然为空，那是零次通过不是通过）。这三条都是挡"门自己失效"的，不是挡代码的。

现况：venv `Ran 164 tests OK`（无 skip）、系统 python `Ran 111 tests OK (skipped=12)`、
`_citations.py --verify` 68/68、`release_check.py` 退出码 0。

### 同日续六：陌生人照第一条应用命令跑，缺依赖时拿到的是满屏栈

A 项（干净 shell、只读 README 第一段）实测：

- `cd frontend && python evaluate_metrics.py --policy ga --episodes 1 --episode-steps 600
  --seed 100` 用系统 python 就能跑完，退出码 0，输出与 README 示例**逐位吻合**
  （完成率 0.7667 / 超时率 0.0435 / 平均时延 0.4565 / 完成 23/30 / 利用率 0.705 与 .4f 的
  0.7045 / 空载率 0.498 与 0.4984 / 顺路 5 / 绕飞 7），只写
  `results/adhoc/backend_ga_metrics.csv`，跑完 `git status --porcelain` 为空 ——
  文档那句"会写到哪"是真的，不需要背景知识也能跑完。
- 一处对不上：本机 `.venv310` 在仓库**外面**（父目录），README 教的
  `python -m venv .venv310` + `source .venv310/bin/activate` 照敲在这台机器上不成立
  （工具两个位置都认，文档只写了一个）。
- 缺依赖的表现不一致：`console.run` 与 `console.selfcheck` 早就打印可读前置检查并退出码 2，
  而 README 第一条**应用**命令 `evaluate_metrics.py` 直接抛
  `ModuleNotFoundError: No module named 'shapely'` —— 评审会读成"仿真坏了"。

补 `_preflight.guard_or_exit()`，退出码 3（与 0/1/2 分开），打印缺的包名、项目解释器绝对路径
与**同一条命令**的重跑写法；只补这一个入口，另两个已有自己的前置检查。

顺带修掉我自己造成的连带失败：`test_run_determinism` 与 `test_readme_command_side_effects`
原先用 `"No module named" in out` 识别"这台机器跑不了"。哨兵把 traceback 换成一句人话后
这个匹配失效，3 条用例当场从 skip 变 FAIL —— **判据寄生在报错文案上，文案一好它就坏**。
统一成 `_preflight.env_shortfall(rc, out)`（认退出码 3、统一标题，旧字样向后兼容），
两处调用点都换掉；修完系统 python `Ran 111 tests OK (skipped=12)`。

顺手量了一下这件事的暴露面：仓库第一方代码里现有 **325 个** `.pyc`，
每一个都与其源码的 (mtime,size) 相符 —— 也就是 325 处"缓存说了算"的地方。

现况：venv `Ran 164 tests OK`、系统 python `Ran 111 tests OK (skipped=12)`、experiments 24 OK、
`_citations --verify` 68/68、`_readme_counts --verify` 一致、`release_check.py` 退出码 0。

### 同日续七：上一轮那条门自己没记账；这一轮把同一把尺子伸进 `paper/`（只报不改）

**先记一笔自己的欠账。** 加行集合差异表与"引用必须声明行集合"那笔提交（现 `ab830e7`，
改写前的旧号 `370b9fc` 还在 reflog 里）
**当时没写 CHANGELOG 小节** —— README、登记表、`results/compare/plots/README.md` 都跟着改了，
唯独这本流水漏了。这正是这一整轮在修的那类东西：文档说做过，但记录里翻不到。补上摘要：

- 量出来的结论：作废目录那三份派生表 **27 个统计量里 22 个**在 `core4` / `all10` 两种行集合下
  读数不同（`Weighted Overall Score` 0.833768 vs 0.588907，差 −0.244861；`Total Energy`
  13699.87 vs 61220.86；`Priority-1 Average Delay` 0.000000 vs 9.705890）。
  全表由 `results/row_set_delta.py --write` 生成、`--verify` 不一致退出码 1，
  落 `results/compare/plots/ROW_SETS.md`（禁止手改）。
- 引用作废产物的每一行必须紧跟 `行集=core4` 或 `行集=all10`；声明 `all10` 还要与表里
  实际算法集合相符 —— 表重生成后标注自己会红（双向）。
- 剩下 5 列两读数相同（`Generated Tasks`、`Berth Utilization Rate`、`Nest Turnover Rate`、
  `Avg Berth Wait Time`、`Total Swap Sessions`）。**这条只当线索，不当结论**：
  同值不代表该列不该声明行集合，只代表这一批数据上它恰好没差。

**这一轮：同一把尺子伸进 `paper/`，但只报不改。** `console/_paperscan.py` 扫
`main.tex` 与 `paper/figure/*`，产出 `docs/论文侧撤除未达清单.md`
（`--paper-report --write` 生成、`--paper-report --verify` 逐字节不一致退出码 1），
并接进 `console/_citations.py --verify` 那条总门 —— 现在 `--verify` 一次核三件事：
文档引用、作废产物行集合标注、论文侧清单是否还是代码现在算出来的那份。

**为什么必须分类，而不是"见名就报"。** `IQL / VDN / QMIX` 在论文里有两种身份：

- **待作者定夺 17 处** —— 结果表里那六行数据、伪代码表的图注、以及摘要/关键词/贡献/方法/
  结论里"我们评了这六个"的正文主张（逐条行号见清单，这里刻意不重抄：重抄一遍就是
  再造一个没人核对的手抄值，而清单本身是逐字节核过的）；
- **合法 6 处** —— 「相关工作」里引 Qie et al. 等别人方法的三行、文献条目
  （`\bibitem{qmix}` 那一段）三行。

把两类混成一锅报，下一轮为了变绿就会去删**真的相关工作引用** —— 那是比重复数字更坏的修法。
所以分类本身就是判据：`console/test_paper_void_scan.py` 双向钉（待夺类漏报要红、
合法类误报也要红），四条变异实测都变红 —— 放宽 `RELATED_HINTS` 含 introduction（红 3）、
默认分类改成合法（红 4）、正则改成手抄（红 1）、去掉词边界（红 1）。
词边界那条不是装饰：`QMIXv2`、`preQMIX`、`dynamically` 都会被子串匹配算成"已撤除的数据行"。

**算法名单不再手抄。** `NAME_RE` 现在由 `console/_rowsets.py:WITHDRAWN` 现算
（`qmix_u` → `QMIX-U`），改那边一个键这边就跟着变；用例既验现值全覆盖，也验 `name_re()`
真的按传入集合算 —— 清单顶部那句"同一把尺子"因此是可证伪的，不是一句话。

**清单里那句"撤除从未到达论文"是算出来的**（同一用例核逐字节）：`6b8c4c8` 动过 `paper/`
的文件数 = **0**，`main.tex` 最后一次入库改动停在 `4d8ac93`（2026-09-08），
10 张图最后一次改动全部早于该撤除。图的**像素内容未单独核验** —— 位图读不出列，
这道门能核的只有入库批次；这条欠账长期挂着的前提，是引用它的每一行都声明了行集合。

**README 里去掉一个必然过期的数字**：`docs/` 那行原本写"16 份文档"，我新增一份它就错了
（而且这类"份数"上一轮已经错过一次），改成不写份数、逐份看文末索引。

现况：venv `Ran 178 tests OK`（20 个文件，无 skip）、experiments `Ran 24 tests OK`、
`_citations --verify` 68/68 带锚点 + 作废引用 3/3 已声明 + 论文清单逐字节一致、
`_readme_counts --verify` 一致（console=20/178、experiments=2/24）、`release_check.py` 退出码 0。

### 同日续八：一条门禁模块只要被 import 就喷脏话；以及"红得没人读得懂"也算坏

两件都是别人跑我的产物时发现的，不是我跑出来的 —— 这个区别很重要，写在下面。

**① `_paperscan.py` 的 docstring 里写了 `\cite` 而没加 `r`。**
别人跑 `python -m unittest console.test_paper_void_scan` 时，输出里多了一行
`_paperscan.py:5: SyntaxWarning: invalid escape sequence '\c'`：
**一个门禁模块只要被 import 就喷一行噪声**，而它自己那条"输出要干净"的门当然也看不见自己。
改成 `r"""`。

顺手普查这个类别，并且**先认错**：我第一遍扫出来是 0 命中，判据是
`issubclass(x.category, SyntaxWarning)` —— 而 3.10 对这一类抛的是 **DeprecationWarning**
（3.12+ 才升成 SyntaxWarning），所以那台机器上量具整个是瞎的。第二次扫把类别去掉、只按
消息文本匹配，并把 `results/`、`experiments/` 这些生成器目录纳入范围（82 个 `.py`）：
**1 处命中，就是 `_paperscan.py`**；改成 raw 后归零。
量具本身也证了非空转：把那个 docstring 改回非 raw → 立刻 1 条命中，改回来 → 0 条。
这一类**没有新增门禁**（他只要"一句命中数"），加了就是为假想场景盖层。

**② 更要紧的一条：我的门在这台机上"红得读不懂"。**
同一次运行里那行 warning 中的中文整片变成 `??????`（GBK 系通道 vs UTF-8）。
这不是我的 bug，但后果是真的：**门报红时如果诊断只有中文，值班的人看得见 `[FAIL]`、
看不见它在说什么** —— 那这条门在真事故时等于没有。

三个选项里选了 ②（关键诊断行附 ASCII 短码），没选 ①/③，理由具体：
`_citations.py` 已经在 `main()` 里 `sys.stdout.reconfigure(encoding="utf-8")`，
① 对该模块自己无效，而"被重定向到管道/文件"才是别人实际遇到中文丢失的通道；
③ 会造出第二个事实源（一份 UTF-8 log 与屏幕上的红互不核对），是新的漂移面。
所以形状固定为：

    [FAIL][<ASCII 短码>] <文档>:<行> <ASCII 事实> | fix: <ASCII 方向><中文解释>

新门 `console/test_gate_ascii_diagnostics.py`（5 条）钉三层，都由变异证过生效：
- **每条判据都能被真的弄红**（8 条引用样本 + 2 条行集合样本 + paper 三条分支），
  且整行 `.encode("ascii","replace")` 之后短码、`文档:行`、`| fix:` 仍在；
- **非空转**在两侧都断：中文必须*确实丢掉*（`faded != msg`），
  且样本必须*恰好*弄红一条（第一版样本把 `已失效@` 写进了反引号里，
  CITE 整条匹配不上，于是 5 个样本全绿 —— 是"样本没生效"而不是"判据坏"，靠这条抓到）；
- **短码表与实发短码互印**：`_citations.py` 头部那张表的 14 个短码，
  少发一个红、多发一个也红（防止代码换了叫法而表还在讲旧故事）。
四次变异实测：摘掉 `[ANCHOR_MISS]` 前缀（红 2）、摘掉 `| fix:`（红 1）、
把表里一行改名（红 1）、成功行退回纯中文（红 2）；`_citations.py` 还原后逐字节相同。

**改文案把自己的旧用例打红了 4 条 —— 同一课第二次上。**
`test_compare_gate` 里三条、`test_plots_archive_void` 里一条，断言写的是
`assertIn("找不到", ...)`、`assertIn("却不带 #锚点", ...)`、`assertIn("过期", ...)`：
判据寄生在**中文文案**上，文案一改成 ASCII 优先就当场假红。
这与上一轮 `_preflight.env_shortfall()`（判据寄生在报错文案上，文案一好人就坏）是同一个错误，
只是这次犯在我自己的门禁用例上。全部改成断言短码，并因此多拿到一处判别力：
磁盘分支与历史分支旧文案都写"找不到锚点"，分不出来；现在分别是
`[ANCHOR_MISS]` 与 `[ANCHOR_MISS_HISTORY]`，摘掉 `已失效@` 标注后走哪条支路是可断言的。

**欠账照旧（不混进这条）**：`.venv310` 在仓库外而 README 教的是仓内形式（一句话定性已在
同日续六记下）；GA 按结项口径重跑（3600 步 / 5 回合 / seed 101–105）排在 `paper/` 那条之后；
`release_check.py` 已重跑退出码 0（同日续六里那句"退出码 0"是修剪 CHANGELOG 之前测的，
现在这句是修剪之后重测的）。

**③ 提交信息里的 shell 残文：只改 message、树未变，全过程留痕。**
`4520523` 的 message 尾部混进了 `MSG; git status --porcelain; echo "[STATUS-END]"` ——
heredoc 的收尾行写成 `MSG; <命令>` 时 bash 不认它是定界符，整行被当正文吞进 commit。
它不是 HEAD，`--amend` 够不着，所以用 `commit-tree` 按原 tree/parent/author/committer
重落，最后一步才 `update-ref`（带 old-value 守卫）。普查用了 `^MSG;` 这个通用形状
（不是那一条字面量），全仓 106 条提交里命中 **3 条**，其中 2 条已处理：

| 旧 sha | 新 sha | 做了什么 |
|---|---|---|
| `4520523` | `328b6f4` → `873f069` | 删去尾部那行 shell 残文（两轮改写各换一次指针） |
| `2294adc` | `007be71` → `b9d37c7` | 同一形状的另一条：`MSG; git status -sb \| head -3` |
| `370b9fc` | `6f83007` → `ab830e7` | message 一个字节没动，只因父提交被重落而换指针 |
| `2550328` | `5d3d153` → `4adc947` | 同上 |
| `76825e0` | — → `1fc3425` | 同上（第三轮待批的那条链里） |
| `e3b7db8` | **未处理，等你拍板** | 尾部一行 `MSG; PYTHONIOENCODING=utf-8 …… echo "[END]"`；它在更前面，改它要把上面 6 个指针一起重落 |

断言（每一条都跑过、不是叙述）：`git diff <旧HEAD> <新HEAD>` 为空、`rev-parse ^{tree}`
逐条相同、author/committer 与时间戳原样、未改动的提交 message 逐字节相同、
`git rev-list --count origin/master..main` 改前改后都是 **42**（一条没多没少）、
工作区状态改写前后逐行相同。安全闸门：每条被重落的提交都先验过
`merge-base --is-ancestor <sha> origin/master` **不成立** —— 推出去的历史不改写。
旧链仍在 reflog 里（`git reflog` 可见 `370b9fc`/`6f83007`），可回退。
**旧 sha → 现 sha 的完整映射表（含复算式与自查块）见 `docs/提交改写映射表.md`。**
实测规模（现算，别抄这里的说法）：两轮 apply 让 **4 条**提交换了活 sha
（`007be71`/`5d3d153`/`873f069`/`ab830e7`），另有 **12 个** sha 不可达但对象仍在 ——
4 条原始 + 2 条第一轮产物 + 6 条**只跑过 dry-run** 的那轮造的（`72aa7ca`/`1fc3425`/
`b9d37c7`/`4adc947`/`5b4048b`/`9fc3be5`，从未上链）。最后这 6 个是我这张表最初写错的地方：
我把 dry-run 对象当成了"现 sha"填进去，是那张表自己的 `git log --grep` 复算式抓出来的。
外部台账若引用过其中任何一个，按那张表的第二节换过去。
规则同批生效：**多行 message 一律 `git commit -F <文件>`，不再用内嵌 heredoc。**

### 同日续九：把"本轮手动跑的一次普查"做成常驻门（只这一件）

上一轮那句"82 个 `.py` 里命中 1、修完归零"是**手动一次性普查**，不是门 —— 它只会在我恰好
跑它的那一次为真。这轮做成 `console/test_source_escape_sequences.py`（3 条用例）：

- **机制自己选**：逐文件 `compile(src, path, "exec")` 包在
  `warnings.catch_warnings(record=True)` 里并**强制 `simplefilter("always")`**；
  命中只看**消息文本** `invalid escape sequence`。理由的两档解释器实测表写在模块注释里：
  3.10 抛 `DeprecationWarning`、3.13 抛 `SyntaxWarning`；裸进程不加 `always` 时 3.10 记到 **0 条**；
  **同一模块第二次 import 吃 `.pyc` 缓存后 0 条** ⇒ `-W error` 与"跑一次没喷"都不能当证据。
- **范围下限**：`FLOOR = 80`（实测 83 个 `.py`）。塌到下限以下直接红，且报警写明
  "是**扫描范围塌了**，不是没有缺陷" —— 没有下限的扫描只会永远绿。
- **普查数印在行上**：`[ESCAPE_CENSUS] py_files=83 hits=0 floor=80 broken=0`，
  外加 `broken`（compile 不过的文件）必须为 0 —— 编不过不能算"这个文件没问题"。
- **两面夹具**：植一条非 raw 的 `\cite` 必红（含"真放进被扫目录、走完整 `scan_repo()`"那条，
  只测函数挡不住"目录名单把第一方排除了"这类失效）；当前仓必绿；raw 反面样本必须 0 命中。
- **变异 5 条，连没咬到的那条一起报**：匹配只认 `SyntaxWarning` 类别（红 2）、
  下限抬到 9999（红 1）、反面样本丢掉 r 前缀（红 1）、判据乱抓每文件塞一条假命中（红 2）、
  **摘掉 `simplefilter("always")`（不红）**。最后一条不红是实测出来的原因：
  unittest 进程自己给 `DeprecationWarning` 开了滤镜。所以那行是**抗环境保险**，
  不是被判据抓到的 bug —— 模块注释②与用例文档里都明写"这条没被变异证明"，不占功。

**我自己在这条上写坏过两处，两处都是当场被抓**：
① 反面样本写成 `r'…'` 再去拼接 —— 那只让我这边的字面量变 raw，**产出的源码里没有 r**，
   于是"应当 0 命中"的对照组带着 1 条命中回来，用例判红。这就是假对照组。
② 新门的模块注释里嵌了三引号示例，把 docstring 提前终止成 `SyntaxError`；
   而同一次运行我打的 `echo "gate rc=$?"` 取到的是管道尾巴（`tail`）的退出码，不是测试的。
   同一个坑本轮第二次踩，写在这儿当账。

**另一次操作自报**：那批变异脚本用 Python 去读 bash 的 `/tmp` 备份路径 —— Windows Python
不认 `/tmp`，脚本崩在还原那一步，把 `console/test_source_escape_sequences.py` 留在了
"摘掉 `simplefilter`"的变异态。发现后从备份还原，用 `cmp -s` 与 sha256 双向确认逐字节相同，
之后改用 `tempfile.gettempdir()` 的绝对路径。教训是流程级的：**改盘上文件之前，
还原那一步必须做成不可能失败**（备份路径两侧同源），否则变异本身就是事故源。

现况：venv `Ran 181 tests OK`（21 个文件，无 skip）、experiments `Ran 24 tests OK`、
`_citations --verify` 68/68 带锚点 + 作废引用 3/3 已声明 + 论文清单逐字节一致、
`_readme_counts --verify` 一致（console=21/181、experiments=2/24）、
`[ESCAPE_CENSUS] py_files=83 hits=0 floor=80 broken=0`。

**还欠着的一件（等他拍板，不自作范围）**：全仓 `^MSG;` 普查命中 3 条，已处理 2 条，
剩 `e3b7db8` 尾部一行；它在更前面，改它要把 `e3b7db8 / 76825e0 / b9d37c7 / 4adc947 /
5b4048b / 9fc3be5 / 34e3730` 共 7 个指针一起重落。dry-run 断言（含"每条都不在
`origin/master` 里"这道闸门）已跑过全绿，未拍板就不动。

### 同日续十：他自己量到的那条失配（注释写 82、门印 83），和"注释里的数"这一族

**失配是他测出来的，不是我。** `console/test_source_escape_sequences.py:52` 写着
"实测 82（2026-09-30）；下限 80 ⇒ 余量 2"，而同一个文件跑出来的 census 印的是
`py_files=83`。porcelain=0 ⇒ **这条已经提交在仓里**。最便宜的核对方式就是
"注释里的数 vs 它自己印出来的数"，我没做，他做了。成因很具体：83 = 82 + 门自己那个文件，
我上一轮报告用的是加进门之后的数，注释用的是加进之前的数。

按"数要么删、要么由代码生成"处理：
- `FLOOR` 那行注释里的**实测条数删掉**，只留"下限与实测的差由断言兜着"这个语义；
  条数只存在于 `[ESCAPE_CENSUS]` 那一行（每次现算）。
- README 里同一族四处 `# N 行` 全删（**四条当场全是错的**，实测：
  index.html 写 2982 实为 3030、environment.py 写 2017 实为 2007、drone.py 写 289 实为 291、
  runner.py 写 609 实为 674）。没有任何用例钉过它们 —— 也就是说它们错了多久没人知道。
  行数交给 `wc -l` 现数，树状图那几行只留职责描述。

**`.pyc` 那条从"注释里的说法"变成"测出来的事实"**（两边结果都报）：
- 机制层（干净子进程，`PYTHONPYCACHEPREFIX` 指到仓外、缓存真落盘）：
  `[ESCAPE_MECHANISM] import=[1, 0] compile=[1, 1, 1] pyc=1` ——
  同一个坏文件，**import 路第二遍就 0 条**，compile 路三遍都是 1 条。
- 接线层（真把 `scan_repo()` 里探针那一路换成 `import`）：4 条用例红 1 条，红的是
  `AssertionError: 0 != 1 : 同一个坏文件第二遍扫不到了（[]）—— 判据依赖了 compile 之外的状态`。
  这条断言是本轮新加的（复扫必须仍红），它是"换成 import 就漏检"的**承重**，
  所以 `compile()` 确实替什么买单，现在是事实而不是说法。
- 新常驻用例 `test_compile_is_what_keeps_the_second_pass_alive` 把这个对照钉住，并且
  **反过来也可证伪**：哪天真让 import 第二遍也抓得到，它会红，报警直接写着
  "注释③那句'不能当证据'失去依据，要连注释一起改"。
- 变异过程自己翻车两次，都报出来：第一次把 helper 插成缩进块 ⇒ 红在 `NameError` 上
  （无效变异，我没当成证据）；第二次前置断言写错期望数（`_by_import` 出现次数）⇒ 脚本
  自己崩，没碰盘上文件。第三次才拿到上面那条有效变异。

现况：venv `Ran 182 tests OK`（21 个文件，无 skip）、experiments `Ran 24 tests OK`、
`_citations --verify` rc=0、`_readme_counts --verify` 一致（console=21/182）、
`[ESCAPE_CENSUS] py_files=83 hits=0 floor=80 broken=0`、`[ESCAPE_MECHANISM] import=[1, 0]
compile=[1, 1, 1] pyc=1`。

### 同日续十一：保护名单挂到了子集上 —— 他读出来的一次数错，成因是"两个数不同源"

上一轮我把那 6 处合法行号写进仓时，形成长这样两行：

```
- 合法（相关工作叙述，**不得当缺陷报**）：61, 63, 65
- 合法（文献/引用键）：414, 416, 419
```

他对着这一行问"你说 6 处，这里只有 3 个"。**三个可能答案里他给的第 3 个最接近事实，
但缺陷比"标签不清"更坏**：`不得当缺陷报` 这个字样只挂在 3 个的那行上，而"6"来自另一处
（`len(legal)`，即两个子集之和）。所以矛盾不是"早期计数过期"（不是第 1 类），
也不是"少写了三个数"（不是第 2 类），而是**同一个文档里两个数不同源**：
一个是子集的长度，一个是全集的长度，共用了一个"合法"的名字。

为什么这条比一般的数字失真严重：这张名单是按短语 grep 来用的 —— 谁 grep
`不得当缺陷报` 来决定"哪些不许动"。挂在子集上，就意味着**按它保护的人只会保护 6 处里的 3 处**，
另外 3 处（`\bibitem{qmix}`、`QMIX: Monotonic…`、`\bibitem{vdn}`）会被当成可删项。
那恰好是这套分类存在的理由（别把别人的相关工作当缺陷删）被自己的交付形式推翻。

改法（`_paperscan.render()`，仍是生成、不手填）：
- 保护名单成为**单独一行、且就是全集**：`- **合法，不得当缺陷报（共 6 处，这一行就是全集）**：61, 63, 65, 414, 416, 419`；
- 两个子集降格成"├ 子集·…"，并加一行明写"别拿子集当保护名单"；
- 待夺那行同时补上处数，两类合起来的总数由同一批 `rows` 现算。

新断言 `test_greppable_line_numbers_exist_and_match`（`console/test_paper_void_scan.py`）钉的是
**形状而不是数字**：列行号且含该短语的行必须恰好一行；那行的行号集合必须与 `classify_text`
现算的合法集合**双向相等**；印的处数必须等于行号个数；两个子集的并集必须等于全集且不得重叠
（重叠=同一处数两遍）。为什么不能只靠已有的逐字节核对：那条挡"手改产物"，
挡不住"把 render() 里这段删掉再 --write"，更挡不住"挂到子集上"。

三条变异实测（每次都连带重生成清单，让逐字节核对处于'一致'状态，专门看它瞎不瞎）：
① 把保护字样挪回只含 3 个的行 ⇒ 红，`Lists differ: [61, 63, 65] != [61, 63, 65, 414, 416, 419]`；
② 全集行少列一个行号 ⇒ 红，`[61, 63, 65, 414, 416] != …419`；
③ 两个子集改成有重叠（并集仍是 6 个但会数两遍）⇒ 红。
还原后 `_paperscan.py` 与清单均逐字节相同。

现况：`console` `Ran 183 tests OK`（21 个文件）、`experiments` 24 OK、
`_citations --verify` rc=0、`_paper-report --verify` byte_equal=yes、`release_check.py` rc=0。





### 同日续十二：映射表从"我抄的"改成"git 算的"（同一族第四次，这次直接把来源换掉）

手写那张表连着错在同一个地方三次：注释里的实测条数与门印出的不一致；把 dry-run 造出的对象
当成活 sha；记下来的"要重落几个指针"过一轮就过期（记的是 9，现在自己变成 11）。
**所以这次不再"更小心地抄"，而是把来源换成对象库**：`console/_rewrites.py` +
`console/_citations.py --rewrite-report --write/--verify`，产物仍是
`docs/提交改写映射表.md`。表里没有任何一个手抄值。

口径全部可复算：
- **活对端**按 `subject + tree + author行 + committer时间戳` 四样同时相等去配（不靠我记的映射）；
- **曾当过分支头 vs 从未上头**（dry-run 产物）：看 sha 是否出现在 `git reflog refs/heads/main`；
- **还欠几条残文**：一条 `git log --format=%B` 扫全部可达提交，**不等我承认**；
- **恒等式**：`曾为头 + 从未上头 + 树不等 + 无关悬空 = 不可达条数`，不成立直接退出码 1
  （分桶里最容易死的是"某一类既不算通过也不算失败"，所以印的是等式而不是三个独立数）；
- **与改写无关的悬空对象要点名分类**（实测 5 个：3 个孤儿根初始提交、2 个 `git stash` 残留），
  不当失败、也不当"没这东西"；归不进任何一类才算问题。
- 门自己的成本印在行上：`cost_ms=`（现算约 3.7 s，随提交数增长，所以文档里也不写这个数）。

两条当场被抓的自错，都记下来：
1. **生成器第一版不确定**：只按 committer 日期排序，同秒的对象跟着 set 迭代序走，而 set 序受
   `PYTHONHASHSEED` 影响 ⇒ 刚 `--write` 完，下一毫秒 `--verify` 就报"表被手改过"。
   改成全序 `(日期, sha)`，并加一条跨 4 个 hash 种子比哈希的用例钉住。
2. **欠账表最初只列 sha 与计数、不列残文本体** —— 下一个人看不出扫到的是不是同一形状。
   现在带上原样首行（这条是它自己那个正例用例逼出来的）。

新门 `console/test_rewrite_map.py`（6 条）在临时仓里造真实触发，因为**当前仓这几条判据
全都处于"没抓到东西"的状态**，只跑真仓等于只测了绿的一面：
message 带 `MSG;` 的坏提交（扫描必须数到它）、改写时顺手改了树（闸门必须报"树不相等"）、
表被改一个字节 / 被删掉（`--verify` 必须退出码 1）、活文档引用的 sha 断链（正例见下面）。

变异/对照实测（各条都被不同的用例抓到，`_rewrites.py` 与 `test_rewrite_map.py` 事后逐字节还原）：
排序退回非全序 ⇒ 确定性用例红；悬空对象不再点名 ⇒ 自洽用例红（problems 从 0 变 5）；
残文正则改严 ⇒ 正例扫不到；摘掉"树不等"的放宽配对 ⇒ 临时仓那条正例不再被点名；
**摘掉前缀比对 ⇒ 误报 78 处**（见下面第二条自错）；从表里删掉一行只在表里登记的 sha ⇒
红，并直接报出 `CHANGELOG.md:343/359/405` 三处引用 —— 这条就是给他台账兜底的形状。

第四、五次自错，也都记下来：
1. **文档 sha 可达性那条用例第一版全仓误报 77 处**：可达集里是 40 字长号，文档引的是 7 字短号，
   `tok in reachable` 对短号永远为假。改成按前缀比 + 断言这批对象里 7 字前缀不相撞。
   误报被我自己当成"仓里真断了 77 处"看到的第一眼是没怀疑判据的 —— 是先跑正例才分清的。
2. **"表里删一行"这个对照第一版是无效的**：我挑了 `2294adc`，而它作为曾经的分支头仍然
   `--reflog` 可达，删掉那行什么也不会发生（rc=0）。换成只在表里登记、reflog 里没有的
   dry-run 对象 `b9d37c7` 才真的红。**一个"能变红"的对照，要先确认它变红的原因就是被测的那条性质。**

**第三轮改写已落地**（`e3b7db8` 那件，本轮唯一在账的事）：
重落 11 个指针（`e3b7db8 76825e0 007be71 5d3d153 873f069 ab830e7 34e3730 1f540dc a93f548
741b024 fba16e0` → 新链 `d05b0b7` 结尾），只删 message 尾部那一行 `MSG; …`（697→411 字节）。
断言逐条跑过：链上 11 条全部未推、每条 tree 相同且 `git diff --quiet` rc=0、
author/committer 与时间戳原样、非目标提交 message 逐字节不变、**11 条标题一条没变**（台账主键）、
未推条数改前改后都是 47、工作区状态逐行相同。
独立复验：全链 message 里 `^MSG;` 命中 **0**；`rev-parse HEAD^{tree}` 与改写前 `fba16e0` 相同；
回退命令印在脚本输出里（`git update-ref refs/heads/main fba16e0`）。
生成器随即自己更新：`objects=133 reachable=111 unreachable=22 pairs=17 pending=0 problems=0`，
恒等式成立，欠账那节变成"（无）"。**这就是把表交给代码的全部意义**：
本轮之前它写的是 `pending=1 / 11 个指针`，我一句没改，重跑就变对了。

现况：venv `Ran 189 tests OK`（22 个文件，无 skip）、experiments `Ran 24 tests OK`、
`--rewrite-report --verify` rc=0（cost_ms≈4.5 s）、`--paper-report --verify` byte_equal=yes、
`_citations --verify` rc=0、`_readme_counts --verify` 一致（console=22/189）、
`release_check.py` 见下一条。

**紧接着就被自己的验证抓到一处自指**（同一轮内，上一笔提交 `750bd26` 之后立刻跑到）：
产物里印了 `对象库里的 commit 总数` 与 `从 HEAD 可达` 两个绝对量 —— 而**承载这份产物的那笔提交
自己也是一笔提交**。所以时序是：`--write` → `--verify` 绿 → commit → 再 `--write` 就产生 diff
（实测 `objects` 133→134、`reachable` 111→112），也就是"交付即过期"，`--verify` 从此每次红一次。
这是我在给"表交给代码算"之后**新引入**的一类错，不是老错复现。

处理：产物里只留与"新提交"无关的量（不可达数、配对数、分类各桶、欠账数、问题数、恒等式）；
绝对总数与门成本只出现在运行时读数行上。加断言
`test_artifact_has_no_self_referential_counts` 把这两个行名和 `cost_ms=` 钉住，
同时反向断言"不可达 / 配对 / 欠账"必须仍在（防止我用"删干净"来通过这条）。
现况重测：`Ran 190 tests OK`（22 文件）、`--rewrite-report --verify` rc=0、
提交后再 `--write` 产生 **0 行 diff**（这才是这条修好的证据）。

### 同日续十三：B 组手抄数清干净 + C 组把取数搬进一次批读（一笔 commit）

顺序按他定的：先 C 再 B，B+C 一次单独 commit；A 组只做证据，不进这笔。

**C（性能）**：`console/_rewrites.py` 原先对每个 commit 起一次 `git show -s`（45 个对象 ⇒ 45 个
进程）。现在按仓缓存一次 `git log --no-walk --format=%x01%H%x00… --stdin` 读全量，`fields()`
与排序键 `_dkey` 都只查内存。本轮读数（项目 venv `../.venv310`，Python 3.10.11）：

| 量 | 读数 | 复算 |
|---|---|---|
| 门自己的成本 | `cost_ms=1685` | 印在 `[REWRITE_MAP_MATCH]` 那一行上 |
| `_citations --verify` 全套 | rc=0，4.68 s | `python console/_citations.py --verify` |
| `test_rewrite_map` 单模块 | `Ran 8 tests in 17.4 s`（另两次 16.67 / 17.61） | `python -m unittest console.test_rewrite_map` |
| 活文档 sha 普查 | `[DOC_SHA_CENSUS] 172 / 0`（与优化前同一个数） | 上面那条用例自己印 |
| 生成的表 | 逐字节一致（`--verify` rc=0，表未重生） | `--rewrite-report --verify` |

跨解释器的两组数不混算：先前那组 45.3 s→17.8 s 是在 anaconda 3.13 上测的，只与同解释器的
前值比；本轮全部读数出自 3.10.11。

**等价性不靠"看起来一样"**：新用例 `test_batch_read_matches_per_object_read` 逐字段比 45 个对象
（22 个不可达 + 20 个可达，且**先断言这些 sha 真在批读表里**，否则它们会静默落到单条兜底、
这条用例就没测到批读）+ 三类边界标题（前置空行、前导空格、尾随空格）。三条实测都可复算：

- 变异 M1（把 `.strip()` 加回批读的标题字段）⇒ 红，`不一致=1`。**同一个变异在加边界标题夹具之前是绿的** ——
  本仓没有能区分它的标题，所以先造数据再谈判据生效。
- 变异 M3（提前建批表，让边界对象落到单条兜底）⇒ 红，`assertIn` 直接点名标题。
- 消融（删掉我先加的 `RW._BATCH.pop(...)` 兜底）⇒ 绿 ⇒ 那句是装饰（临时仓目录来自
  `mkdtemp`，键每次都是新的，缓存不可能预先有值），已删，只留断言。

**我自己产的量具崩过一次，成因值得记**：`both()` 里用了 `subprocess.run(..., text=True)`。
本机默认编码 GBK，解 git 的 UTF-8 输出时 reader 线程抛 `UnicodeDecodeError`，
而 `subprocess` 把这件事表现成 **`stdout=None`、rc 仍然是 0** —— 于是 `.stdout.strip()` 崩
`AttributeError`。第一版是绿的、换了样本就崩：判据跟着数据漂，比恒红更坏。
改成按字节读再 `decode("utf-8","replace")`，并在 `read()` 里 `assert returncode==0`。

**B（六处手抄静态数）**：`_citations.py` 开头（覆盖率改指 `[CITE_SUMMARY]`，现印 68/68）、
`_rewrites.py` 两处（悬空分类改指表里的恒等式行；删掉 `实测 3 条 33 ms` 这种随仓漂的成本数）、
`README.md` 目录树里"8 份对比 CSV"（实为 7，且两份清单不一致 ⇒ 去掉数、指向清单本身）、
`results/compare_gate.py` 开头、`console/test_config_keys_coverage.py` 开头、
`console/test_server_guards.py` 的 `:disabled` 注释（改指 `grep -ac ':disabled' console/static/index.html`，
本轮现数 32；引入断言那笔 `c819118` 的父提交上 `.tiny-btn:disabled` 为 0 而 `.btn:disabled` 已存在，
所以"样式只写了 `.btn`"这句是核过的）。

**其中一处是我自己数错的，纠正如下**：我上一轮把 `compare_gate.py` 的"20 张图"记成
"应为 17 PNG + 3 表"。实测：`plot_compare_metrics.py` 一次生成 **17 张 PNG + 3 份派生表 = 20 个文件**
（默认被口径门拒绝，要 `--allow-mixed-comparisons`；它只写 gitignore 的 `results/adhoc/plots/`，
本轮跑完已删），归档侧是 **12 PNG + 3 CSV**（那 15 个才是出图链的入库产物；目录另有
`README.md` 与 `ROW_SETS.md` 两份说明，不归这条链生成 —— `ROW_SETS.md` 的生成器是
`results/row_set_delta.py --write`）。
所以 20 这个数没错，**错的是标签**（把 3 份 CSV 说成图）。README「已知归档缺口」那段现在
同时给了标签正确的数和当次复算的跑法。

顺带查到、**不改**（属 A 组边界）：`results/plot_compare_metrics.py:CSV_FILES` 仍挂着
`backend_wx_metrics.csv` —— 该文件已随后端 MARL 移除删掉，`load_compare_data()` 用
`[n for n in CSV_FILES if (COMPARE_DIR / n).exists()]` **静默过滤**，所以今天只剩"清单里
挂着一个不存在的文件名"；而它下面那句逐文件 `if not path.exists()` 的告警分支因此永不触发。
已把差异写进 `compare_gate.py` 开头，代码留给他定。

本轮全部门禁读数（都是这一轮打印的，不是上一轮的）：
`Ran 191 tests OK`（22 文件，无 skip）、`_citations --verify` rc=0
（`[CITE_SUMMARY] checked=68 anchored=68`、`[ROWSET_SUMMARY] void_refs=3 declared=3`）、
`[ESCAPE_CENSUS] py_files=85 hits=0 floor=80 broken=0`（83→85 = 上一轮新增的
`console/_rewrites.py` 与 `console/test_rewrite_map.py` 两个文件进了扫描范围，命中仍 0）、
`[REWRITE_MAP_MATCH] objects=135 reachable=113 unreachable=22 pairs=17 pending=0 problems=0`（恒等式成立）、
`_readme_counts --fix` 后 `--verify` 一致（console=22/191）、`python release_check.py` rc=0。
**解释器这条要单独记**：我第一次用 anaconda 3.13 跑 `release_check.py` 得 rc=2，
预检印的是 `便携预检失败：便携 Web 模式缺少依赖：shapely、pyproj、fastapi、uvicorn` ——
那是预检按设计把"环境不对"和"代码坏了"分开报，不是我这轮改出来的；换项目 venv 3.10.11 即 rc=0。

**本轮还有一起与代码无关的事故，必须留痕**：全量跑到一半，
`console/test_readme_command_side_effects.py` 三条红了，原文是
`git status 失败（128）：error: bad signature 0x00000000 / fatal: index file corrupt`。
实测 `.git/index` 是 42356 字节、**逐字节全 0**（`NONZERO_BYTES 0`），无 `index.lock`，
盘剩 21 G。**归不到我跑过的任何一条命令上 —— 这条只能写"未解释"**。
处理：坏索引改名保留（`.git/index.allzero-20261001`，不删），`git read-tree HEAD` 只重建索引、
不碰工作树；修完 `git status` 列出 8 个改动文件（正是本轮改的那 8 个），
`HEAD^{tree}` 与损坏前测到的同一个号（`5e06f6eb51c6…`，对象库未伤）。
判别式：**同一条命令、同一批文件，只把索引换掉 ⇒ `Ran 191 tests OK`** ——
所以那三条红的是索引，不是我改的逻辑。

边界照旧：`VERSION` 仍 `1.0.0`、未打 tag、未 push、无新依赖、未动 DDL、`paper/` 一处未碰
（那十七处仍只报不改）。A 组的 R4 与 `total_charging_energy` 两套方案证据在下一轮。

### 同日续十四：R4 的数交给扫描器（他点的是"生成化"那条）

A1 两个方案里他选了 **b**：不把 R4 那几个数改对，而是把数的来源换成扫盘。
新增 `console/_csvcensus.py` → 产物 `docs/compareCSV普查.md`，接进
`_citations.py --csv-census [--write|--verify]`，并挂到 `--verify` 总退出码上。
本轮现算读数：

```
[CSV_CENSUS] files=7 declared=6 both=5 disk_only=2 declared_only=1
             widths=13,20,25 no_bom=0 seed_cols=0 cost_ms=80
```

三条口径是照着这族反复踩的坑定的：
- **名单不抄第二份**：`_CSV_FILES` 与 `CSV_FILES` 从**源码解析**（括号配平 + 引号 + 注释分支），
  解析不出来就是 `[FAIL][CSV_CENSUS_PARSE]` + 退出码 1，**绝不退回"空名单继续算"**
  （空名单会把磁盘上每一份都判成"没人声明"，那是喊狼的红）。
- **两种 0 分开**：`清单声明但磁盘没有`（今天就是 `backend_wx_metrics.csv`，
  由 `6b8c4c8` 删的，sha 也是现算的）只进报告行、**不进退出码** —— 摘哪一行是他定。
- **分桶印恒等式**：`两边都有 + 只在磁盘 = 磁盘份数`、`两边都有 + 只在清单 = 声明条数`；
  外加范围下限 `FLOOR=5`，现数低于下限整轮不作数（`[CSV_CENSUS_RANGE]`，排在比产物**之前**）。

四条自错，都被自己人或自己的门抓到：
1. 第一版把"清单声明但磁盘没有"塞进 `problems` ⇒ 那条只报不改的事会变成拦路的红门。写的时候
   跟模块头里自己写的口径对了一遍才发现，拆成 `watch` 桶，并加断言"`--verify` 必须仍是 0"。
2. 夹具第一版把名单写在**临时文件的第 1 行**，撞出 `_parse_declared` 用 `"\nVAR = ["` 找锚点
   会漏这种入口（真仓两份都有前导内容，所以这个洞从没暴露）。改成 MULTILINE 行首匹配。
3. `[CSV_CENSUS_RANGE]` 写在短码表里却**从没被发出来**（下限走的是 `PROBLEM`）—— 被
   `test_documented_codes_are_all_emitted` 点出来。拆开后顺手给 `PROBLEM` 找了个真证人
   （0 字节那份 CSV），否则"空表头记一条问题"这条分支没人验过。
4. `--write` 原本无条件返回 0 ⇒ 扫描瞎了也能"交付"一份没人信得过的产物。改成 RANGE 先返回 1。

变异四条，各自 RED，跑完从备份还原并核 sha256（`b71956c7…`，`files_now_identical=True`）：
摘掉 `FLOOR` ⇒ 下限用例红；把 `watch` 塞回 `problems` ⇒ "待夺不进退出码"那条红；
去掉注释跳过分支 ⇒ 带 `don't` 的名单解析红；空表头不记问题 ⇒ `PROBLEM` 用例红。
（`console/test_compare_csv_census.py` 共 10 条；真仓那条不比生成器，而是**用 `glob` + `csv.reader`
另数一遍**逐字段对产物 —— 生成器错则两边一起错，自洽不等于正确。）

登记表 R4 那行改成**只指路不抄数**，并加断言钉住：`| R4 ` 行里出现 `\d+\s*列`、`[四七八九十]\s*份`、
`efbbbf|e7ae97` 任一形状就红（防"改完生成器又把数粘回文档"）。README 文档索引加一行，
用例数由 `_readme_counts --fix` 重生（console=23 文件 / 201 用例）。

**A2 只多了一条证据，没动代码**：`total_charging_energy` 的兄弟 `total_charging_sessions`
（`frontend/environment.py:253`）**同样只有定义、无写无读** ⇒ 登记表 M10 那句"全文件检索命中 1 次"
少报了一个键。活的换电计数是 `total_swap_sessions`（`:183` 定义、`:800` 写、`:821` 导出，
对应 CSV 列 `换电总次数`）；`frontend/charging_station.py:11` 自己写着 `charging_power` 仅作向后兼容。
⇒ 删这两行是对外零变化，接上真值会动口径并要重跑结项 68 次 —— 这条等他单独点头。

边界照旧：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 一处未碰。

### 同日续十五：R5/R6 也交出去，普查多算一节"宽表比窄表多哪些列"

接着上一条往下做：同一张表里 R5、R6 两行还各自扛着手抄数。这次分两种处置，**故意不合并成一份**：

- **R5 的口径**（族 / episode 上限 / 重复数 / seed 集 / 磁盘实际步数）**唯一真源是
  `results/compare/manifest.json`**，它已经有自己的门（`compare_gate.py --check-all` 核声明与磁盘、
  `--selftest` 证"混口径真会被拒"）⇒ R5 那行改成指路，**普查不重算一遍口径**（重算就是第二份真源）。
- **R6 的列差集**（"哪些列窄表根本没有"）以前**没有任何地方算过**，只有 R6 那句
  "机队 5 列只在 25 列 schema 里有" ⇒ 给普查加一节 `column_gap()`，按完整列集合分组后取差集。
  本轮现算：含 `算法` 列的 5 份里 2 种列集合，宽表比窄表多 **5 列**，具名
  `总飞行距离`/`无人机利用率`/`禁飞区绕飞次数`/`空载率`/`顺路接入次数` —— R6 那句手抄话被证到位了，
  而且以后窄表补一列，差集会自己缩（变异 M-E 把差集写成常量 ⇒ 3 条用例红）。
  读数带字段名：`gap_schemas=2 gap_only_in_wide=5`。

**本轮我自己犯了三条，都记下来，其中第一条正是这族错误的原型**：
1. **R6 的新文案里我引用了一个不存在的用例文件** `console/test_echarts_missing_column_not_zero.py` ——
   真证人其实在 `console/test_compare_gate.py`（`test_frontend_does_not_coerce_missing_columns_to_zero`
   与 `test_missing_column_policy_is_written_down`）。我是把文件名**想**出来的，不是查出来的；
   写完当场 `ls` 才发现没有这个文件。指路指到不存在的地方，比手抄数更坏。
2. **R6 被我替换成两行**（旧行没删掉），是"重复行"这种最容易被忽略的形状；
   新加的断言"`| R6 ` 应恰好一行"从此盯着它。
3. **测试期望值我自己脑算错过一次**：夹具里窄表 `[算法, A]` 对宽表 `[算法, A, B, C]`，
   我写成差集是 `A,B,C`，跑出来是 `B,C` —— 我自己就是那个"手抄数"的人，一条断言跑一遍就现形。

取证脚本里加了一条纪律：**崩溃不算变异咬到**。变异若造成 `SyntaxError`/`ImportError`，
退码也是非 0，把它记成"RED"等于给自己发假证；脚本里显式判成 `CRASH(无效变异)` 并跳过。
三条变异（M-E 差集写成常量 / M-F 把最窄当最宽 / M-G 空集不解释原因）各自 RED，
每条跑完都从备份还原并核 sha256（`a893cabd…`，`identical=True`）。

现况：`console/test_compare_csv_census.py` 13 条用例；`_readme_counts --fix` 后 README 一致；
`--csv-census --verify` rc=0。（当时写"R8 那行仍带着手抄数、这轮没动" —— 下一笔就动了，见续十六。）

边界照旧：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 一处未碰。

### 同日续十六：R8 那对里的三处互抄收成一份（含我丢掉又重放的一次工作）

主控令：①提交上一笔（`f15ded5`，批准语已写进提交信息）②只推进 R8 ↔ `console/test_plots_archive_void.py`
那对 ③`A2` 两行死字段不动，只落一条待批记录。本节记②。

**盘上原来有三处在抄同一批数**：登记表 R8 行、作废通知 `results/compare/plots/README.md`、
以及用例本体 —— 后者在文件头部把 `CORE / WITHDRAWN / VOID_SET` **抄了第二份**（连注释都是
`_rowsets.py` 里那句），于是"改了唯一真源、这条门还按旧名单绿着"是可能的。收成一份：

- 名单只留 `console/_rowsets.py`；用例改成 `import _rowsets as RS` 并派生三个集合，
  另加一条自源断言 `set(CORE|WITHDRAWN) == set(RS.ALL_NAMED)`。
- 表清单不再写死三个文件名，与 `results/row_set_delta.py:_tables()` 同一条口径（`glob("*.csv")`）；
  产物件数**不再是常量 15** —— 两个桶各要求非空（空桶 = 扫描到不了，不是"没问题"），
  真数印在运行行上：`[PLOT_VOID_CENSUS] csv=3 png=12 withdrawn=6 all_named=10`、
  `[PLOT_VOID_ARTIFACTS] 逐件问祖先：15 件（csv=3 png=12）`、
  `[PLOT_VOID_GA_CALIBER] archived_ga_steps=2000.0 current_ga_steps=400.0`。
- 通知与 R8 行里的 `15 件 / 12 张 / 10 个 / 0.833768 / 2000 步 / episode_max_steps=3600`
  全部改成指路（各自的唯一真源是运行行、`ROW_SETS.md`、`manifest.json`），
  并由新用例 `test_no_second_copy_of_the_counts_or_the_list` 禁掉这些形状。

**一次真实红（不是措辞，是运行输出）**：把 `results/compare/plots/combined_compare_metrics.csv`
里 `iql` 那一行删掉 ⇒ `FAILED (failures=4)`，红的四条是
`test_archived_tables_still_carry_the_withdrawn_rows`、`test_detector_is_not_vacuous`、
`test_rowset_delta_generator_is_pinned_and_goes_red`、`test_rowset_marker_is_required_and_bidirectional`；
还原后逐字节等于 `HEAD`（扰动态 `4681545f0adc49c7` → 还原 `b465b781f5420996`），用例重新 `OK`。

三条变异（还原一律用 %TEMP% 快照，见下面那条教训）：
N-A 通知里抄回"15 件产物、12 张图" ⇒ `failures=1`，红的正是新加那条禁抄数用例；
N-B 用例里再造一份 `{"iql_u"}` 名单 ⇒ `failures=1`，同一条；
N-C 往 `_rowsets.WITHDRAWN` 里加一个不存在的算法名 ⇒ `failures=4`（表判定、判别式、
通知逐个点名都跟着红）—— 这条证的是"名单只有一份"真的贯通到纸面，不是嘴上说说。
三个文件跑完 `restored_all_identical=True`，`git status` 收尾只剩该动的三个。

**②里我自己砸了一次工作，重放了一遍**：第一版取证脚本用 `git checkout HEAD -- <文件>` 做还原，
而那两个文件带着本轮**未提交**的修改 ⇒ 一次 `checkout` 把用例与通知的②改动一起冲掉了
（`git status` 当场只剩登记表一行）。这是台账里已经写过的那条（别把 `checkout` 接在要保留的改动后）
被我原地再犯。处置：按对话里的原文逐条重放 9 处编辑 ⇒ `py_compile` + 9 条用例回到 `OK`；
取证脚本改成"快照到 %TEMP% / 从快照还原 / 逐个核 sha256"，并把这句写进脚本 docstring 当提醒。
另一次红也来自我自己：重写 R8 时把带 `行集=all10` 标注的引用一起删了 ⇒ 登记簿的作废引用
从 3 处掉到 2 处，`test_rowset_marker_is_required_and_bidirectional` 自己红。
**没有放宽那条下限**，而是把带标注的引用放回 R8 行（`[ROWSET_SUMMARY] void_refs=3 declared=3` 回到原值）。

边界照旧：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 一处未碰。

### 同日续十七：A2 落成仓里一条 awaiting-user 记录（代码一行未动）+ 一条现状门

主控令 ③：`A2` 那两行死字段**先别动**，删对外结论属作者权；要做的是写成仓里一条待批记录，
标 `awaiting-user`，写清是哪两行、怎么复算、"删"与"不删"各自的后果。

- 记录落在 `docs/数据来源与可追溯性登记表.md`：M10 那行改成同时点名两个键
  （`frontend/environment.py:252#total_charging_energy`、`frontend/environment.py:253#total_charging_sessions`，
  带锚点的形式才让引用门禁翻得开），并新增「待批（awaiting-user）」一节：
  两条复算命令、为什么它们是死的（活键是 `total_swap_sessions`，`:800` 写、`:821` 导出，
  对应 CSV 列 `换电总次数`；`charging_station.py:11` 自述 `charging_power` 仅作向后兼容）、
  「删」的后果（对外零变化 + 唯一风险是仓外按键取值，仓内检索为 0，**仓外我不知道**）、
  「不删」的后果（不影响产物，但纸面上永久留着两个"看起来是指标"的恒 0 名字，前科就是 R6），
  以及第三条路「接上真值」为什么不推荐（动对外口径 + 68 次运行产物要重跑）。
- 顺带纠正记录自己：M10 原先写"全文件检索命中 1 次"，**漏了兄弟键**，现为两处定义。
- 新增 `console/test_dead_charging_fields.py`（4 条）：它不替谁做决定，它保证"决定还没做"这件事
  不会悄悄过期 —— 定义/写入/读取/导出四桶分类、扫描**下限 60 个 `.py`**（本轮实扫 88）、
  记录与现状同生共死（撤记录不撤字段 ⇒ 红，接上字段不撤记录 ⇒ 红），
  外加一面反夹具：同一分类函数必须能把"有人读"的键判成活键，否则那些 `== []` 只是我的正则谁都不匹配。
  本轮读数：`[DEAD_FIELD] name=total_charging_energy defs=1 writers=0 readers=0 exports=0 定义处=['frontend/environment.py:252']`
  （`total_charging_sessions` 同形，定义处 :253）。
- **一次真实红（运行输出，不是措辞）**：临时放一个 `frontend/_deadfield_probe_tmp.py`
  只读这两个键 ⇒ `FAILED (failures=1)`，原文
  `AssertionError: Lists differ: ['frontend/_deadfield_probe_tmp.py:2'] != []`（"出现了读取点"那条）；
  删掉探针 ⇒ `Ran 4 tests OK`。探针是我自己造的散件，用完即删，没碰任何被跟踪文件
  —— 这次还原用的是"造文件/删文件"，不是 `git checkout`（②里那条教训）。

现况（本轮实测，不是上一轮的数）：`Ran 209 tests OK`（console 全量，2.5 分钟）、
`_citations --verify` rc=0、`_readme_counts --verify` rc=0、
`[ESCAPE_CENSUS] py_files=88 hits=0 floor=80 broken=0`（87→88 = 新加的那个用例文件）。

边界照旧：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 一处未碰；A2 代码一行未动。

### 同日续十八：`release_check` 353 s 的成因定到一段，剩余部分明写未定

环境行（同机并发负载，本轮实采）：全程 **node 8–10 个、java 4–5 个**在跑（属其他会话，
未结束任何人的进程），CPU 采样 `[11,14]`～`[60,62]`。解释器只用项目 venv
`../.venv310/Scripts/python.exe`（3.10.11）。

**同一条命令连跑 3 次的分布**（不是单次）：

| 轮 | 参数 | rc | 耗时 |
|---|---|---|---|
| full1 | 无 | 0 | 353.017 s |
| full2 | 无 | 0 | 351.495 s |
| full3 | 无 | 0 | 356.900 s |
| noE2e | `--skip-e2e` | 0 | 348.257 s |
| strict | `--strict` | **0** | 356.007 s |

极差 5.405 s（1.5%）。**`--strict` 在这台机通过**（errors=0），所以它不是"环境不达标"那条。

**逐段计时**（独立调用同一段代码，各 1–2 次；`Ran 209 tests` 那轮父套件实测 152.202 s）：

| 段 | 耗时（本轮实测） | 复算 |
|---|---|---|
| `_preflight.collect_skips()` | **170.884 / 171.146 / 172.293 s**（n=3，中位 171.146） | `python -c "import sys;sys.path.insert(0,'console');import _preflight as P;P.collect_skips()"` |
| 父进程 `unittest discover -s console` | 152.202 s（跨轮 154.2 / 156.3 / 158.7） | `python -m unittest discover -s console -t .` |
| `_citations.main(["--verify"])` | 6.130 s | `python console/_citations.py --verify` |
| 端到端自检（由 `--skip-e2e` 差得） | ≈ 4.76 s | `353.017 − 348.257` |
| `compileall` / `experiments` / `_check_js` / 两个 dry-run / `build_package` / `run_checks` | 0.953 / 1.161 / 0.599 / 0.419+0.415 / 0.772 / 0.293+0.319 s | 各自单跑 |
| **合计可解释** | **338.8 s** | — |
| **余量** | **≈ 14.2 s 未拆** | ≥8 次子进程启动与输出捕获，但没有更便宜的证法；**标未定** |

**定性**：`_preflight.collect_skips()` 的 docstring 自己写着"跑一遍 console 发现"—— 它起子进程
把**同一套用例再跑一次**，所以 `release_check` 的时长里约等于**套件成本 ×2**：
`171.1（子）+ 152.2（父）= 323.3 s = 中位时长的 91.6%`。这是"201 s → 353 s"的**机制性解释**：
套件从 105.3 s（191 条）长到 152.2 s（209 条）是 +46.9 s，×2 就是 **+93.8 s**；
剩下约 **+58 s 我无法同时刻反证**（201 s 那一轮没有配套的负载采样，也没有当时的 `collect_skips` 分段数）
—— 这一段按令**明写定不下来**，不拿"性能没问题"收尾。

新增/改动门自己的成本（各 2 次，取区间；因为 ×2 机制，这部分在总时长里是按双份计的）：
`test_rewrite_map` 26.319–27.743 s、`test_compare_csv_census` 4.723–4.877 s、
`test_plots_archive_void` 2.581–2.658 s、`test_dead_charging_fields` 0.649–0.688 s。
（`test_rewrite_map` 比上一轮的 13.8–17.6 s 又贵了，它起子进程，对同机负载敏感 —— 这条也标观察，不定量。）

**(a) 索引损坏/重建 ⇒ 变慢：排除。** 同 flag 对照：本仓 `git --no-optional-locks status`
139/143/153 ms，健康仓 `D:\image-hosting-platform` 149/150/156 ms；本仓
`count-objects` = 1751 散件 / 0 pack / `.git` 57 M。损坏索引发作时是让 git **失败**
（rc=128 `index file corrupt`），不是让它慢。
**(c) DB / Flyway 状态：本仓无对应物。** `flyway|jdbc|out-of-order` 在代码/配置/文档里命中 **0 行**，
`.sql` 文件 **0 个** —— 没有可 `out-of-order` 的东西，这条不是"排除了"而是"不适用"。
**(d) 同机负载：解释不了台阶。** 五轮 ms 挤在 351.5–356.9，而期间 CPU 采样从 11% 跨到 62%；
但它对历史那一次（201 s）的绝对值影响**无法反证**，见上面那句"定不下来"。

**处置建议（未执行，等令）**：把 `collect_skips` 从"再跑一遍"改成"读父进程那一次的结构化结果"
（父套件本来就在跑，让它自己吐 JSON 摘要即可）。这能砍掉约 **171 s（48%）**，
且不改任何判据 —— 只是不再付两遍钱。**这是改 `release_check`/`_preflight` 的代码，本轮没动。**

**`.git/index.allzero-20261001` 的具名事实**：42 356 字节、逐字节全 0，mtime epoch `1790837016`
= 本地 **02:43:36**；现役 `.git/index` 42 740 字节 epoch `1790872185` = **12:29:45**，
与 381.9 s 那轮的输出文件 mtime（`1790872184`，12:29:44）**相差 1 秒** —— 那个索引是被那一轮
`release_check` 自己重写的，而损坏文件比它早 **9 h 46 m 09 s**。所以"损坏索引"与"381.9 s 那轮"
**不是同一时刻、也不同因**，我此前把它们放在一条候选里的猜测**撤回**。
按令处置 = **保留**该文件、`.git` 里不删不 restore 不 `gc` 不 `repack`，**成因仍写"未解释"**
（无 `index.lock`、盘剩 21 G、我跑过的任何一条命令都归不上）。

边界照旧：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 一处未碰、
`.git` 内未动任何东西、那 5 张未入库 PNG 未删。

### 同日续十九：`collect_skips` 不再重跑套件（省 ~171 s），并用同一份探针证覆盖面没缩

主控令：把 `_preflight.collect_skips()` 改成读一次结构化结果，**四条硬约束**——覆盖面不得缩小、
省下的秒数必须是 ≥3 次实测分布、不得为了快而删掉任何一次真实执行、那 14.2 s 余量与 ~58 s 台阶继续挂账。

**改法**（`console/_preflight.py` + `release_check.py`）：

- 子进程 `_CHILD_SKIP` 的 JSON 多带一个 `detail` 字段（`TextTestRunner` 的报告正文原本被丢进
  devnull）。这不是装饰：红的时候只报计数就是"FAIL 但不说为什么"，而那一栏此前由父进程的
  `unittest discover` 提供 —— 正文跟着 JSON 回来，才敢合掉那两遍。
- 新增 `run_console_suite()`；`collect_skips()` 保留成它的别名（`console/_preflight.py --skips`
  这条 CLI 仍走它，实测 `Ran 209 tests，failures=0 errors=0 skipped=0` + 「本次运行没有 skip」）。
- `release_check` 里"父跑一遍 discover + 子再跑一遍拿 skip"合成**一遍**；判定改成
  `failures==0 and errors==0 and tests>0` —— `tests=0` 算失败，什么都没收集的 OK 是最贵的假绿灯。
  **没有任何一次真实执行被删掉**，删掉的是同一套用例的第二次执行。

**覆盖面两面证据**（同一份探针：给 `console/test_compare_gate.py` 临时加一个
`REDDEMOProbe`，一条 `@unittest.skip` + 一条 `self.fail`；跑完从 %TEMP% 快照还原，
`restored_eq_HEAD=True`、`sha=c9ffd1419b4a1de2`、探针残留命中 0）：

| 面 | 改前（`collect_skips()` + 父 discover） | 改后（`run_console_suite()`） |
|---|---|---|
| skip 是否抓到 | `tests=211 failures=2 errors=0 skipped_total=1`，JSON 含 `…REDDEMOProbe.test_probe_skip_marker` | 同一行 `skipped_total=1`，同一 id 仍在 |
| 失败正文是否可见 | rc=1，`Ran 211 tests in 151.781s` / `FAILED (failures=2, skipped=1)`，`FAIL: test_probe_failure_visible` | `detail` 含 `test_probe_failure_visible` 与 `FAILED (failures=2, skipped=1)`；`release_check` rc=2 并 `[FAIL] console 单元测试 · Ran 211 tests（failures=2 errors=0 skipped=1）` |
| skip 渲染段 | —（另调 `render_skips`） | `[INFO] 本次不可跑的用例` 印出（ASCII 标记 `_preflight.py --skips` 命中 1） |

（改前那轮的第二个失败是 `test_readme_counts_match_measured` 报 `(24, 209) != (24, 211)` ——
我注入 2 条用例被计数门正常抓到，不是无关缺陷。）

**分布（同机背景：node 10–13、峰值 27；java 4；CPU 采样 1%–90%）**

| | min | median | max | rc |
|---|---|---|---|---|
| 改前 全量（续十八，n=3） | 351.495 | 353.017 | 356.900 | 0 |
| 改后 全量（n=3） | **169.987** | **171.772** | **186.449** | 0 |
| 改后 `--strict`（n=3） | 183.882 | 183.931 | 185.433 | **0** |

省下 **181.245 s**（中位对中位）；`Ran 209 tests` 在六轮里一条没变。
`--strict` 本轮补上了分布（上一轮只有 1 次）：**三次全 rc=0**，但它比不带 `--strict` 的
a1/a2 慢 ~13 s —— 而 `s3` 起始采样是 `node=27 cpu=[90,37]`，所以**这 13 s 不能算 `--strict` 的成本**，
本轮的精度分不开它和负载。

**继续挂账（不顺手归掉）**：上一轮的"分段能加到 338.8 s、余 14.2 s 未拆"这条仍未结。
用本轮同一套分段数重算，改后的预测是 184.4 s，而实测三点是 169.987 / 171.772 / 186.449
（极差 16.462 s）—— **要解释的余量（14.15 s）比改后自身的极差还小**，这个精度下分不开，
所以余量与那 ~58 s 台阶都保持"未定"，不因这次改动而结清。

边界：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 未碰、`.git` 内未动、
那 5 张 PNG 未删、未结束任何其他人的进程。

### 同日续二十：A/B 逐行比对合批改动 —— 抓到的不是"少一路 stdout"，是"整份诊断归零"

主控令只做一条：关掉我自己在"仍然没验证"里列的第 3 条 —— **没比对过改前/改后可见输出是否等价**。
方法：一份固定的 5 标记探针套件（两条 print 到 stdout、一条写 stderr、一条**不带换行**地 print
以 `{` 开头的内容、一条真 fail），改前那侧按当时 `release_check` 的调用形态取 `stdout+stderr` 全集，
改后那侧取 `run_console_suite()["detail"]`，逐行比集合。

**第一面（改后 = 上一笔 `adb38ed` 的实现）结果比预想糟**：

| 数 | 值 |
|---|---|
| 改前可见行数 | 14 |
| 改后可见行数 | **0** |
| 只在改前出现的行 | **14（= 全部）**，且 `run_console_suite()` 抛 `JSONDecodeError: Extra data: line 1 column 36 (char 35)` |

也就是说：测试自己 print 到 stdout 的东西确实被丢了（那是我以为的最坏情况），**但更坏的是** ——
④ 那个反例不是理论问题：一条不带换行的 `{` 开头输出会和 JSON 粘成同一行，
`startswith("{")` 选中混合行 ⇒ 解析崩 ⇒ `release_check` 把"跑过的套件"报成
"套件没能跑起来"，顺手吞掉失败正文与 skip 清单。**一条正常的测试 print 能让发布检查说谎。**

**修法**（`console/_preflight.py`）：JSON 走带制表符的哨兵行 `__PREFLIGHT_JSON__\t{...}`，
前后各一个换行；父侧按哨兵取**最后**一条，其余非哨兵行不再丢弃，而是作为具名的
`[stdout]` 段并进 `detail`，stderr 保留 `[stderr]` 段；`verbosity` 从 0 回到 1。

**第二面（同一份探针，改后 = 本次实现）三个数**：改前 **14** 行 / 改后 **17** 行 /
只在改前出现 **3** 行，五个标记两面全在（`PFMARK-STDOUT-001/004`、`STDERR-002`、`GLUE-003`、
`FAIL-005`），解析不再崩，计数 `tests=5 failures=1 errors=0`。那 3 行逐条对上，各有对应：

1. `{...}.PFMARK-STDERR-002 …`（改前把两路粘成一行）⇒ 改后拆成 `[stdout]` 与 `[stderr]` 两行；
2. 进度点 `..F.` ⇒ 改后 `...F.`（`verbosity=1` 补回来的，见下）；
3. `FAIL: test_d_fail (test_probe_io.ProbeIO)` ⇒ 改后是 `(console.test_probe_io.ProbeIO)` ——
   **测试 id 变成带包名**。不丢信息，但会破"按 id 字符串匹配 release_check 输出"的用法，
   具名记在这里，不假装它没变。

进度点那一条按令**没有用"报告正文已含失败信息"抵**：它是 `verbosity` 的产物，属于"为了合成一遍
顺手关掉一种输出"，所以补回 `verbosity=1` 而不是解释掉。

**钉成常驻用例**：新增 `console/test_preflight_capture.py`（4 条，整套跑完 0.612 s）——
三路各一个标记、`[stdout]`/`[stderr]` 段必须有具名标头、进度点行必须在、`Ran 5 tests` 必须在、
计数与正文不得互相替代、哨兵行不得漏进 detail。三条变异各自 RED、还原核 sha
（`7c86482ada95a83e identical=True`）：`verbosity` 退回 0 ⇒ 红在"三路"那条；
丢掉 `[stdout]` 那一路 ⇒ 同一条红；解析退回 `startswith("{")` ⇒ 4 条里 1 红 3 错（哨兵是承重的）。

现况：`Ran 213 tests OK`（161.527 s）、`release_check.py` rc=0（186.128 s）、
`_citations --verify` rc=0、`_readme_counts --verify` rc=0。
**继续挂账**：14.2 s 余量与 ~58 s 台阶本轮没动、也没顺手归因 —— 这次改的是采集与解析，
不产生新的耗时结论。

边界：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 未碰、`.git` 内未动、
5 张 PNG 未删；取证脚本在 `%TEMP%`，还原一律用快照 + 核 sha（不用 `git checkout`）。

### 同日续二十·补：三路合一之后，给人看的那一行被某条 print 顶掉了

上一笔把 stdout/stderr 并进 `detail` 之后，`release_check` 的摘要行取的是 **detail 末行** ——
于是 `[OK] console 单元测试 · …` 末尾变成了某条测试自己的 print
（实测为 `[ESCAPE_MECHANISM] import=[1, 0] compile=[1, 1, 1] pyc=1`）。信息没丢（计数与
`FAILED (…)` 都还在结构里），但**扫输出找 OK 的人会读空**。这条是我自己这次改动引进的，
不是历史遗留，所以记在同一天的账上。

处置：新增 `_preflight.summary_line(detail)`，按 `OK` / `FAILED (` / `ERROR` 优先、
再退到 `Ran N tests`、最后才退到末行；`release_check` 用它。
`console/test_preflight_capture.py` 加第 5 条用例，反例形状照实测写死
（detail 末尾挂 `SOME-TEST-PRINT [X] import=…`，中间才有 `FAILED (failures=1)` ⇒ 必须挑出后者），
并钉 `summary_line("")` 返回空串（不许抛）。

实测：`Ran 5 tests OK`（0.526 s，这个模块）；改后第一次 `release_check` 报
`failures=1`，那条失败是**我自己的用例数门**（README 写 213、实为 214），
`--fix` 后 `Ran 214 tests in 152.612s OK`、`release_check.py rc=0`（184.023 s），
摘要行回到 `… errors=0 skipped=0）· OK`。**这次没有跳过那一次红**：先让它红、再改、再复跑。

### 同日续二十二：真套件 A/B —— 合批顺手静音了 896 行 `ResourceWarning`，四处补回

上一条留的第 1 条洞（"A/B 只用了 5 条探针，没比过仓里 214 条"）本轮关掉，结论比探针严重。

**第一面（真套件）**：改前 = `python -m unittest discover -s console` 经 `_run` 收到的
`stdout+stderr`；改后 = `run_console_suite()["detail"]`。

| 数 | 值 |
|---|---|
| 改前可见行数 | **939** |
| 改后可见行数 | **43** |
| 只在改前出现的行（数字打掩码） | **898**，几乎全是 `ResourceWarning: unclosed file …` |
| 裁决类行是否丢 | 否（`verdict_only_before=0`） |

机制**不是**"stdout 那一路没接上"（那一路接通了），而是：`unittest.main()` 会给 runner 传
`warnings="default"`，我手写的 `TextTestRunner(stream=_buf, verbosity=1)` **没传** ⇒
`ResourceWarning` 落回默认过滤器（对它恰好是 `ignore`）⇒ 整类诊断被**静音**。
这是上一条 `verbosity=0` 同一个错的加重版：为了"合成一遍"顺手关掉一种输出。
而那 898 行 warning 又指向**我自己本轮新写的用例在漏句柄**
（`test_compare_csv_census.py`、`test_dead_charging_fields.py` 共 7 处
`io.open(…).read()` / `open(…).read()`）。

**四处处置**：① 子进程 runner 加 `warnings="default"`（stderr 仍具名并进 `detail`）；
② 那 7 处泄漏改 `read_text()/read_bytes()`；③ 常驻用例
`test_resource_warnings_are_not_silenced` —— 探针故意漏一个句柄再 `gc.collect()`，
断言 `detail` 里必须有 `ResourceWarning` 且 `[stderr]` 标头在；
④ 再补 `summary_line` 一刀：它原先在**合并后的全文**里倒着找 `OK`，而 `[stdout]/[stderr]`
是追加在正文之后的 ⇒ 任何一条测试打印以 `OK` 开头就能顶掉真裁决；改成先截到第一个段标头再找，
并把混合形状写死成断言（`FAILED (failures=1)` 必须赢过 `OK 这只是某条测试自己打印的一行`）。

**第二面（同一把尺子复测）**：改前 **196** / 改后 **198** 行；`warning` 条数 **92 / 92**、
`ResourceWarning` 字样 **93 / 93**、只在任一侧的 warning 类型集合**均为空**；
`verdict_only_before` 剩 1 条，就是上一条已具名的 **id 带包名**差异
（`(test_readme_counts…)` → `(console.test_readme_counts…)`），同一条信息不是丢失。
行边界残差全部来自"进度点串与 warning 在改前挤同一条裸 stderr、改后分属两路"。

**变异**：P-D 去掉 `warnings="default"` ⇒ 红在 `test_resource_warnings_are_not_silenced`；
P-E 把 `summary_line` 改回全文倒找 ⇒ 红在 `test_summary_line_is_the_verdict_not_the_last_print`。
各自 RED，还原核 sha `d80dc6f86b72395f identical=True`。

**耗时不结旧账**：`Ran 215 tests in 88.368s`、`release_check.py rc=0` 用时 **131.325 s**
（上一轮同两条是 152.6 s / 184.0 s）。降了，但**不能读成"这次把性能修好了"**：同机背景从
`node 10–27` 掉到接近空闲，且这轮顺手去掉了 92 条 warning 的格式化开销，两个因素没拆开。
**14.2 s 余量与 ~58 s 台阶继续挂账。**

**仍然没验证**：绿跑时 warning 不进**可读输出** —— `release_check` 只在红的时候印 `detail` 尾 3000 字，
改前后都这样；这次对齐的是"捕获得到"，不是"看得见"。

边界：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 未碰、`.git` 内未动、
5 张 PNG 未删、未结束他人进程；取证脚本仍在 `%TEMP%`。

### 同日续二十三：A/B 从"我手动量过一次"变成仓里的一把尺子，量具自己被抓出四个错

上一条留的两条洞（"27 条行差没逐行证明"与"warning 种类全集未清点"）本轮关掉，方式不是再手动
跑一次，而是把它做成常驻工具 `console/_suite_ab.py` + 用例 `console/test_suite_ab.py`（9 条）。
判据、消融、范围下限都在仓里，下一个人能重算，不必信我这段话。

**真套件那一轮（同一份工作树代码，只换采集方式；`Ran 225 tests`）**：

| 数 | 值 |
|---|---|
| 原始行数 改前 / 改后 | 54 / 56 |
| 可比单元 改前 / 改后 | 52 / 53 |
| **only_before / only_after / common** | **0 / 1 / 52** |
| 进度点总数（两侧 / testsRun） | 225 / 225 / 225，`identity=True` |
| 改后独有那 1 条 | `<section-header>` —— 采集器自己的 `[stdout]`/`[stderr]` 标头，不是内容 |

`--compare` 退出码 0。**only_before=0 就是这一轮要的三个数里的那个"零丢失"**：改前那条命令
收到的每一行，归一化之后都能在现在的 `detail` 里点到名，不需要"补回"，也没有"不可达"。

**这把尺子有牙（不是"没东西可比"的 0）**：
- M2 丢掉 stdout 那一路（更早一轮真实发生过）⇒ B 面塌到 **3** 个可比单元，被范围下限当场拒比
  `[AB_RANGE] A=52 B=3`，`_bite()` 把"拒比"归成咬到；
- M1 去掉 `warnings="default"`（上一轮真实发生过）⇒ **本轮在这一份取证上比不出差别**：
  漏句柄已被我自己修光，A 面带出处 warning=0（`[ABLATION_VACUOUS]`，`--ablate` 退出码 2 而不是 0）；
  非空转的 M1 证据有两条 —— 本轮内**修 build_probe 之前**那一轮真套件（`Ran 224 tests`）
  实测 `only_before=12`（4 条发射行 + 4 条 `Enable tracemalloc` 伴行 + 4 条源码回声行），
  以及常驻夹具 `[SA_M1] only_before=3`（夹具故意漏一个句柄，随 discover 与 `release_check` 跑）。

**四个自己被抓出来的错**（都是量具的错，不是被测对象的错）：
1. **`warning_census` 把量具自己算进了被测量的量**：原先按类名在全文里计数，真套件报
   `ResourceWarning:6` 而带出处的只有 **2** 条 —— 多出的 4 次是采集器自己印的
   `[PF_WARN_CENSUS]` / `[PF_WARN_CHANNEL]` 两行加每条 warning 的 `Enable tracemalloc` 伴行。
   现在数**带出处的发射行**（`文件:行号: XWarning:`），并把 `全文提及=` 并排列出：
   自占的那部分要看得见，不是抹掉。夹具 `test_warning_census_is_not_inflated_by_the_instrument`
   把形状写死（`warnings=ResourceWarning:2 带出处=2 全文提及=6`），另一条断言钉"只有字样、
   没有出处 ⇒ 带出处=0"。
2. **`build_probe()` 自己漏句柄**（两处 `io.open(...).write(...)`），而且被两个测试类各调一次
   ⇒ 真套件里 4 条 `ResourceWarning`。改 `write_text` 后 `release_check` 印
   `[WARN_CENSUS] warnings=ResourceWarning:0 带出处=0 全文提及=3 suite=225` —— **真套件现在零泄漏**；
   探针那个故意漏的句柄（`PROBE_SRC` 里的 `test_f_leak`）保留，它才是钉 `warnings="default"` 的证人。
3. **A 面把 stdout 与 stderr 直接相接**：夹具里那条不带换行的 print 与 stderr 的进度点行粘成一行
   （实测 `{"PFMARK-GLUE-003": "no newline"}....F.`）⇒ 点串数不出来、恒等式响在量具自己身上。
   改成 `join_streams()` 补一个换行。这就是 `[AB_ONLY_AFTER]` 那类粘连的自食版。
4. **进度点识别从"长度 ≥10"改成"行首连续进度符且必须含 `.`"**：小套件只有 6 个点，长度阈值会把
   它当正文（`[SA_*]` 第一轮就是这么红的）；要求含 `.` 是为了不把 `FAILED` 开头那个 `F` 数成一个点。
   识别判歪的后果由 `[AB_DOTS_MISMATCH]` 兜住 —— 整轮作废，不是悄悄放行。
   同时 `_preflight` 把哨兵解析与三路合一抽成 `split_sentinel()` / `merge_detail()`，
   `_suite_ab` 复用而不是照抄，避免"尺子的口径"和"产品的口径"长成两份。

**warning 种类这一族到此的清点**（能证的部分）：本轮**最早那一份四件取证**（`Ran 215 tests` 那轮，
`a_stdout/a_stderr/b_stdout/b_stderr`）里出现的 warning 类别只有一个 ——
`grep -oE '[A-Z][A-Za-z]*Warning' | sort | uniq -c` = `12 ResourceWarning`、其他类 **0**；
同一次核对用 grep 独立数带出处发射行 = A 侧 2 / B 侧 2（正例对照：同一把 grep 数 `Ran 215 tests`
得 2，所以那两个 2 不是量具瞎）。到 `Ran 225 tests` 那一轮，两侧带出处都是 **0**（泄漏修光之后
自然没有类可点），所以"种类全集"这条只在还有发射的那一份上成立。
**清点点不到"从未触发的类别"** —— 那不在可观测范围里，明写为未验证。

**耗时**：`release_check.py rc=0` 用时 **114.608 s**（同一条命令本轮早些时候是 100.3 s 与 147 s，
`--skip-e2e` 那一跑 100.3 s 不算同口径）。三个数摆在一起只说明"这一档几十秒的抖动还在"，
**不能读成性能已被修好**；14.2 s 余量与 ~58 s 台阶继续挂账，本轮没动它。
本轮为了拿这三份可比读数，额外真跑了 3 遍套件（`--capture` 两遍 + `--ablate` 里 M1 一遍），
这笔验证成本也要记账，不算进"门变便宜了"。

**仍然没验证**：见本轮末尾给的那份清单（结项 68 次/GA 3600·5·seed 未重跑、PNG 像素未核、
A2 两字段的仓外取值未知、`--strict` 只在非完整环境跑过、论文十七处只报不改）。

边界：`VERSION` 仍 `1.0.0`、未 push、无新依赖、未动 DDL、`paper/` 未碰、`.git` 内未动、
5 张 PNG 未删、未结束他人进程；取证与比对脚本本轮**进了仓**（`console/_suite_ab.py`），
原始四份取证仍在 `%TEMP%`（它们是一次性读数，不是产物）。











`VERSION` 保持 `1.0.0` 未动，未打 tag、未发 release、未 push。

起因是可复现性最硬的一条反例：**评审照 README 原文跑就是红的**。

```
$ python -m unittest discover -s console -p "test_*.py"     # README:131 原文
Ran 75 tests ... FAILED (errors=5, skipped=6)                # 系统 python 3.13.5
  ModuleNotFoundError: No module named 'fastapi' / 'shapely'
  AttributeError: module 'environment' has no attribute 'DEFAULT_EPISODE_MAX_STEPS'
```

他不会先建 venv 再跑，看到这屏会以为**仿真坏了**。修完两个解释器都干净：
系统 python `OK (skipped=12)`、`.venv310` `Ran 130 tests OK`，退出码均 0。

**① `console/_preflight.py`**：测试模块在重导入之前 `require(...)`，缺包就整模块 skip，
原因里写清缺哪些模块、对应 pip 名、受影响测试模块，以及项目 venv 解释器的**绝对路径**
与可粘贴的重跑命令。`python console/_preflight.py` 单独跑也一眼可见。

**② 那条 AttributeError 不是缺包，是名字撞车**：`console/test_command_console.py`
会往 `sys.modules["environment"]` 装轻量桩，并在真实导入失败时**故意留着桩**（对它自己合理），
于是"episode 步数单一真源"这条**地基守门用例**拿到假模块 —— 常量确实在
`frontend/environment.py:91`，名字对了但不是那个文件。改为 importlib 按**文件路径**加载、
不写进 sys.modules，判据从"属性存在吗"升级为"是不是那个文件的那个值"。
单独跑报 ModuleNotFoundError、聚合跑报 AttributeError，这个差异本身就是撞车的证据。

**③ README 计数从手抄变成跑出来**：原先写"7 个文件 / 74 个用例"（实测 14 / 130）与
"2 个文件 / 21 个用例"（实测 2 / 24）。`console/_readme_counts.py --verify` 不一致退出码 1，
并接进 discover。两个坑都记下了：
- **测量随解释器漂**（缺依赖时 12 条所属模块整模块 skip、不进计数，同一命令量出 130 与 77），
  所以 `measure()` 固定用项目 venv 解释器起子进程量，找不到 venv 就报错，绝不凑数；
- **自证用例自己硬编码了 "13 个文件 / 128 个用例" 当锚点**，`--fix` 一跑锚点就失效 ——
  检测手抄计数的用例自己不能靠手抄锚点，已改为正则取当前值再 +7 扰动。

另补 `test_detector_itself_is_not_vacuous`：合成喂合法/坏引用各两条，要求 0 报 / 2 报。
只读真文档的检测器一旦被放宽成"跳过不存在的文件"，真文档干净时它照样绿 —— 这条主动测红它。

**本轮未验证 / 未闭合**：论文图仍需按 3600/5/seeds 重跑 GA 才能对齐口径（未跑）；
`part_of_yangpu.osm` 仍无内容哈希被钉（只有 loader 计数作行为代理）；
`results/compare/plots` 20-vs-15 归档缺口待拍板；`--record-into-evidence` /
`--publish-latest` 的正向写盘只在可回滚前提下验过；对比页拒绝横幅只验到接口契约与
`v-if` 存在性，没拿到屏幕截图。

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
