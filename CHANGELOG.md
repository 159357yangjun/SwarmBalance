# Changelog

## [Unreleased]

### 2026-10-08（第三十二笔）：#70-P1 裁定 (i) 落地 —— P3 普查集改为按谓词从盘上现算，谓词两面各配证人；另交阶段② g2teeth 纸面标定方案

基线 b25634c。主控批 (i) 不批 (ii)，并补两条要求：① 该门要先红后绿归档；② **谓词本身要两面**——写了但不还原才违规，正确还原的不得被拉进名单当违规。硬边界照旧：未 push、未打 tag、paper/ 未碰、生产代码零改动。

**(i) 实现**：`console/test_p3_no_cross_test_residue.py` 的 `CLEAN_MODULES` 从手写 5 个具名模块改为 `census_modules()` 按谓词现算 ⇒ 基线 **covered=10 / matching=10**（原手写名单漏了 5 个写入者）。判据写成 `(matching - covered)==0`，两个数都来自本轮扫描并排印出对账（`[P3_COVERAGE] modules_covered=10 modules_matching_predicate=10`）。新增 test_C（覆盖率恒等式）、test_D（豁免表理由+失效，基线空表）、test_E（谓词两面）、test_F（自我观测）。

**范围与判据分开（这是要求②想通的那一点）**：源码谓词只决定**观测范围**（写了全局态就入册，不看有没有 tearDown —— 用 has_restore 去豁免等于给"加一个空 tearDownClass"留逃生口）；**是否违规**由运行时 diff 决定（正确还原者 env_changed=False / path_added=[]，在 test_A 自然不报红）。test_E 三面断言钉住这个划分。

**谓词四次自纠（每一次都是一手实测，不是推演）**：
1. 朴素谓词命中 **37** 个模块 ⇒ 绝大多数只是把仓库永久目录挂上 sys.path 的 import 引导，属误伤；
2. 排除 raw-string 子进程脚本正文（c1_lifecycle_gate:48 / h3_lifecycle_gates:48 / observer_zero_drift:41 里的 setenv 都在新进程里执行）⇒ 降到 27；
3. 改成"文件级看有没有 tempfile 字样"又误伤 7 个（compare_csv_census / portable_runtime / stale_bytecode… 只是别处用了临时文件）⇒ 一度涨回 17；
4. 定稿为**极窄数据流**：只认"`X = tempfile.mkdtemp()` 之类赋值出的名字，且 insert 参数里出现它"⇒ 回到 **10**，且注入样本 `_zzd = mkdtemp(); sys.path.insert(0, _zzd)`（insert 行里没有 tempfile 字样）照样被抓到。宁可漏不误伤：漏的那类由 test_A 运行时 diff 兜住。

**先红后绿归档（要求①）**：临时造 `console/test_zz_redface_tmp.py`（插临时目录、无还原），跑完即删。读数 `[A] predicate_hit_new_module=True covered=11` / `[B] gap_if_list_handwritten=['test_zz_redface_tmp'] -> P3_COVERAGE_GAP red`（模拟"有人把名单写死回去"）/ `[C] runtime path_added=True` ⇒ **结构面与运行时面都抓到注入**；还原后复绿。

**顺带修掉两处本门自身的缺陷**：
· 自我嵌套：本门也在普查集里，子进程内再"真跑完自己"会起第二层全量普查 ⇒ 实测堆到 **18 个 python.exe** 仍不收敛、只能外部终止（我已把我起的这些进程清干净，未动别的会话的）。修法=子进程固定跳过自身那一支 + 显式证人 `SELF_EXCLUDED=yes`；丢掉的覆盖面由 **test_F** 用另一条通道补回（父进程加载并跑完本模块的**有界**用例集，再 diff env/sys.path ⇒ `[P3_SELF_VERDICT] env_left=0 path_added=0 tests_run_in_self=2`，0.25 s）。
· `_CHILD` 里曾写 `SELF = SELF_NAME` ⇒ 子进程拿不到主模块的全局名，直接 NameError 让整条门跑不起来（已改字面量并写明原因）。
· 我自己的红面驱动脚本第一次也因中文 print 在 GBK 下 UnicodeEncodeError 中断 ⇒ 改纯 ASCII 重跑（这条形状上一笔刚记过，这次是我自己踩）。

**两处真实残留顺手补齐**（普查改版后立即暴露）：`test_h3_real_pop_events` 的 setUpClass 补记账+tearDownClass；`test_speed_fallback_gate` 删掉模块顶层那次 `_install_gate_config()`（它在"本门因缺 OSM 被 skip"时仍会把环境变量改走，且 `_pf_kernel()` 每次都会重装 ⇒ 顶层那次从来不是判据的一部分）。

读数汇总：`Ran 7 tests OK`（P3 全套，367 s）；回归 `test_h3_real_pop_events + test_speed_fallback_gate + test_p2_*` `Ran 15 tests OK (skipped=1)`，G1/G2 正常、`[P2_VERDICT] violations=0`；citation exit=0（problems=0）；README 计数由工具核对一致（console 49 文件/**356** 用例，比上一笔 +4 = 本笔新增 test_C/D/E/F）。

**(ii) 登记为挂账（本轮不实现）**：触发条件采纳主控建议并收紧为三条 —— ① (i) 的红发生一次以上（即普查门抓到过新的跨测试全局态写入点）；② 开始阶段② g2teeth 重标定**之前**；③ 任一时刻出现"聚合红但单跑绿"的新案例（那是顺序相关的最直接症状）。判据草案（字母序 vs 逆序跑有界子集、逐用例比对状态集合与关键读数、两侧各印 Ran N）留在 docs/P70_which_gate_is_the_resident_one.md §3(ii)。

**阶段② 纸面方案已交**：docs/P70_g2teeth_calibration_plan.md —— 命题拆两层（L1 机制层用合成场景 K1–K6 做常驻门、L2 真实工况读数只作信息不进退码），阈值 15 的来源如实写为"历史常数、仓内无推导依据"且**本次不动它**，冻结三元组（阈值来源+夹具集合+生产文件哈希版本），并列明四种允许重开 calibration 的情形与三种不允许的理由。**等批才改码。**

### 2026-10-08（第三十一笔）：#70-P1 定性更正 —— 第 6 条的常驻门是 P2+P3，P1 不在其职责上；明写还欠两条（只给判据，不动手）

基线 f75f423。主控指出我把两问答成了一问：他补的是"门没跑起来时报红还是静默"，上位裁定第 6 条要的是**一条常驻 order-independence 回归门（后人重新引入全局污染时会红）**。我上一轮那句"三扇门都报非零退码"容易被读成"六条判据齐了"⇒ **就地收回一半：三门 ≠ 第 6 条已满足**。

一句答：**P2 是那条常驻门的主体**，但按裁定原话的范围量，**还欠两条**（§3，先判据待批，本轮未动一行实现）。

判别式实测（两种形状各注入一次，跑完即 `git checkout` 还原，收尾工作树为空）：
- **形状 A = 重新引入 P1 那笔污染**（把 r2 的 loader 换回 `from environment import Environment`）⇒
  **P2 FAILED** `[P2_NAME_IMPORT] test_r2_destination_without_load.py:setUpClass … （不在册）` ✅会拦；
  **P1 却 OK** `[P1_VERDICT] order_ab_rc=0 order_ba_rc=0 optimize_ab=11454 optimize_ba=11454` ❌看不见。
  ⇒ 关键事实：**P1 对这笔污染本身已经无感**——被污染的 G2 已子进程化、不再吃主进程常量。所以第 6 条不能指望 P1；它守的是"G2 这条消费路径仍与顺序无关"。这正是我上轮说错的地方。
- **形状 B = 只改环境变量不还原**（把 r2 的 `tearDownClass` 改名使其失效）⇒
  **P3 FAILED** `[P3_RESIDUE] 跑完 5 个模块后仍有未还原的全局态：[{"kind": "env", …}]` ✅会拦；
  P2 也红，但**成因不对**（是 P3 在被污染树上跑时自己漏了 env 被它附带捕获），不是 P2 认得了这种形状 ⇒ P2 作为源码结构扫描**天然看不见**这一类。
⇒ 定性：第 6 条目前由 **P2 + P3 两扇合起来**覆盖两类形状，各有实测正例；P1 不在这条职责上。

还欠的两条（只写判据，等裁再做）：
(i) **覆盖集是手写名单**：P3 的 `CLEAN_MODULES` 只有 5 个具名模块，新写测试改了 env/sys.path 不还原就**根本不进它视野**。拟判据=清单从盘上现算：凡含 `os.environ["SWARM_BALANCE_SIM_CONFIG"] = …` 或 `sys.path.insert(…)` 的 `console/test_*.py` 必须在普查集内，命中而不在集内 ⇒ `[P3_COVERAGE_GAP]` 红（判据=缺口 0，不是"名单里都绿"），并印 `modules_covered / modules_matching_predicate` 两个本轮真数对账。代价：单轮耗时上升（现 5 模块≈8 s，谓词命中约 11 个）。
(ii) **没有一条门断言"套件整体与发现顺序无关"**：现有 P1 只测一对顺序、只盯一个读数。拟判据=discover 字母序 vs 逆序各在 fresh process 跑一个**有界子集**（不含 OSM-booting 慢测，免得把并发假象请回来），逐用例比对状态集合与关键读数，差集非空 ⇒ `[P1_ORDER_DEPENDENT]` 红；两侧各自印 `Ran N tests` 分母。代价与局限明写：最贵的一条，且子集是我选的 ⇒ 只证"该子集顺序无关"，不外推全仓。
不一上来做 (ii) 的理由：(i) 便宜且直接堵真缺口；(ii) 的子集范围与每轮成本要先由主控定，我不替他扩范围。

具名定性文档：docs/P70_which_gate_is_the_resident_one.md（含两次注入的原始读数与复算命令）。
登记接受：g2teeth 仍 skip（属阶段②）；#69-C6 的 C2 前提(ii) 两向皆盲已入档、不复活。
硬边界照旧：未 push、未打 tag、paper/ 未碰；本笔只加一份文档 + CHANGELOG，**代码零改动**（`git diff --numstat` 见提交）。

### 2026-10-08（第三十笔）：#70-P1 测试隔离 —— 污染源定位到行 + 消除"谁先 import"这件事 + 两扇顺序门（生产零改动）

基线 5fc4471。上位裁定把"阶段通过"定义成六条**结构事实**（不是"这次聚合刚好绿"），本轮按 #70-P1 授权范围做①②③三件。硬边界照旧：未 push、未打 tag、paper/ 未碰；**生产代码零改动**（`git status --short frontend/ experiments/ console/server.py console/sim_session.py` 输出为空 ⇒ drone.py 三段、environment.py 皆未动，本笔只改测试与文档）。

**① 污染源本体（不停在"import 顺序有关"这句描述）**：三方链，逐步行号与一手读数见 docs/P70_import_order_pollution.md。
`console/test_r2_destination_without_load.py:30` setenv(出厂 config) → `:34` `from environment import Environment`（**首次 import 就发生在这一行**，由拦截 `builtins.__import__` 打栈实证）→ `frontend/environment.py:87/:100/:105` 模块级冻结 CFG/FLEET_MIX/DEFAULT_NUM_DRONES 成 10/{5,3,2} → `console/test_speed_fallback_gate.py` 随后换 SWARM_BALANCE_SIM_CONFIG 已太晚 ⇒ PSO buffer 峰=2 < 阈值 15 ⇒ optimize 零调用 ⇒ `[pso][NO_DENOMINATOR]`。**被改动的全局态 = Python 模块缓存 `sys.modules["environment"]` 里那份 import 期冻结的常量**（另含 `SWARM_BALANCE_SIM_CONFIG`、`sys.path`）。本轮自纠两处错判一并入档：先前"r2+speed_gate 两方"漏了第三方；先前"r2 不 import 重货、是别人干的"源于只 grep 顶部 40 行的 `^import`，漏了函数体内的 import。

**② 修复 + 六条判据落地**：
1. G2 改为**每算法各起干净子进程**跑完整真路径（子进程自己写重载配置、在 import 之前 setenv），主进程常量不再参与判定；机队规模由**被测那份进程自报** `num_drones==6` 核对（短码 `[GATE_FROZEN_BY_FOREIGN_IMPORT]`）。
2. **消除"谁先 import"这件事本身**（不是点修 r2）：11 处从"按名字 import 内核"迁到 `console/_preflight.py:load_kernel_environment()`（按文件路径 exec、不进 sys.modules、用完还原 sys.path）—— r2 / c1_destination_leg / c4_is_carrying / h_r7 / h3_real_pop_events / route_planner_equivalence / height_binary_gate / environment_incidents / phase1b1_distance_experiment / phase1b2_eta(×4) / speed_gate 的 `_episode`。`test_environment_incidents` 原先还"发现桩就删掉再按名字重导"（替全进程决定这个名字指向哪份代码），一并去掉；height gate 改为持有**自己那份**内核引用、只还原自己那份。留在主进程按名字 import 的只有两类且结构上必须：生产代码 `console/sim_session.py:43`（reload 语义依赖名字绑定，不在测试侧改动范围）与 `test_command_console.py`（刻意装桩、自带 `tearDownModule` ⇒ 由 P2 的 test_C 单独管"装了必须有复原路径"）。
3. **残留记账还原**（判据③）：r2 补 `tearDownClass` 还原 `SWARM_BALANCE_SIM_CONFIG` + `sys.path` 快照；建 P3 普查门时又实测抓到四处同样改了不还原的，一并补齐 —— c1_destination_leg、c4_is_carrying（各加 `setUpClass` 记账 + `tearDownClass`）、h_r7（它在**用例体内** setenv ⇒ 用 `setUp`/`tearDown` 成对切换）。

**③ 两扇新门，两面配齐**：
- `console/test_p1_order_independence_gate.py`：GREEN=两种显式相反顺序（r2→G2 / G2→r2）各跑 fresh process，双双 rc=0 **且** `[G2/pso] optimize` 读数逐字相同（只断"都通过"不够——读数漂移也是顺序相关）；RED=注入复刻 r2 形状的已知污染样本，断言它确实把 DEFAULT_NUM_DRONES 冻成出厂 10，否则报 `[P1_INJECT_NO_EFFECT]` 而非默默绿。实测读数：`Ran 2 tests OK` / `[P1_AGREE] … optimize=11454 一致` / `[P1_TEETH] 注入生效…冻成 10`。诚实边界写在 docstring 里：B 面证"污染机制仍在"，A 面才证"目标不被带偏"，二者不可互替。
- `console/test_p2_no_name_based_kernel_import.py`（新增结构门）：扫 console/test_*.py 找主进程内按名字加载内核的语句，判据=命中 0，豁免须在册且带理由，**同时核"条目还在/已消失"**（防白名单变万能钥匙）。基线白名单为**空表**（迁移完 speed_gate 后测试侧已无合法理由按名字读内核）。三面实测：清洁树 `OK`（扫描 48 文件、命中 0、在册 0、已消失 0、普通字符串待确认 4）；负例注入被抓（第 5 行）；raw-string 子进程脚本不误伤；**真实变异**（把 c4 的 loader 换回 `from environment import Environment`）当场 `FAILED [P2_NAME_IMPORT]`，还原后复绿。另有 test_C 专管装桩模块"装了必须有 tearDownModule"。解析纪律：docstring 用 AST 识别（第一版用"独立成句的字符串"启发式会误伤拼接串）、隐式拼接串被 tokenize 合成单 token（实测 start=99/end=102）⇒ 普通字符串只按语句起始行登记，避免整块误豁免。
- `console/test_p3_no_cross_test_residue.py`（新增残留门，判据③的常驻证人）：fresh 子进程里**真跑完**指定模块（含 setUpClass/tearDownClass），前后 diff `SWARM_BALANCE_SIM_CONFIG` 与 `sys.path`，判据=空；并逐模块点名（不靠聚合的巧合）。三面实测：`Ran 3 tests OK` — `[P3_CLEAN] 5 个模块全程跑完后残留=0` / `[P3_TEETH] 注入生效：读到残留 [{"kind":"env",…,"after":"/tmp/p3_injected_not_restored.json"}]` / `[P3_WITNESS] 正例证人通过`。两次自纠入档：(i) 第一版用 `loadTestsFromName` 只 import 不 run ⇒ 那个"0 残留"是量具到不了、不是现场干净（r2 的 setUpClass 根本没执行）；(ii) 注入样本一度只进 PYTHONPATH 却按 `console.<名>` 加载 ⇒ 样本压根没跑，会把"看不见"误报成"注入无效"，故补正例证人。**`sys.modules` 这一面实测撤掉**：任何真运行都会正常导入 drone/task/route_planner/config.config_loder 等 12 个名字，那是运行副作用不是"改了没还原"，当判据会让门永远红、只能靠放宽过活；该面改由 P2 从源码结构侧守。随机状态/注册表单例**未测**（本轮没实测到有人改了不还原 ⇒ 明写无人证得过，不写都会绿的门）。

**④ G1 这条门的修法换了三次，全部留档（防止下一个人在同一处再猜）**：
(a) 在主进程 setUpClass 核对机队 ⇒ ORDER-A 仍红（把已免疫顺序的 G2 判死）；
(b) 改成"按路径加载一份内核 + 读主进程那份常量核对" ⇒ 全量复跑仍红 `[GATE_FROZEN_BY_FOREIGN_IMPORT] DEFAULT_NUM_DRONES=10`，因为**真正的第一个 importer 是生产代码** `console/sim_session.py:43`（经 `console/test_server_guards.py:22` 的 `import console.server` 拉进来；判别式=拦 `builtins.__import__` 打栈，输出 `[FIRST environment] … sim_session.py:43` / `>>> first import happened while loading: console.test_server_guards`）；对着一个合法的生产名字绑定喊狼是不行的。
(c) 改成"模块顶层装一次配置 + 按路径加载" ⇒ 第三次全量复跑仍红 `[GATE_CONFIG_NOT_APPLIED] DEFAULT_NUM_DRONES=10`：字母序在 speed_gate 之后的 `console/test_swap_time_gate.py:63`（及 `test_sla_consumption_gate.py:68`）会把同一个环境变量改走 ⇒ 我 import 时装的那份早被人顶掉。
**定稿**：`_pf_kernel()` 每次取内核前重装配置、按路径 exec 一份、当场核对该内核的常量指纹 ⇒ 校验对象与消费对象是同一个模块对象，与"谁先 import""谁后改 env"都无关。判别式实测三面：`sla+g1` 10 tests OK / `r2+g1` 5 tests OK / 单跑 g1 OK，断言面（取值集合）三面同为 `[14.0, 20.0]`。
⚠ 诚实标注：G1 的**采样次数**随前序模块是否改走过 task_generation 配置而在 43200/28824 之间变，它不是本门判据、也没被写成判据；若要把它钉成判据得先让它对配置注入时序不敏感。


### 2026-10-08（第二十九笔）：#69-C6 追问更正 —— 6-A 未守住 C2 命题，§6-D 那句升级就地作废

基线 2e5931a。主控追问"白名单相等门守的是 is_free=True 赋值点集合，它真的守住 C2 的命题了吗"。**实测答案：没有 ⇒ 选①**，C2 仍属 [P]/[D]。

C2 有两条承重前提：(i) 赋值点集合有限已知（6-A 守这条）；(ii) assignment 移除早于变空闲（env:1212→:1221/:1230 早于 drone.py:342；:545 前先 :563 pop 走）——**6-A 完全不看 (ii)**。

判别式实测（临时副本，非推理）：把 drone.py route-exhausted 分支 `self.is_free = True` 从 line 342 上移到 pop(line 328) 之前，重跑 6-A census ⇒
`census 键集变化: 新增=[] 消失=[] / 互换后 集合==白名单 ? True / ⇒ 仍然绿（没抓到）`。
根因：键是 `(文件, 函数名#同函数内第几处)`，同一函数内部挪语句既不增键也不减键 ⇒ 本门能拦"多一个入口"，拦不住"入口被提前到服务终结之前"。

处置：docs/#69_结项报告.md §6-E 纯追加(+19/-0)记作废与实测读数，**§6-D 原句保留不删**（就地标效力作废），并把 §5.3"C2 无门可守"恢复为有效残余盲区、明写不得对外称 C2 已有门守。
门文件 docstring 同步收窄：加一段"只覆盖前提 (i)、不覆盖 (ii)"并引 §6-E，防下一个读者重犯我这个错。测试仍 4 tests OK、citation --verify exit=0、生产代码零改动。

**⑤ 六条结构事实的落地状态（本轮实测，不含推断）**：
| # | 判据 | 读数 | 复算命令 |
|---|---|---|---|
| 1 | fresh process 单跑=聚合 | G2 四算法 optimize 逐字同：pso 11454 / ga 114 / ortools 120（聚合与单跑各一遍） | `python -m unittest discover -s console` vs `python -m unittest console.test_speed_fallback_gate` |
| 2 | 换发现/import 顺序结果不变 | `[P1_AGREE] 两种顺序均通过且 pso optimize=11454 一致` | `python -m unittest console.test_p1_order_independence_gate` |
| 3 | 无未还原的全局态残留 | `[P3_CLEAN] 5 个模块全程跑完后残留=0`（env/sys.path 两面，逐模块点名亦空） | `python -m unittest console.test_p3_no_cross_test_residue` |
| 4 | g2_all_four 不依赖前序模块初始化 | 该用例现在只在子进程里跑，父进程常量不参与；两向顺序皆绿（见 #2） | 同 #2 |
| 5 | 除具名 skip 外无顺序相关红项 | 本笔定稿后全量 `Ran 352 tests in 1092.777s` / `OK (skipped=5)`，退码 0；五条 skip 全部具名（见下） | 见下"套件分母" |
| 6 | 有新的顺序无关回归门 | P1（运行时两向对撞）+ P2（源码结构扫描）+ P3（残留 diff）三扇常驻门，各自两面/正例证人齐 | 三门各自单跑 |

`citation --verify` exit=0（183 条 path:line，74 条带锚点，problems=0）。

**套件分母（口径要分开）**：定稿后那一轮全量 = console **`Ran 352 tests ... OK (skipped=5)`，退码 0**，与 `_readme_counts.py --verify` 现算的总数一致（console 49 文件 / 352 用例、experiments 3 文件 / 32 用例）。本笔过程中另有一轮是 `Ran 349 ... OK` —— 差的 3 条是当时刚建、尚未计入那一轮的 P3 门。**引用哪个数都要说清是哪一轮、哪一棵树**。复算命令：`python -m unittest discover -s console -p "test_*.py"`（实跑）与 `python console/_readme_counts.py --verify`（总数）。
五条具名 skip 原文：`[OLD_IS_BASELINE_AUDIT_SNAPSHOT]`（old 面不作通过/失败判据）、`仅 mutation 面执行`、`[H_SKIPPED_NOT_FROZEN_BASELINE] 该基准只对 580c937 有效`、`正式配对实验耗时长，显式 SWARM_1B1_FULL=1 才跑`、`[GATE_CALIBRATION_STALE]`（g2teeth，#69-H3 裁定①留的显式 skip，既非通过也非失败）。

**提交后的复算门**（两笔 commit 落地后原样再跑一遍，防"提交后才坏"）：`python -m unittest console.test_p1_order_independence_gate console.test_p2_no_name_based_kernel_import console.test_p3_no_cross_test_residue` ⇒ `Ran 9 tests ... OK`，六条读数行齐（P1_AGREE/P1_TEETH、P2 命中 0/豁免 0、P3_CLEAN/P3_TEETH/P3_WITNESS）。注意 P2 那行现在印 **扫描 49 个测试文件**（新三门自身已入库并被扫到），与上面"清洁树 OK（扫描 48 文件）"那条是**不同时刻的两棵树**，不是同一个数漂了。工作树收尾 `git status --short` 为空、`git stash list` 为空。

**残余边界（写清楚没做到什么）**：(i) 生产侧 `console/sim_session.py:43` 的名字绑定仍在——它是 reload 语义所需，改它属另一类授权；(ii) P3 只测 env/sys.path 两面，随机状态与注册表单例未测（本轮没实测到"改了不还原"的样本）；(iii) G1 的采样次数随配置注入时序漂移，已明写不作判据。

**#69 尾项（6-A 是否守住 C2）不在本笔范围**：那个实测问题已由先前两笔（42919a5 / 5fc4471）闭合 —— §6-E 以两种变异证明 6-A 对前提 (ii) 两向皆盲、§6-D 那句"升为 [G]"就地作废，C2 仍属 [P]/[D]；选项③（补一条覆盖顺序的门）判据仍未写死、未动手，待另行放行。#70-P1 没有顺带改动它。

**⑥ 补条实测：门自己没跑起来时报红还是静默（原始输出落盘 docs/取证输出/p70_p1/）**
把三扇门在缺依赖的解释器（`Python310/python.exe`，实测无 shapely/fastapi）下各跑一次，与清洁树+venv 并列：
P1 `FAILED (failures=1, errors=1)` / P2 `FAILED (errors=2)` / P3 `FAILED (failures=1)` ⇒ **退码全为 1，无一静默**。
但两条红的成因是量具自己的问题，本轮据此改了门的形状：
(a) **P2 起初被自己的 print 炸掉**——中文行里的 U+21D2 在 GBK 控制台抛 UnicodeEncodeError，test_A/test_B 双双 ERROR，而违规其实是 0（半坏自检比没有更坏）。⇒ 每条门**先**印纯 ASCII 证人 `[P*_VERDICT] k=v … exit_criterion=…`，再印中文说明行；顺序承重。现在坏解释器的日志里也留有 `[P2_VERDICT] violations=0`，人能分清"量具崩了但判定值是 X"与"根本没到判定这步"。
(b) **P3 那条红的成因不对**——残留是被测模块 import 失败、setUpClass 半途而废留下的 env 改动，不是本门要守的"改了不还原"。⇒ 判据写成 `residue_items==0 AND run_errors==0`，run_errors 非空即 [P3_BLIND] 整轮作废；读不到 RESIDUE_JSON 同样退 1。**共同点：读不到读数 = 红，不是绿。**
复算两面：`Ran 7 tests OK`（P2+P3，五道 VERDICT 行齐）、P1 见 B_clean_tree_green_P1.log（`optimize_ab=11454 optimize_ba=11454`）。

硬边界照旧：未 push、未打 tag、paper/ 未碰。

### 2026-10-08（第二十八笔）：#69-C6 收尾批 —— 6-A 白名单结构门落地（is_free=True 赋值点集合，两面注入有牙）

基线 bf37281。只这一件、开完即停。新增 console/test_c6_is_free_whitelist_gate.py（4 tests OK），**生产代码零改动**（git status frontend/ 为空）。

① 期望值是**白名单集合相等**而非"抓到违规样本" ⇒ 现场无违规时仍会红（多一处赋值点即红），这正是 §6-A 守得住的原因。四项键：drone.py:__init__ / drone.py:update / drone.py:update#2 / environment.py:set_drone_out_of_service。定位钉 `符号名+同函数内第几处`、不钉行号（本会话两次被生产挪行咬到，行号只作读数打印）。
② 每项带一句"为什么合法"的理由，无理由或理由<12字即算违规——沿用 C4 豁免表形状，未另建机制。
③ 动态 free_with_assignment 不变量在注释与文档里定位为**第二证人，不得升为主门**（论证只在报告 §6-A-2 存一份）。
④ §6-B"守不住+为何守不住"的措辞唯一版本留在 docs/#69_结项报告.md §6-B；门文件 docstring 改为纯指针引用，不两处各写一版。

两面注入实测有牙（都在**临时副本**上跑，故生产文件不动）：ADD 面冒出白名单外新键 `_c6_probe`、DEL 面失去既有键 `set_drone_out_of_service`。另有量具自检面：census 命中 <4 ⇒ [C6_BLIND]，防"正则失明被当成现场干净"。

本轮两次自纠如实报：(a) 首版把 ADD 面断言方向写反（要求 fresh⊆WHITELIST，等于要求注入不被发现）⇒ 已改为"必须冒出未登记键"；(b) 白名单键标签与 census 实际输出不符（update#2/#3 vs update/update#2）⇒ 对齐后 4/4 绿。另有一次用 heredoc 补写测试时 `
` 被转义吃掉造出语法错，退回 Write 整文件重写解决。

报告续写 §6-D(+7/-0 纯追加)记落地状态：§5.3"C2 无门可守"前提侧由 [P]/[D] 升为 [G]；§6-B 语义归属仍守不住、不排期。
README 计数 console 45→46 文件 / 339→343 用例；citation --verify exit=0。硬边界：未 push、未打 tag、paper/ 未碰、无绝对坐标回退；drone.py 三段与环境变量注入通道零修改。之后本仓进观察模式。

### 2026-10-08（第二十七笔）：#69-C6 结项续写 —— 报告补 H/C2–C5 + C2/C3 门禁缺口分析（一半可上门、一半守不住）

基线 209080f。只做两件、不加新机制。docs/#69_结项报告.md **纯追加**（+60/-0，§0–§4 F 轮快照原文一字未动）。

① 续写：新增 §5（H/H2/H3+C2/C3/C4/C5 结论与分母，沿用 [G]/[P]/[D] 三档）与 §6（缺口分析）。
   两条冲突旧措辞按"保留原文+就地标作废"处理，不许第三版盖前两版：
   (i) §0 那句"cleanup_no_svc 在 greedy-s102、ga/pso/ortools-s101 各 =1"——其"现状"效力二次作废：一手逐变量复算 f2bcdf5=1(dr59)→9b1cd15=0(dr60)→483fc6c=0→c5ea8b0=0 ⇒ 关闭火口的是 H1′(9b1cd15) 前缀比对而非 C1，差异由代码态造成不由 fleet/episode 造成；版本沿革 v1/v2/v3 并存留痕。
   (ii) §4 挂账那句"由 #69-H2 行进线段谓词处理"——该半句作废：H2 过 (a) 不过 (b) 被否决回退，最终走 D-iv；H-R1 九例现由 G-H3-D(0/9 firing)+T5 根除。
   新分母：seed40907 avg_delay=2.8026315789473686；seed102 cleanup_no_svc=0/38、task_44 妥投；T1–T6 7 OK；G-H3-A..E 5 OK；C4 夹具 5 OK(变异 F1,F3 咬)+扫描门 4 OK(hits=2/exempt=2/violations=0 判预防性)；聚合 Ran 339/failures=1/skipped=5。

② 门禁缺口回答（按我自己三条纪律先排除死路：无可读取状态写不出不会永绿的门 / 期望值 0 的夹具给不了牙 / unknown 三态无覆盖率上限即逃生口）：
   **6-A 守得住**——is_free=True 赋值点是有限集合(本轮枚举 4 处:drone.py:88/:281/:342、environment.py:545)，可建"白名单相等"静态结构门：期望值是白名单而非"抓到违规"，故现场无违规样本时仍能红；配注入面给牙。动态 free_with_assignment 不变量单独看给不了牙(恒 0 永绿)，只能当第二证人。
   **6-B 守不住(明写)**——"is_free 是否只承载 Q2 语义"是关于意图的命题，代码无可读取状态：`if drone.is_free:` 在两种语义下写法完全相同，不存在 C4 那种错误写法签名 ⇒ 只能人工约定+文档语义表；真要机器守必须先反向拆字段。
   **6-C 接盘登记**：白名单门交下一系列（触发＝任何触及空闲态的重构，含 C3 遗留审计）；语义误用不排期。

本笔零生产代码改动。citation --verify exit=0；README 计数不变。硬边界：未 push、未打 tag、paper/ 未碰、无绝对坐标回退；drone.py 三段零修改。停在结项终态汇报。


### 2026-10-08（第二十六笔）：#69-C5 收口与结项 —— 聚合带分母复跑 + 门禁总表三分证人类型 + 对外口径五行

基线 d66f236。不加新机制，只收尾。全文 docs/C5_收口与结项.md（F_收口门禁总表.md 的增补，F 表 270-test 历史快照不动）。

① 聚合单次 discover 实测：`Ran 339 tests in 868.317s / FAILED (failures=1, skipped=5)` ⇒ 通过 333/失败 1/skip 5（339=上轮 330+C4 新增 9）。
   唯一红 = `test_g2_all_four_algorithms_get_real_fleet_speed`，断言原文逐字同前轮（:251 `[pso][NO_DENOMINATOR]`），且**本轮同文件单跑 OK(92.061s/EXIT 0)** ⇒ standalone 绿+聚合红 = **同一因（import-order 配置污染），非新因、非 D-iv**。
   诚实标注：F 表 §③ 当年以"批次切法 A/B/C/D=270 全绿"记为未见复现并预告"改回单次 discover 需重验"——本轮正是单次 discover，**按预告复现**，说明那是批次切法的观察盲区而非问题消失。
   skip 5 条逐项点名（old 面审计快照 / c1 mutation 面 / observer 冻结基线 / phase1b1 正式配对实验 / g2teeth GATE_CALIBRATION_STALE），其中仅第 5 条由 H3 引入；第 4 条须对外表述为"未执行"不得计入通过。

② 门禁总表按证人类型三档分列：**[G]** 常驻可执行门 / **[P]** 一次性探针（已删不可复算）/ **[D]** 仅文档声明，**只有 [G] 进门禁计数**。
   净增 [G] = 5 文件 24 用例（h_b_baseline_provenance 3 / h3_real_pop_events 7 / h3_lifecycle_gates 5 / c4_is_carrying_discriminator 5 / c4_cargo_truth_scan_gate 4），各写守什么火口＋残余盲区。
   ⚠ 本轮最重要的一条如实交代：**C2「cleanup 结构不可达」与 C3「is_free 单语义」没有任何常驻门**（探针同轮删了，属 [P]/[D]）——若将来新增 is_free=True 赋值点使该路径重新可达，当前无门会红，只能靠 G-H3-B/C1 的 cleanup_no_svc 间接触发。已单列在 §2-B，不混进门禁数。

③ 对外结项口径五行（≤5 行，未验不写成已验）：关掉的两条（生命周期一致性改执行器事件作证+三类反推移除且有源码级门；KPI 内部自洽闭合+载货口径双门）；开着的三条（外部有效性 #65/#67 欠账且 phase1b1 配对实验是 skip 未执行；C2/C3 无门可守；g2_all_four 已知干扰与 g2teeth 待重标定）。⇒ 对外只能说"339 中 333 通过、1 已知干扰、5 具名 skip"，**不能说 suite 全绿**。

citation --verify exit=0；README 计数 console 45/339 一致；本笔仅新增 1 个 doc（未动生产代码）。硬边界：未 push、未打 tag、paper/ 未碰、无绝对坐标回退；drone.py 三段零修改。停在 C5 终态汇报等裁。



### 2026-10-08（第二十五笔）：#69-C4 加固两条 —— _is_carrying 判别式夹具 + current_load 载货真值扫描门

基线 b211302。主控批准 #69-C3 建议的最小加固两条，实施轮、范围就这两件。**未动 environment.py / drone.py**（git status 只有 README + 2 个新测试文件 ⇒ 证明加固不需要碰禁改边界）。

① console/test_c4_is_carrying_discriminator.py（5 tests OK）：F1 已 add_load 但下一航点是 source→False；F2 dest 在航线且 load 未扣→True；F3 只剩 waypoint→False（防"route 里有 dest 才判"这种错写法蒙对前两面）；加一条承重变量判别式（同航线形状仅改 current_load 不得翻转）。变异面把 _is_carrying 换成被禁止的 `current_load > 0` ⇒ 实测具名报出 **F1,F3 被抓、F1 先咬**。两面齐全，非只会绿的门。

② console/test_c4_cargo_truth_scan_gate.py（4 tests OK）：扫全仓"拿 current_load 与裸零阈值比较"当载货真值。
   **基线读数如实报：hits=2 / exempt=2 / violations=0 ⇒ 本轮零违规，此门是预防性的**（未为计数归零发明判据）。
   两处命中逐条带理由豁免：environment.py:1751（_is_carrying 内部把 load<=1e-9 当下界短路，随后仍按航线标签定夺，非载货真值）、test_c4_is_carrying_discriminator.py:82（变异面故意构造的退化 lambda，扫它等于自杀）。无理由即算违规。
   三面夹具：clean(真仓库绿) / dirty(临时违规样本→红并具名行号) / shape-specificity(检测器自身两面：getattr 包裹式与点号式必须命中，env:1065 容量算术与 env:1797 比值必须不命中)。另有 exempt-stale 面防豁免表过期。

量具自我纠错（两次都是"工具瞎"不是"现场没有"）：第一版行级正则造 7 条假违规（6 条是 docstring/文案散文）；第二版整串丢 STRING token 又让 env:1751 与 lambda 消失（属性名藏在字符串里）⇒ 改用 tokenize 保留"恰为 current_load 的字面量"参与判定，并把 `_NUMCMP` 拆成正向/反向两条以覆盖 `0 == current_load` 写法。shape-specificity 面就是为防这类失明常驻。

README 计数 console 43→45 文件 / 330→339 用例；citation --verify exit=0；porcelain 仅剩本笔三文件。
硬边界：未 push、未打 tag、paper/ 未碰、无绝对坐标回退；drone.py 三段(:328-331/:342-343/:362-366)与 environment.py 全程零修改。约条件重评三条登记在档未动。停在加固终态汇报。



### 2026-10-08（第二十四笔）：#69-C3 current_load / is_free 状态职责审计 —— 判「不需要拆」，零代码改动

基线 d493b6f。纯审计轮，environment/drone 无任何改动。全文 docs/C3_state_field_audit.md。

① 清单：current_load 写 8 读 12、is_free 写 14 读 20+，逐处标注语义（Q1 机上有货 / Q2 可接单 / Q3 服务已终结）。is_free 全部落在 Q2，需要问航线阶段的地方(env:1044/:1584/_is_carrying:1752)一律现读 scheduled_position，不从 is_free 猜 ⇒ 单语义无风险。current_load 一名两义：add_load 于**派单时刻**调用(env:1109/1121/1818)，故它表示"已指派重量"(Q2 容量算术 env:1065 用它是正确的)，但被当 Q1 用就会错。

② 判别式（落到行号 + 实测）：分叉发生在"飞往取货点"段。seed102/3600 逐步采样 busy_leg_samples=12414、load>0&航线判空载=6906、航线判载货&load==0=**0** ⇒ 分叉真实且量大但危险方向为 0。消费者核查（不为立项发明危害）：KPI empty_load_ratio 唯一消费点是 env:1168 `_is_carrying(drone)`，走航线形状不吃 current_load；observer payload_at_reach 独立复算 **0/60 非零**（record@:1212 早于扣减@:1215，同帧⇒无区分力），observer 已注释拒绝用它下结论、改用 load_at_consumption(10583/10611 非零)；能耗侧分叉段 109497.5m/7847.1Wh 占加载能耗 48.7%，属 E1 假设层口径且在禁改边界内。

③ 结论：**不需要拆**。is_free 实测 free_with_load/route/service_waypoint 三项 ~4100 步全 0；current_load 唯一误用方向已被 _is_carrying 挡掉，且该口径早被本仓 M4(docs/数据来源与可追溯性登记表.md:331)专查并证伪过一次("98.53% 空载其实带货"已撤回，判"代码不要动")。本轮 route-pop 独立复算与 M4 在关键方向一致(carrying_but_counted_EMPTY=0.0m)，反方向数值差异(我 51.53% vs M4 3.40%)如实并列、不取其一。拆字段要横跨调度/UI/能耗/observer 六处写入点，为已证伪的风险付此代价不成立。登记三条重新评估触发条件；建议的最小加固(_is_carrying 判别式断言 + "禁用 current_load>0 当载货真值"扫描门)不在本轮实施、等裁。

硬边界：未 push、未打 tag、paper/ 未碰、无绝对坐标回退；drone.py 三段(:328-331/:342-343/:362-366)零修改。5 个临时探针同轮删除。citation --verify exit=0、README 计数不变、porcelain=0。停在 C3 终态汇报等裁。



### 2026-10-08（第二十三笔）：#69-C2 latent cleanup —— 判定不可达，零代码改动，出论证 + 更正过期口径

基线 c5ea8b0。窄敕三件走裁定③（不可达 ⇒ 不改码）。一手结论：**当前提交态下"dest 未 pop 却走 cleanup"结构上开不了火**。

入口条件表（现读行号）：environment.py:1233 `not self._prev_free_status.get(i,True) and drone.is_free` ∧ :1234 `i in self.drone_assignments` ⇒ 记 :1238 兜底完成。is_free=True 全仓仅 4 处来源（drone.py:88 初值 / :281 换电完成且无挂起 / :342 航线跑空即 dest-pop 同帧 / environment.py:545 故障注入复位），四条都不能造出"is_free 且 assignment 仍在"——:342 变空闲的前提正是最后一个航点被 pop，而 dest-pop 已在 :1212 记账、:1221/:1230 移除 assignment。

运行时证人（非静态推断）：① 逐步不变量探针 seeds 101/102/40907 合计 ~6131 步，free_with_assignment_count=**0**；② 生产入口 run_one(with_observer=True) 默认 fleet 与 rerun65 锁定 fleet(5/3/2,10机)/3600 两格，cleanup_no_svc=**0**，且 completions==destination_reached==counter==legal_unique==60、unattributed_completions=0（正例对照证明读数 0 属"现场没有"而非"量具瞎了"）。

矛盾消解（两边不是各自成立，是不同代码态）：历史 greedy-102 cleanup_no_svc=1 出自 **f2bcdf5**，本轮逐变量对齐复算——f2bcdf5=1(dr=59) / 9b1cd15=0(dr=60) / 483fc6c=0 / c5ea8b0=0 ⇒ 差异由代码态造成、不由 fleet/episode 造成；**关闭这条火口的是 H1′(9b1cd15) 把弹出检测从长度差改为前缀比对**，C1 只修 dest-leg 装配缺失、不足以关掉它。⚠ 更正：我此前把"seed101/102 R7 非零"当现状引用属**过期口径**，已被 H1′ 闭合。

处置：cleanup 分支保留原样（为无 dest 航点的充电自动航线兜底），**不新增变异两面**——给开不了火的分支造红面只会得到"期望值为 0 的夹具给不了牙"的坏门；已有牙（C1 门 cleanup_completion_without_service + G-H3-B）继续监该火口。current_load/is_free 状态语义审计移交 **#69-C3**。全文 docs/C2_cleanup_unreachable.md。

硬边界遵守：未 push、未打 tag、paper/ 未碰、未用绝对坐标回退；drone.py 三段（:328-331 pop / :342-343 is_free+current_load / :362-366 单段直线位移）零修改。citation --verify exit=0；README 计数 43/330 一致。停在 C2 终态汇报。

### 2026-10-08（第二十二笔）：#69-H3 g2teeth 处置落地 —— 显式 skip + 校准前提已死具名状态

基线 3c54c37。主控裁定①落地：g2teeth 的牙在 pre-D-iv completion 计时上标定、D-iv 树 flush_size=0 ⇒ "size 触发口曾打开"为假；两条重定路（flush_size>0 永红 / optimize_calls>0 无牙）都不签。
处置 = **不重定义/不降级/不删**，改 `test_speed_fallback_gate.py:329` 前置 guard：probe 实测 gate 面 flush_size==0 时打印 `[GATE_CALIBRATION_STALE]` 状态并 `skipTest`。skip ≠ 通过 ≠ 失败，聚合报告行印出具名状态，不许默默红或绿。单跑实测 `OK (skipped=1)` + 状态行。
裁定②：论文口径约束新增 #65_rerun_delta.md §7——"PSO size-flush 在修正计时下从未触发＝调度器行为事实非缺陷；描述 PSO 缓冲须用 D-iv 后数据重述"；不为让触发口再开而调低 `buffer_size_threshold`（改 scheduler 语义，硬边界外）。裁定③：citation remap 收口不变。g2teeth 现挂 pending-revalidation，等独立 re-calibration 决策。
⑥ 论文口径句入档 docs/D_KPI定义层盘点.md 附录："取货/送达时间定义为执行层消费服务航点的离散 sim_time；<1m 是 planner endpoint 选择规则，不构成服务完成事件。"
⑦ 硬边界遵守：drone.py:335-336 未改（仅在 :328 pop 处新增 append）、cleanup/is_free 兜底语义未动；current_load/is_free 状态审计留待后续 #69-C3。

改动面：frontend/drone.py(+8/-1) · frontend/environment.py(+11/-47) · console/{test_h3_real_pop_events.py,test_h3_lifecycle_gates.py} 新建 · test_h_r7_delivery_detection.py 退役纯函数面留端到端 · README 计数(console 43/330) · docs{#69-H_terminal,D_KPI定义层盘点,数据来源与可追溯性登记表,#69-H2_stop_report}。停在 H3 终态汇报。



基线 f1e3a5b。按主控裁定"修在 env 检测层、H1 批文作废"落地。改动面 = frontend/environment.py + console/test_h_r7_delivery_detection.py + 登记表 path:line 重指 + README；drone.py/route_planner/metrics_schema/runner 未动。

根因（二次取证已证，见 #69-H_R7_forensics.md）：environment.py:1190 用 `len(prev)>len(curr)` 判航点弹出，在同一 step「弹掉 dest 服务点 + 追加换电/仓库点」时净长度不变 ⇒ 漏检送达 ⇒ assignment 残留被 is_free_cleanup 兜底计成完成（task_44 seed102）。实测此类转移 10 次。
修法 `_consumed_prefix_len`：(a) curr 是 prev 去前 k 个的后缀⇒正常弹出 k 个；(b) 非后缀但队首是已从 curr 消失的服务航点⇒计消费；(c) 整体 re-route⇒k=0 不入账。消费块遍历 prev[:k]。

验收四条：(a) seed102 reached 59→60、cleanup_no_svc 1→0、task_44 origin=destination_branch t=1458 ✅；(b) seed40907 配对回放 completed/DR/cleanup=38/38/0、timeout/delay、first_divergence index=852 seq=853 task_11 全不变 ✅；(c) completion 全 1.0 不变、timeout/delay 7/8 格不变，**唯 greedy-s102 timeout 0.0667→0.05/delay 4.85→3.225**——这是把"从未妥投却兜底计时"的 task_44 正确改判为按时送达的直接后果，非外溢；(d) 两面夹具 pre-fix RED([R7_STILL_PRESENT])/post-fix GREEN(6 OK) ✅。聚合 A90+B44+C117+D25=276 0 failures。
⚠ (c) 与 (a) 在受影响格上互斥，交回主控定夺是否认可该格 timeout 变化属预期修正（详见 docs/#69-H_terminal.md），执行会话未自行改论文数字口径。未 publish、未 push。停在 H 终态汇报。

### 2026-10-08（第二十一笔）：#69-H3 D-iv —— 消费证人改为"执行器真 pop 离散事件"，废除一切反推

基线 483fc6c。主控/ChatGPT 裁定不选 D-i/D-ii/D-iii，走第四方向 **D-iv**；上位原则冻结：
"到达不是几何观察值，而是执行器完成某服务航点的离散事件；几何只决定航点能否被执行器接受，业务只消费执行事件。"

① 回退 #69-H2 未提交的线段谓词（environment.py 那 71 行工作树改动丢弃，原 diff 存档 docs/取证输出/h2_segment_predicate_discarded.diff）。9b1cd15 后缀启发式降为历史中间对照、不作最终 lifecycle-correct baseline（见 #69-H_terminal.md「裁定更新 D-iv」）。
② 实现真实事件机制：`Drone.update()` 在 `scheduled_position.pop(0)`（drone.py:328）处 append 进单步有序缓冲 `consumed_waypoints_this_step`；Environment 每步读出即清空、只消费这些事实。**删除** `_consumed_prefix_len` 反推函数与 step() 里的 `prev_scheduled` 快照——长度差/前后缀/线段穿越一律不再用于判弹出。
③ 六硬夹具 console/test_h3_real_pop_events.py（T1 direct pop / T2 detour pop / T3 同帧弹+追加净长不变仍计 / T4 途经无弹出必不计 / T5 mid-flight re-route 无弹出必不计·杀 9 例 / T6 多 pop 保序 + 幽灵事件不变量），含变异面 M1/M2 证牙。
④ 五把门 console/test_h3_lifecycle_gates.py G-H3-A..E（A seed40907 avg_delay 恢复 2.802632 / B seed102 cleanup=0+task_44 送达 / C 执行器 pop 处确发事件 / D 那 9 例不再提前 completion / E 反推符号彻底移除），全 live 复算不读归档。摘掉 append 行→C+B 双双实测报红（有牙）。
⑤ 回放判据实测：seed40907 avg_delay=2.8026315789473686（=冻结证人，task_3 真 pop 在 t=172，非回归）；seed102 cleanup_no_svc=0、task_44∈DESTINATION_REACHED；旧 9 例假阳性时刻无一再计送达。**未 re-freeze 到 2.776316**。C1 门/Observer 零漂移/GateA 全绿；citation 门随 environment.py 行号上移重指 12+1 条后归 0 breaks。
⚠ **一处 D-iv 行为外溢停在待裁（本笔不含其修复）**：`test_speed_fallback_gate.test_g2teeth` 红——一手对照见 #65_rerun_delta.md §7：D-iv 树 gate 工况 flush_size=**0**/buffer_peak=**10**（HEAD 是 1/15）。旧后缀规则的 9 例提前 completion 虚增了 PSO pending_buffer、把 size 触发口顶到阈值；D-iv 修好计时后峰值真实回落 ⇒ 该门的牙是在替 R7 缺陷负载标定。按主控裁定①"重定后仍红则停下交具名证据"停此：**不删牙、不降阈、不改判据**（flush_size>0＝永红夹具、optimize_calls>0＝无牙 mutate=6≠0），等下一轮方向。论文侧旧 buffer_peak=15/flush_size=1 作废、不得当 PSO 特性证据（裁定②已入 #65_rerun_delta.md §7）。并发假象 ×2（g2_all_four / rewrite_map.batch_read）standalone 均绿，登记为已知干扰不修（裁定③）。citation 三门随 remap+rewrite-report 收口 ✅。自纠入档：上一轮误读 unittest 缓冲进度点为"无 FAIL"，本轮以一手 failures=4 纠正。

### 2026-10-08（第十九笔）：#65 四算法重跑轮 —— delta 表 + 旧数字作废清单 + opt-in observer

基线 f2bcdf5。锁 seeds 101–105 / [greedy,ga,pso,ortools] / fleet light5-std3-heavy2 / episode 3600，走生产入口 experiments.worker.run_one。改动面 = experiments/worker.py（新增**默认关**的 --with-observer，产 lifecycle 两读数；runner 不传⇒现有链路与 latest 逐字不变，smoke 证 metrics 零漂移）+ docs/#65_rerun_delta.md + docs/取证输出/rerun65_cells.json。临时驱动同轮删。

结果：completion 四算法恒 1.0。delta(old=one_click_latest→new)：greedy timeout Δ0、delay +0.085(latest/raw 口径差非本轮)、energy −620；ga/pso/ortools timeout −0.010~−0.013、delay −0.6~−0.9。**确定性已验**：greedy 五 seed new==old-raw 逐位相同 ⇒ delta 非噪声；差异只在批量优化器真正介入的 s101/102/104。**排名翻转**：按超时率/时延第 3–4 名 pso↔ortools 互换（greedy 最优、ga 次之不变），但 n=5 符号检验不可判 ⇒ 论文不得据此断言 ortools>pso。

作废清单三分类：A 直接作废=无；B 旧证据失效待重跑=latest 全部指标（生成于 C1 前代码），尤其 ga/pso/ortools 超时率/时延随 C1 变；C 不受影响但统一刷新=完成率恒1.0/里程量/figures 重绘。撤回我先前"旧 latest 不可复算"一句——greedy 超时率 latest 0.053333==其 raw 均值，可复算，仅 delay 有批次口径差。

⚠ **意外发现 R7（具名交回，未修）**：cleanup_completion_without_service 在生产 seed 上=1（greedy-s102、ga/pso/ortools-s101），一手复现 task_44 t=1415装载/t=1666经 is_free_cleanup 计完成/无 DESTINATION_REACHED ⇒ 计入 completed 却从未妥投。pre-C1(f654587 worktree)同 seed=14/27，post-C1=1 ⇒ C1 消掉绝大多数但残留一条另一路径。**更正 #69-C2a/F 说法**："cleanup 不可达/R5=0"只对 seed 40907 成立、系过度外推；结项报告"latent defect 仅注入面"应改为"有真实正例(seed101/102)+注入面"。是否开 #69-H/R7 修复轮交主控定。停在重跑汇报，未 publish、未 push。

### 2026-10-07（第十八笔）：#69-G 结项 —— 待裁①落地（old 面降为审计快照）+ 结项报告

基线 8a76462。改动面 = console/test_c1_lifecycle_gate.py（test_1 增 elif FACE=="old"→skip）+ docs/#69_结项报告.md；production 零 diff。

待裁①裁定 (b) 落地：old 面从"永久红的测试"改为显式 `skipTest("[OLD_IS_BASELINE_AUDIT_SNAPSHOT] pre-C1 基线审计见 docs/取证输出/c1_face_old.json")`，不删。理由＝聚合 runner 长期绿是验收基础设施前提，而 old 的历史证人已在冻结 c1_face_old.json(R1=12/R4=1/R5=12)+#69-A/C0 文档持有，不需红灯持有它。牙仍由 mutate/forced_cleanup 注入面 + GD-a/GD-b 承担。
实测：C1 default face（无 env）Ran 8 OK(skipped=2) ⇒ 跑默认 face 的聚合不再因此红；四面 fixed/mutate/forced_cleanup OK、old skip。
聚合复跑（本轮现测）：A90+B38+C117+D25=**270 tests 0 failures** + C1 门 8(skip=2)=合计 278 全绿。
待裁②(C2b :336 语义重叠)关闭不修、待裁③(D-1 措辞)记于 D 文档 §3 留用户直接指令。
结项判定：系统内部自洽层闭合——硬不变量有门、latent defect 有牙、replay 闭合、KPI 疑点门化。会话进入观察期，不自动开新阶段；V6 (#67) 仍暂停；未 push。停在结项汇报。

### 2026-10-07（第十七笔）：#69-F 收口确认轮 —— 全量门禁总表 + replay 终态对账（零代码改动）

HEAD 7d36b99。纯确认轮：不改任何码，只把 C1–E 的门禁在本轮重跑一遍并逐字段核对 replay。产物 docs/F_收口门禁总表.md。

① 全量门禁一次性总表（**全部 F 轮现测、非引旧档**）：C1 四面（fixed/mutate/forced_cleanup OK；old 刻意 [C1_NO_TEETH]）、
Gate A 35 例逐点等价、source A/B/C/D、destination A/B/C/D、Observer 零漂移 8、compare_gate 27 / height_binary 4 /
loader_baseline 9 / README counts 5、聚合 suite batch A90+B38+C117+D25=**270 tests 0 failures**。
② paired replay f654587→HEAD 逐字段对账：AFTER 侧从本轮重生成 c1_face_live_fixed.json(mtime 20:25) 现算
completed/DR/cleanup=38/38/0 与 C1 提交产物一致；first_divergence index=852 seq=853 task_11 DESTINATION_REACHED 仍在 ⇒ E 后读数逐字不变。
③ #69 剩余开项（只列不修）：待裁①teeth 极性(old 面红，唯一让默认-face runner 不绿者)、待裁②drone.py:336 保留vs合并、
待裁③D-1 措辞入 metrics 文档；预存干扰本轮批次切法下 0 复现（诚实标注≠并发时序永不再现）。结项判断：三项均为判据/措辞/前瞻动作、
非未闭合缺陷 ⇒ 裁定落定即可结 #69，无需 G；其中①优先级最高（影响"suite 全绿"对外表述）。停在收口汇报。

### 2026-10-07（第十六笔）：#69-E KPI 疑点门化 G-D-a/G-D-b + D-2 互检（production 零修改）

基线 518b3d9。改动面 = console/test_c1_lifecycle_gate.py + docs/D_KPI定义层盘点.md + README 计数；
frontend/experiments/backend_si 对 518b3d9 **零 diff**（已 git 核）。

① G-D-a → test_5_GD_a_timeout_only_from_legal_delivery：谓词"任一 d_delay>0 或 d_ontime==0 的完成必须 origin==destination_branch"，
判据写成结构事实、期望不写常量 2（自然值 GD_a=0）。证人用 origin 不用 has_destination_evidence（后者几何精确相等会把 detour
容差抵达的合法送达误报）。证牙探针：合成一条 cleanup-origin+d_delay>0 完成喂进 classify ⇒ 必 >0。
② G-D-b → test_6_GD_b_dr_completion_bidirectional_align：counter==|completion|==Σd_completed 且缺 DR=0、孤儿 DR=0。
⚠ 自然对齐检查作用在**未注入生产轨迹**（从 c1_face_live_fixed.json 读，counter 由 Σd_completed 现算），不是本面注入后 trace——
mutate/forced_cleanup 故意注入错位是 R3/R4 的职责，拿注入 trace 断言"必须对齐"会与 mutation 面自相矛盾（本轮实测踩过：先按 self.trace
跑 mutate 假红 counter38≠comp40、再按注入 counter 比自然事件 forced_cleanup 假红 39≠38，两次都因取错总体）。证牙探针：删一条 DR ⇒ missing_dr≥1 且对齐破。
③ D-2 互检（按"结论是啥写啥、不建重门"）：avg_energy_per_task(env:966) 分母=total_completed_tasks，与 rate 指标同分母；
grep metrics_schema/reporting 均 0 命中 ⇒ 未导出、无方向 ⇒ 当前无害，符合原结论。只在 D 文档加一行"若将来导出必须同时登记方向"的互检，不单独建门。

四面终态：fixed/mutate/forced_cleanup 全 OK（含两条新 GD 测试执行通过）、old 仍 [C1_NO_TEETH]（承 C2a 待裁项①，非本轮引入）。
聚合 suite 复跑 A90+B38+C117+D25=270 全绿、零失败；README 计数 _readme_counts.py --fix → console=39文件/314用例。
paired replay 读数不变（E 纯审计层，GD 只读事件不改生产；replay 于 C1 已做，本轮不重生成、任何读数变化即视为外溢——实测无变化）。停在 E 汇报，不开 F。

### 2026-10-07（第十五笔）：#69-D KPI 定义层盘点与自洽审计 —— D 轮零生产改动

基线 22ab9b1。只盘点不改码（frontend/、experiments/ 对 HEAD 零 diff）。产物 docs/D_KPI定义层盘点.md。

① 清单：completed/completion_rate/on_time_rate/timeout_rate/avg_delay/energy/swap/action-distance + DR↔completion，
逐个给定义行、分子分母、吃哪些字段、C1 后是否自洽（真源链 _record_task_completion:422-490 → get_statistics:903-1007
→ step info:1255-1287 → metrics_schema._STAT_KEY_MAP:104-129 → reporting 方向标注）。
② 两条指定疑点实测（提交态 c1_face_live_fixed.json）：(a) timeout/delay 全部来自 legal completion
（d_ontime==0 计 2、d_delay>0 计 2，非 delivery-leg 贡献=0；total_completed=Σd_completed=38=len(comp)）——修复前 C0 报的
"timeout 2 例中 1 例非法"现不成立，断言应门化；(b) |DR Δ completion|=0 双向（无缺 DR 的完成、无孤儿 DR），§6-L 族无第二个未对齐定义。
③ 具名不自洽两项（交回裁定，未改）：D-1 on_time/timeout 语义="相对 deadline 迟到"(env:441)而非"经 dest service leg 送达"，
两正交维度当前 seed 恰好同批⇒数值一致但叙述不得混同（口径澄清非改码）；D-2 avg_energy_per_task(:966)与 rate 指标共享旧污染分母、
未导出未登记方向⇒前瞻无害。排除项：unfinished 非独立导出列（replay 里按 generated−completed 现算）、timeout_rate=1−on_time_rate 仅冗余表达值正确。

自查结论=**D 轮零生产改动**（指令②：盘点即有效交付）。建议两条审计层门 G-D-a/G-D-b（待放行才写夹具，本轮不动）。硬边界全程遵守。停在盘点汇报，不开 #69-E。

### 2026-10-07（第十四笔）：#69-C2b drone.py:335-336 载重归零语义审计 + mutate 夹具目标重挂

基线 674a3c2。**只审计不改生产码**：drone.py / environment.py 本轮零 diff；改动仅 console/test_c1_lifecycle_gate.py 的 `_inject` + 新增 docs/C2b_drone载重归零审计.md。

① 契约对账结论：**语义重叠（冗余双写/防御性 backstop），建议合并待裁**。一手证据（提交态 c1_face_live_fixed.json + 真实 planner 出口）：
- 路由交错实测：两任务 kinds=['source','dest','source','dest']（plan_route_for_tasks :1848-1879 每任务追加一整腿），故每腿送达+扣减(:1218/:1227)都发生在下一腿取货前 ⇒ 无"分组装载中途空车"。
- per-drone 栈式对账：TASK_LOADED 压入、COMPLETION 弹出，在每次 DRONE_BECAME_FREE（触发 :336）时残留未完成载货数 = **0**（38 次转空闲现场，SANITY loaded=40/completion=38/free=38）。⇒ :336 触发时 current_load 恒已为 0，是环境侧逐腿扣减之外的第二处载重写＝冗余双写，非幽灵清零。
- 三态取"语义重叠"：不删的理由写成前瞻风险（将来若出现"清空但仍有未送达 assignment"的新场景，:336 会从无害兜底变成掩盖上游记账缺失的静默清零——同"两套到达定义"族），当前不可达、不作缺陷量化。建议两处加互相指向的注释锚或按裁定合并；本轮不动。

③ mutate 注入器 `_inject` 目标从旧几何判据 `not has_destination_evidence`（叙事="伪造无送达→有送达"，属 #69-A/C0 cleanup 冒充 delivery 场景，C1 后生产不再发生）改挂到 `record_origin=="destination_branch"` 的一条合法 dest 完成，诚实命名其证明的窄事实："任意完成被重复计入 ⇒ R3 抓到"。四面复跑：fixed ✅ / mutate(R3=1) ✅RED / forced_cleanup(新门=1,R1=1,R4=1) ✅RED / old(live)[C1_NO_TEETH] ✅RED。

停在审计汇报，不开 #69-D。

### 2026-10-07（第十三笔）：#69-C2a R5 降级为信息读数 + 新建有牙的 cleanup→completion 语义门

基线 aa75b5b。**纯审计层改动**：只动 console/test_c1_lifecycle_gate.py，生产代码（environment/consistency_observer/route_planner/drone）对 aa75b5b **零 diff**（已 git diff 核）。

起因（主控裁定）：#69-C1 后 fixed 面 R5（旧判据 `not has_destination_evidence`）仍=12。本轮消融证明它对 cleanup accounting **零敏感**——把 cleanup 分支整条禁用（`if False:`）后该读数仍=12、逐字不变 ⇒ 它实际度量的是 A* <1m 容差抵达率（dest-branch 合法送达中坐标非精确抵达的条数），不是"cleanup 冒充 delivery"。以"cleanup 牙"的名义保留它是错的。

改动：
- R5 → 信息量读数 `r5_nonexact_arrival_count`（当前=12；不进退码、不作通过/失败判据，只要求是非负整数）。
- 新增有牙语义门 `cleanup_completion_without_service`：谓词 = completion 的 record_origin==is_free_cleanup_branch 且该任务无 DESTINATION_REACHED 证人。生产 seed 上 cleanup 不可达 ⇒ fixed=0；其牙由 forced_cleanup 注入面证明（注入 origin=cleanup+无 DR ⇒ =1）。
- test_1 判据随之改写：fixed 断言新门=0（>0 即缺陷复发或越界修了 cleanup）；old/mutate/forced_cleanup 三面改为"必须有违规读数才过"（teeth = 新门>0 或 R3>0 或 R4>0）。

先红后绿演示（三段原始输出留档 docs/取证输出/c2a_face_*.txt）：
① old live 面 rc=1 `[C1_NO_TEETH]`（当前代码不再自带 cleanup 违规，刻意红）；
② 把新门谓词改成恒真 → fixed rc=1 `[C1_CLEANUP_GATE_RED_ON_FIXED] got=38`（证门承重）；
③ 还原 → fixed rc=0 OK（新门=0、r5_nonexact_arrival_count=12）。

四面终态：fixed(R1/R2/R3/R4=0, 新门=0, r5=12) ✅ / mutate(R3=1) ✅RED / forced_cleanup(新门=1,R1=1,R4=1) ✅RED / old(live)[C1_NO_TEETH] ✅RED（历史违规数见冻结 c1_face_old.json: R1=12/R4=1/R5=12）。
验收③ paired replay 不变：事件派生 AFTER 指标 completed/DESTINATION_REACHED/cleanup=38/38/0 与已提交 c1_paired_replay_f654587_fixed.json 逐字相同，first_divergence index=852 seq=853 task_11 不变。

未做（留待主控/C2b）：mutate 注入器 `_inject` 的目标选择仍挂在旧几何判据 `not has_destination_evidence` 上——它在 C2a 下仍能造出 R3 违规（因被改写的本已合法 dest 完成造成 dup-with-DR），但选靶语义已过时；是否随 #69-C2b/C3 一并清理待定，本轮不扩大范围。docs/当前状态真源图.md 里那处 "R5_cleanup_counted_as_delivery":12 是 580c937 基线的历史记录，键名对当时快照正确，不改写历史。

### 2026-10-07（第十二笔）：#69-C1 destination service 契约修复（选 P1，仅改 dest leg）

基线 f654587。裁定：P1 落地；P2 淘汰；P3 拆为 #69-C2/#69-C3 后续做。本轮**只**修 destination service 契约，
不动 route_planner.py / drone.py:335-336 / cleanup accounting / TaskState / scheduler / KPI 定义（全部零 diff，已核）。

改动（frontend/environment.py）：dest leg 装配对称套用 #69-B 的 service-waypoint 规则——前 N-1 个 waypoint = transit、
末个 = dest service waypoint；消费块删除第二套判据 `get_destination() == dest_pos`（含其唯一消费者 dest_pos 变量），
送达改由"dest 服务航点被弹出"这一条标签触发。列表分支取最早未送达 assignment（remove-on-deliver ⇒ 存在即未送达，
无需新字段），dict 分支同步去掉相等守卫。

观察层（frontend/consistency_observer.py）随之对齐同一契约：DESTINATION_REACHED 证人从几何 pos==dest(<1e-6)
改为 origin==destination_branch（否则 detour 容差抵达会把合法送达误报成无证据，正是本任务要消除的层间不一致）；
分支文本锚从旧守卫行改挂到消费块注释特征行「服务航点被弹出即视为送达」；has_destination_evidence **保留几何原义**
作 R5 的唯一证人（cleanup 分支 + 无人机不在目的地），不用 origin 顶替。

门与夹具（console/test_c1_lifecycle_gate.py + 新增 test_c1_destination_leg_semantics.py）：
fixed 面改为直接跑当前生产代码（不再读 #69-B 时代的冻结 JSON，那反映的是修复前行为）；old/mutate/forced_cleanup
三面判据范围收窄到本轮实际修复面——牙从 R1 迁到 R5（cleanup 仍未修）+ mutate 注入 R3 + forced_cleanup 注入 R4/R1。
四组 dest 夹具 direct/detour/fallback-single/mutation 全绿；D 静态哨兵经变异验证有牙（加回相等判据当场红）。
两处 subprocess GBK 解码 bug（parent text=True 用 locale codec 解 UTF-8 子进程输出 → proc.stdout=None）一并修
（encoding="utf-8" + PYTHONIOENCODING）。README 测试计数由 _readme_counts.py --fix 更新为 console=39文件/312用例。

验收读数（seed 40907 / greedy / 1200 步，配对回放 docs/取证输出/c1_paired_replay_f654587_fixed.json）：
第一处分歧 index=852 seq=853 t=95 task_11 —— before 走 is_free_cleanup_branch(has_destination_evidence=false)，
after 走 DESTINATION_REACHED(dest service leg)，同任务同时刻、只有分类变化。九项 delta：
DESTINATION_REACHED 26→38(+12)、cleanup completion 12→0(−12)、completed 38→38(0)、timeout_rate/mean_delay/
energy/swap/action-distance 全部 Δ=0、unfinished 6→6。**聚合 KPI 零变化但 12 条 cleanup 完成转为合法 destination
完成** —— 这是有效结果，命中 ChatGPT 待验证假设。套件：Gate A 35 例逐点等价 GREEN、source A/B/C/D GREEN、
Observer 零漂移 8/8（test_h 按基线门控 skip）、C1 fixed GREEN / mutate RED(R3) / forced_cleanup RED(R4,R1)、
全量 console 三批除 README 计数（已修）外全绿。完成后停止，不进 #69-C2、不改 drone.py。

### 2026-10-07（第十一笔）：#69-C0 根因取证 —— 找到共同上游根因，按指令停止未打补丁

基线 39165c2。产物 docs/取证输出/c0_cleanup_forensics.json（12 条 cleanup × 20 字段 + 38 次转空闲现场）。

**关键反转**：#69-A 记的"12 条中 3 条从未取货"在 R2 修复后变成 **0 条**（has_load_evidence 全为 True）。
⇒ 那 3 条本是 R2 pickup 契约的下游表现、已被 #69-B 顺带消除；我上轮据 load_time_raw is None 分的
"更像分配后未执行"一类，实为记账缺失造成的误分。

12 条共同上游特征（每字段取值集合均为单点）：is_free=True、current_load=0.0、remaining_waypoints=0、
suspended_route=0、awaiting_berth=False、out_of_service=False、in_pending_pool=False、
has_load_evidence=True、task_status='assigned'、n_remaining_assignments={1} 且含自身；
battery/capacity ∈ [0.241,0.924] 无一低于阈值 0.2 ⇒ 排除换电路径。
决定性分布：**38 次转空闲事件的 waypoints_before 全为 1**。

根因＝分类 B（route 提前清空），不是 cleanup 分支写错：dest leg 装配仍是旧双判据写法
(environment.py:1867-1874，#69-B 只改了 source leg) ⇒ A* <1m 容差使末点非精确 dest ⇒ 该点弹出后
scheduled_position 空 ⇒ drone.py:335 依其契约置 is_free=True 并 :336 清零载重；而环境侧消费 dest
要求 popped[2]=='dest' 且坐标等于 destination(:1204/:1223)，两条件同时不成立 ⇒ 无 DESTINATION_REACHED
却由下一轮 _prev_free_status 差分命中 cleanup 分支被计成完成。
A 残留 assignment 否（assignment 与 waypoints 同步存在）；C free 错误派生于 B；D 资源/电量路径全部排除。

为何必须停（BI 两条规则同时命中）：①「发现共同上游根因先停并汇报」；②「paired replay 第一处分歧
不得提前出现在 route/source/scheduler」——若现在修 dest leg 装配，分歧必落在 route 装配，直接违反②；
若只在 cleanup 内改 requeue/incomplete，则是掩盖上游且那 12 架机货已被 :336 清掉，requeue 会造成幽灵配送。

⇒ #69-C1 原两方案都不干净，登记三选项待裁：P1 把 #69-B 的 service-waypoint 契约对称推广到 dest leg
（需解除"本轮不改 destination semantics"，我倾向此项）／P2 仅修 cleanup 语义（掩盖上游+幽灵配送风险）／
P3 先修 :336 转空闲即清零载重（触及 cargo 语义，风险更大）。未动任何生产代码，三条门禁 RC=0，VERSION 未动。
### 2026-10-07（第十笔）：撤回我"两条预存红＝测试间干扰"的归因 —— 其中一条是我自己造成的

上轮我在 #69-B 验收里写「test_g2_* 与 citation 覆盖率门在基线 580c937 上同样表现，属测试间干扰非本轮引入」。
**这个归因是错的**，本轮一手复算：

`console/_citations.py --verify` 独立跑就报 `[FAIL][REWRITE_MAP_STALE] docs/提交改写映射表.md differs from what git says now`。
根因不是干扰，是**我自己造的垃圾对象**：那张表由代码现算、明写"禁止手填"，它数的是仓库里的不可达对象；
而我在 #69-B 那几轮为了隔离验证反复 `git stash / git stash pop`，每次都在对象库里留下 WIP/index 对象
（stash ref 清了、对象未回收）。重生成后差异恰好是 **+6 条悬空对象、不可达 29→35**，
且新增 6 行全部标注 `git stash 留下的对象`，标题逐条指回 `580c937` ⇒ 因果清楚，不是我误读。

处置：按该工具自己给的 fix 方向跑 `--rewrite-report --write` 重新生成（不手改一个值），
`--verify` 回到 RC=0，citation 门 `Ran 1 OK`。**没有动 .git 里任何东西**（不 gc、不 reflog expire）——
那些对象是回收它们才会真正破坏这张表的证据链。

顺带记一条：**我把 stash 当成了无害的隔离手段，它其实会改动物库状态并被一个只读门检测到**。
以后要在两个 ref 之间对比行为，优先用 `git worktree add --detach`（本轮 paired replay 就是这么做的，
用完 `worktree remove`，不留悬空 commit），而不是 stash。

另一条红 `test_g2_all_four_algorithms_get_real_fleet_speed` 本轮 standalone 复跑 `Ran 1 OK (117.8s)`
⇒ 它确实只在聚合运行下红，属真实的测试间干扰（上一轮这条判断成立，只有把它和 citation 门并案归因是错的）。
所以「全量 suite GREEN」仍差这一条，需要单独一轮做 fixture 隔离，不在本轮顺手改。
### 2026-10-07（第九笔）：把 #69-B 的实质写成一条可复用的设计教训 —— 修层间契约，不塞坐标点

补 `docs/当前状态真源图.md` §6-L。裁定原话值得留档：「RoutePlanner 已经有一套『到达』的定义，
而业务层又偷偷定义了另一套更严格的『到达』」——这类跨层语义不一致普通单元测试抓不到，因为每层各自都通过。

三处判据并置后形状很清楚：planner `euclidean(current,goal)<1`(:160) 说到了；装配把 leg 末点标 'source'；
消费侧还要 `get_source() == source_pos`(:1199-1203) 逐位相等 ⇒ 下层说到了、上层说没到，
合起来产出"既送达又从未取货"的状态，即 C1 R2 那 7 例。

修法只有一句：**让"到达"只有一个定义**（装配统一 direct/detour/fallback 的前 N-1 transit + 末点 service，
消费只认标签弹出）。刻意不做的是往 planner 输出追加精确 goal 点 —— 上一版我这么干过并被驳回，
那等于用第三套补丁弥合两套定义，且实测连带把 Gate A 的路径等价打断（旧/新航点表多出一个点）。
一般化写进文档：两个抽象层对同一谓词各有定义时，先判定哪个是权威、再让另一方成为它的投影，不要新增第三个概念去对齐。

同形状的还有两处，一并登记（解释了三件看似无关的事）：payload_at_reach 读到载重 0 但途中明明带货
（物理量 vs 业务量两套表达）、Task.status 停在 assigned 而完成由计数器决定（状态字段 vs 集合真源）。
⇒ 共同形状：同一事实存在两套表示且没有一处断言要求它们一致。后续建门优先给这类跨层谓词配互检断言。

提交态 d6b6c0b 验收复跑全绿：Gate A Ran 5 OK / A-D source 夹具 Ran 4 OK / Observer 零漂移 Ran 8 OK(skipped=1) /
C1 old FAILED(1)（cleanup 未修＝期望红）/ mutate FAILED(1) / forced_cleanup FAILED(1) / fixed OK；
paired replay 第一处分歧 index=369 t=43 task_3 TASK_LOADED，KPI delta 全 0。三条门禁 RC=0。

⚠ 明确记一条未达成：BI 验收里的「全量 suite GREEN」我没做到 —— Ran 308 仍有 2 条预存红
(test_g2_*、citation 覆盖率打印门)，二者在基线 580c937 上同样表现（standalone 分别 OK / rc=0，仅聚合运行红）
⇒ 属测试间干扰非本轮引入，需单独一轮处理隔离或 fixture 顺序。不把它算作通过。
### 2026-10-07（第八笔）：#69-B source-leg 语义修复 —— planner 不动、只改装配；R2 归零而 cleanup 仍红

按裁定执行：**撤销上一轮越界实现**（planner 追加 exact-goal waypoint + arrival_exact 字段已 `git checkout HEAD` 恢复，
Gate A 重新 GREEN）。本轮生产改动只有 `frontend/environment.py` 一个文件（15+/13-），全在 source-leg 装配与取货消费两处。

统一 direct/detour/fallback 的装配规则：source leg **前 N-1 个 = transit，最后一个 = source service waypoint**。
取货由"服务航点被弹出"触发，**删除** `assignment['task'].get_source() == source_pos` 这条坐标严格相等判据
—— 它与业务标签构成两套判据并存，在 A* 容差抵达（`route_planner.py:160` `euclidean(current,goal)<1`）时永远失配。
不新增精确 goal 点、不改 planner 航点序列、不改 destination 语义 / cleanup accounting / Task.status / KPI / 调度器。

前置核实（BI 要求先查容差）：A* 以 <1 m 容差终止 ⇒ detour 末点不保证等于 goal；direct/fallback 末点精确等于 goal。
⇒ 这推翻了我 #69-A 写的"单点退化走 else 分支"是主因；真实缺陷面是 **detour 航线**。

验收清单（逐项实测）：
- Gate A **GREEN**（Ran 5 OK）—— planner 未被改动
- A/B/C/D source 夹具 **GREEN**（Ran 4 OK），且全部走真实 `plan_route_for_tasks` 出口；
  C 组打印「服务航点精确等于 source: **False**」⇒ 确实覆盖到容差抵达这条路径，不是测我的复刻逻辑
- forced_cleanup mutation 面 **RED**（R1 12→13、never_loaded 0→1）⇒ latent cleanup defect 仍被门捕获
- Observer ON/OFF 在修复后代码上零漂移 **OK(skipped=1)**
- C1 生产 R2_pickup_not_before_delivery = **0**
- paired replay 580c937 → fixed：**第一处分歧 index=369 / t=43 / task_3 TASK_LOADED**，
  可完全解释为 source pickup 修复；KPI delta 全 0（completed/rate/timeout/avg_delay/energy/swaps）
- 三条门禁 RC=0

两个重要澄清：
① **撤销旧预期"R2=0 且 R1>0"是对的，但结论方向与我上轮相反**：修复后 old 面 R1 仍 =12、R5=12，
   即 pickup 与 cleanup **并未耦合**——我上轮看到的"R1 一起归零"是 planner 改动带来的行为外溢，不是因果必然。
   C1 现在正确地继续红（红在 R4 counter=38 != legal_unique=26），cleanup 保持未修状态。
② 我把 test_1 的期望从"必须绿"改成"old/mutate/forced_cleanup 面必须红"（assertGreater(R1,0)），
   否则一旦 cleanup 悄悄变 0，门会静默失去侦测力。fixed 面只断言 R2=0 与 R3=0 —— **判据范围等于本轮修复范围**。

遗留（如实报，不当已通过）：全量套件 Ran 308 有 4 红，逐条一手核过——
test_g2 与 citation 覆盖率门**在基线 580c937 上同样表现**（standalone 分别 OK / rc=0，聚合时才红）＝预存的测试间干扰，非本轮引入；
readme_counts 与 C1 两条已由本轮修正。README 计数 --fix 同步为 38 文件/308 用例。
产物：c1_face_r2_fixed.json / c1_face_forced_cleanup.json / r2_paired_replay.json；冻结证据 c1_face_old.json 未被覆盖
（测试改为写 r2_fixed，并加了 FIXED_TRACE_NO_COUNTER 防形状假设兜底）。
### 2026-10-07（第七笔）：#69-A 12 条 cleanup 事实命运表 —— 第二个 lost-task bug；并纠正我上轮"能耗未污染"的定性过头

**先撤自己一句过头话**（BI 指出，成立）：我写过"能耗未被污染 / 途中均有载重"。`BATTERY_CONSUMED.load_at_consumption > 0`
只证明**物理载荷字段非零**，与 `load_time`/`TASK_LOADED` 是两套表达（后者才是业务取货事实）。
⇒ 正确措辞只能是「本 seed 未发现直接能耗污染证据」，不得写"lifecycle bug 不影响 energy"。

插桩又坏过一次（本轮第 3 次同类，已修）：DRONE_BECAME_FREE 在 1200 步里 0 次。根因不是没发生——
`_prev_free_status` 在 step 末尾被重算成当前值(environment.py:1251)，而我在 step **之后**读它做差分 ⇒
(not was_free and now_free) 恒 False。修法：新增 snapshot_pre_step()，在原 step() 调用前抓 free/oos 基线。
修后 DRONE_BECAME_FREE=38、ASSIGNMENT_RELEASED=38，零漂移仍 Ran 8 OK。
⇒ 教训：差分插桩必须先确认基线是在变化之前抓的；"计数为 0"有"没发生"与"基线错"两种成因，靠独立预期才识破。

命运表（trace 直读，seed=40907/greedy/1200）：12 条 cleanup 全部 ASSIGNMENT_RELEASED 发生、
之后既无 TASK_RETURNED_TO_POOL、也无再取货、也无送达；回合结束仍在 unassigned pool=0、仍在 drone_assignments=0
⇒ **从所有可寻址结构消失 = 12/12**（其中 9 条有取货证据却被清理＝更像送达前中止，3 条从未取货＝更像分配后未执行）。
out_of_service 本局从未发生；生成 44 完成 38 ⇒ KPI unfinished=6（这 12 条不计入 unfinished，因为计了 completed）。

⚠ returned_to_pool 全 0 的正确解读：回池动作只存在于 set_drone_out_of_service()(:517，含 update_status('pending')
+ unassigned_tasks.append :573-574)，该函数本局从未被调用 ⇒ 这是「该路径未触发」，**不能**说成「系统判定已完成故不必回池」。
要区分"没有回池代码被执行"与"回池代码不存在"，前者成立后者不成立。
⇒ 按 BI 分支这属于「release 后既没回池也没再分配也没 delivery evidence 就消失」＝**第二个 lost-task bug**（与 R1 同源后果不同）。

timeout 三分（trace 直读，不反推）：total=2 / legal_delivery=1 / cleanup=1 ⇒ 恰好一半超时来自非法 cleanup completion，
与 KPI 超时率 0.0526≈2/38 一致（分母同为被污染的 counter）。BI 猜的"约一半"此处为实测。
产物 docs/取证输出/cleanup_fate_table.json。C1 门仍 old FAILED(2)（未修任何 bug）。

**#69-A 完成即停，未动 #69-B**。等审查确认：① 这 12 条归 lost-task（进 #69-C）还是先按 requeue 处理；
② #69-B 的"source leg 最终航点才有 source 语义"是否需同时覆盖顺路接入(detour)生成的航线。
VERSION 未动，生产文件对 c4069ac 基线仍零改动（仅 Observer），三条门禁 RC=0。
### 2026-10-07（第六笔）：#68-C 取证轮 —— reason 字段作废、A 交叉表补齐、B R2 机制复现、C 动作插桩

**总原则遵守：本轮只取证，未修 lifecycle。**

一、Observer 字段去业务语义：`reason="cleanup_released"` 撤除（released/failed/delivered 未经证明不许出现），
改为 `record_origin ∈ {destination_branch, is_free_cleanup_branch, unknown_call_site}` +
`has_destination_evidence` + `has_load_evidence`。归因连踩两刀才立住：① sys.settrace 在本包装里拿不到被包裹函数的帧
⇒ 38/38 全 unknown；② traceback 倒序先撞上外层包装帧（行文本同样含 _record_task_completion）
⇒ 38/38 全成 is_free_cleanup_branch（比第一次更隐蔽：给了自洽但错的答案）。
最终只认「语句以 self._record_task_completion( 开头」的帧 + 读其上方 12 行源码文本找分支锚，
得 {destination_branch:26, is_free_cleanup_branch:12}，与几何证人 legal=26/illegal=12 **两条独立路径互证一致**；
unattributed_completions=0 已写成断言（匹配不上必须显式暴露，不许静默归类）。

A 旧污染范围交叉表（2018425 老行为 / seed=40907 / greedy / 1200）：
cleanup(12) in_timeout=1 in_delay=1 Σdelay=85.5 | never_loaded_cleanup(3) 0/0/0 | dest_without_load(7) 0/0/0；
恒等式 26+12=38=counter 成立。
**新风险结论：能耗未被污染，不宣布**。途中载重采样 BATTERY_CONSUMED 共 7480 条，load_at_consumption==0 的有 0 条
（Σwh_used=10330.8 Wh 全部发生在有货状态）。⚠ 我最初想用 payload_at_reach 回答此问，但它无区分力——
连 19 条有取货证据的正常任务也全是 0（:1211 record 早于 :1214 卸货，读到同一刻已清零的值）；
若拿它说"空载飞完全程"就是错的，故改成每步采 load_at_consumption 才拿到有效证据。

B R2 最小受控复现（console/test_r2_destination_without_load.py，Ran 3 OK）：机制从源码定位非猜——
load_time 只在弹出航点带 'source' 标签且坐标等于 task.source 时才写(:1192-1203)，而标签按 point==source_route[-1]
赋给规划末点(:1853-1862)；当 plan_route_around_buildings(current_pos, source) 只返回一个点时走 else 分支，
贴 'source' 的是唯一点而非真取货点 ⇒ 严格相等失败、取货事实丢失，dest 航点照常弹出。
三组 C1 正常航线须命中／C2 单点退化必丢 TASK_LOADED（复现）／C3 双重校验下退化判不命中＋正常判命中。
C3 只在内存定义替代规则，不落盘不改生产代码。

C 动作插桩前先验证动作真实存在：assignments.remove() :1220/:1240、del drone_assignments :1231/:1242/:1245、
回池 :573-574（update_status('pending')+unassigned_tasks.append）、out_of_service drone.py:111
⇒ 新增 ASSIGNMENT_RELEASED(had_load) / TASK_RETURNED_TO_POOL（仅当该 id 确实出现在 unassigned_tasks 才记）/
DRONE_OUT_OF_SERVICE（false→true 差分）/ BATTERY_CONSUMED。全部用状态差分发现，不锚行号。
零漂移重验 Ran 8 OK（sequence sha256/KPI/task_ids/counters/energy/swap/steps 逐位相同）。

三、R2 判据改用 sequence_no：离散仿真同一 sim_time 可有多事件 ⇒ seq(TASK_LOADED)<seq(DESTINATION_REACHED)，
事件写入统一分配全局 seq。

门自身又坏过一次：_inject 长期读已废弃的 reason 键 ⇒ cand=None 原样返回，mutate 面读数与 old 面完全相同
＝一次没有变异的"变异测试"。改为新 schema 取目标 + 找不到就 raise [MUTATE_NO_TARGET] + 注入后 assert len 增大。
现在 mutate 面 completions 38→40、R3 0→1，注入确实生效。印证台账"变异要先证生效"。

README 计数 --fix 同步为 38 文件/307 用例；三条门禁 RC=0；VERSION 1.0.0 未动；未修 lifecycle bug。
### 2026-10-07（第五笔）：审查三问逐条以一手证据回答 + C1 门建成并对旧代码转红

**Q1 报告自相矛盾——我错了**：打出真实事件 JSON，#68-B 交付时 **没有 `reason` 字段**
（实有字段 kind/sim_time/task_id/drone_index/load_time_raw/assigned_time_raw/deadline_raw/drone_position/
delivery_evidence/pickup_evidence/d_delay/d_ontime/d_completed）。我在 §6-H 写"含 reason"是错的。本轮补上该字段，
且只映射几何证据（destination_reached / no_delivery_evidence），**不猜业务意图**。

**Q2 清单与数字不符——两边都错一半**：白名单声明 11 类，实测只出现 **4 类**；
`DESTINATION_REACHED`/`ASSIGNMENT_RELEASED`/`DRONE_BECAME_FREE` 的 record 调用次数分别是 0/0/1 ⇒ 本局一个都没发。
berth 两类**确是** Observer 事件（非旁读统计）⇒ C4 有证人；但 **C1 缺送达证人** ⇒ 本轮补入 DESTINATION_REACHED，
现实测 5 类。summary 改读 `event_kinds_observed`（实测集合）而非白名单声明。

**Q3 "对 HEAD 零 diff"不足——批评成立**：那句只证明工作树干净。按指定命令重跑
`git diff --numstat c4069ac..4db8c0e -- frontend backend_si` ⇒ 唯一一行 `219 0 frontend/consistency_observer.py`，
即纯新增文件、八个既有生产文件零改动，无条件/赋值/返回值/控制流修改。

**C1 门 `console/test_c1_lifecycle_gate.py` 三面结果**：
old FAILED(failures=2,skipped=1) ← 本该如此；mutate FAILED 且 R3_duplicate_completion=1（注入的重复被抓到）；
fixed Ran 0 tests OK(skipped=1) ← 如实标『未跑』不当通过。
old 读数：counter=38 legal_unique=26 R1=12 R2=7 R3=0 R4=1 R5=12（其中从未取货 3）
⇒ 与审查预期完全一致；恒等式 counter==legal_unique+R1 成立，无第三类漏网。

**意外发现第二个缺陷 R2=7**：task_15/16/17/20/21/26/38 的事件都是
DESTINATION_REACHED(t=X) → COMPLETION(t=X, load_time_raw=None)，两条同刻且取货事实缺失
⇒ 走的是 dest 路径（几何证明确实到了 destination）但 load_time 从未写入。机制候选：source 命中要求坐标严格相等(:1201)，
顺路吸附/一步跨过取货点时不会精确落在 source ⇒ 取货事实丢失而送达成立。**这是推断非定论**，需单独受控复现，本轮不修；
但不能因"像量具问题"就把 R2 从门里删掉。

我自己在这步的两个错（都已修）：① FACE 从 sys.argv[1] 读 ⇒ unittest 把模块名塞进 argv，face 变任意串走 else 分支，
**本该红的 old 面第一次跑出来是绿的**；改为只认环境变量 C1_FACE，非法值降到最保守的 old，并加文件名 assert 防再产垃圾产物。
② 第一版 test_1 打印违规数却不断言 ⇒ 典型都会绿的门，重写为逐条 assertEqual(...,0)。教训：**门输出里有数字 ≠ 门有牙**。

Observer 改后零漂移复跑仍 OK(Ran 8)；三条门禁 RC=0。按指令 **C1 稳定红即停，不进入修复**。V6 继续暂停。VERSION 未动。
### 2026-10-07（第四笔）：#68-B 完成 —— 只读 ConsistencyObserver，双跑零漂移通过；按指令停止，不自动修 lifecycle bug

交付 `frontend/consistency_observer.py` + `console/test_consistency_observer_zero_drift.py`（8 项断言）
+ 两面原始输出 `docs/取证输出/observer_zero_drift_{off,on}.json`。

三条约束的实现方式：**没有** `TASK_COMPLETED` 这类带语义事件，只有 `TASK_COMPLETION_RECORDED`（"计数器被加 1"的事实）；
事件名走白名单，未登记名进 rejected ⇒ `test_f` 断言 rejected==[] 即"本模块不许发明状态"；全程只读 env 既有状态；
monkeypatch 仅实例级且原样返回、观察异常被吞成一条错误事件不影响仿真。**八个生产文件对 HEAD 逐文件 git diff 为 0**。

零漂移（seed=40907/greedy/1200 各跑一整局）：sequence_len 1200/1200、action 全序列 sha256 相同、
total_completed 38/38、episode_step 1200/1200、generated_task_ids 相同、KPI 全字段 dict 相等、energy/swap 相同 ⇒ Ran 8 OK。
轨迹非空且对账：events_total=77、completions_recorded=38==计数器==KPI、with(26)+without(12)==38 恒等式、
never_loaded=3、ΣΔdelay=106.5、berth occupy/vacate 各 5、TASK_LOADED 29。
⇒ **26/12/3 与上轮 traceback 行号归因逐位一致**（已钉成 test_h）：两个不同量具互核，几何证人那个不随代码挪行失效。

本轮我自己的两处错（都已修并写进文档 §6-H）：
1. **归因时机错**：把 DESTINATION_REACHED 放在 step() 之后重算谓词，而 dest 路径紧接着 `assignments.remove()`
   （environment.py:1220）⇒ 事后遍历看不到该 assignment，实测 with_delivery_evidence=0（真值 26）。
   **门当时仍全绿**——我只断言"两类之和==总数"，它对全错划分同样成立。是读产物发现的不是读断言发现的。
   ⇒ 教训：**恒等式成立 ≠ 分类正确**；新增分类维度必须配正例下限断言（现由 test_g/test_h 补上）。
2. **字符串替换把源码改坏**：恢复被变异行时 `"\...\..."` 里的 `
` 落成字面两字符 ⇒ :87 SyntaxError、单测 Ran 0 tests，
   我差点当成"产品有问题"。改用 Edit 显式换行 + `py_compile` 作改码后固定检查。印证台账"批量字符串补丁会半成功"。

套件：console `Ran 298`（新增 8）skipped=1，唯一红是 test_readme_counts_match_measured 抓到"加了测试没同步 README 计数
（35/290→36/298）"，按它给的 --fix 修好复跑 OK。两条 --verify 与 verify_data_provenance RC=0。VERSION 未动。
变异面另证 test_h 有牙：把 delivery_evidence 强置 True 后 got=38 want=26 当场红（两面原始输出均留档）。
**下一步 #68-C：用这份轨迹建 C1 完成不变量门，门先红再谈修复。**
### 2026-10-07（第三笔）：cleanup × timeout/delay 交叉污染核查 —— 答案是 >0，三个 KPI 共用同一棵被污染分母

BI 要求补掉的一格。先定位真实计算入口（不反推）：`timeout_rate = 1 − total_on_time_tasks / total_completed_tasks`（`environment.py:986`）、
`avg_delay = total_delay / total_completed_tasks`（`:987`）、单条 `delay = max(0, completion_time − deadline)`（`:439-443`）。
⇒ **完成率、超时率、平均时延三者共用同一棵被污染的分母**，不是只污染分子。

归因方式改为"每次 `_record_task_completion` 调用前后的计数器增量"（非事后猜测），并先用恒等式验量具：
```
ΣΔcompleted = 38  == KPI 完成任务数 38.0
ΣΔon_time   = 36  → 超时数 2，与发布超时率 0.0526×38 = 2 一致
ΣΔdelay     = 106.5 == 平均时延 2.8026 × 38 = 106.5
```

| 桶 | n | in_timeout | in_delay | Σdelay |
|---|---|---|---|---|
| cleanup | 12 | **1** | **1** | **85.5** |
| never_loaded_cleanup | 3 | 0 | 0 | 0.0 |
| dest（对照） | 26 | 1 | 1 | 21.0 |

⇒ 按 BI 给的分支走 **>0** 那条：`timeout_rate` 与 `mean_delay` 同受此错误直接污染。
且 cleanup 只占完成数 31.6%，却贡献全部延迟量的 **80.3%** ⇒ **对平均时延的污染强度远大于对完成率的**。
反事实（剔除 12 条 cleanup）：完成率 0.8636→0.5909(+0.2727)、超时率 0.0526→0.0385(−0.0142)、平均时延 2.8026→0.8077(−1.9949)。
⚠ 这是**影响量级估计不是修正值**（它假设"剔除即正确"，而 cleanup 该归哪个终态未定）；n=1 seed 数值不外推，可外推的是结构事实。

两处自我纠错（都是量具错，不是新发现）：
1. 第一次算反事实把超时数写成 `int(round(超时率×T))` 再套错符号，得"剔除后超时率 **1.3462**"这种 >1 非法值。
   修成逐条 `d_ontime` 求和才得 0.0385 ⇒ **派生比率算完必须验定义域，概率越界即算式坏，先怀疑量具**。
2. 差点把 never_loaded 的 delay=0 写成"未取货任务不影响时延"：实测三条 `cleanup_t`(172/190/886) 均 < 各自
   `deadline`(626/579/1071)，而 delay 只看 `completion_time − deadline`、**与是否取货无关** ⇒ 那是**本 seed 巧合非免疫**。

另采纳 BI 关于恒等式的提醒并写进文档：`total_completed_tasks = dest + cleanup` 只证明"旧计数与旧事件路径自洽"，
是量具没测错的证据，**不是未来正确性判据**；修复后该成立的是
`total_completed_tasks = 具有合法 delivery completion evidence 的唯一任务数`，后者才是 #68-C 要断言的。

六格状态定稿（生产可达性已证 / 正式 KPI 消费已证 / 业务语义错误已证 / 污染范围已查清 / 正确终态语义未定 / 修复暂缓）。
README §已知局限 同步补污染范围。**旧逻辑挖掘到此停止，下一轮进入 #68-B 只读 Observer**（record fact 而非 infer state，
不得生成 `task_state=completed` 变成第四套状态系统；固定 seed 双跑要求正式 KPI + action/assignment 序列 +
generated task IDs + total_completed_tasks + energy + swap + steps 全零漂移；零漂移通过即停，不自动修 lifecycle bug）。
编辑过程中我把本文 §6-G 插到了 §7 之后、并一度造成 §7 重复标题，连续三次切片失败后改用"先打印行号再按行号切"修好——
记入工具性教训：**改文档结构要先读回实际行号，别靠字符串偏移推断**。未改生产代码，VERSION 未动，未新增测试。
### 2026-10-07（第二笔）：生产路径复现成功 —— 完成率分子被兜底路径污染，历史 KPI 转 pending revalidation

BI 第 1 步达成。驱动方式换成**论文实验同一条正式路径** `experiments.worker.run_one(config,"greedy",40907,1200,内置杨浦地图)`
（含 `greedy_action_from_observation`），不再是我自写的循环：

```
completion 记录合计 = 38      ← 与 KPI「完成任务数 = 38.0」逐位相等（第二证人成立）
  ├─ dest（抵达 destination）  26
  └─ is_free_cleanup           12   ← 占完成数 31.6%
       └─ load_time is None（无取货证据）= 3
KPI：生成 44 | 完成 38 | 完成率 0.8636 | 超时率 0.0526
样例 task_3 t=172 load=None assigned=0 / task_8 t=190 / task_24 t=886 assigned=446
```

⇒ 判据只需"至少一条 cleanup 且无 delivery evidence"，实测 12 条（其中 3 条连取货都没有）。
产物留档 `docs/取证输出/prod_completion_repro.json`。
⚠ 口径纪律：**不引用上一轮临时驱动的 44%**，本轮生产读数是 31.6%，两者不可混用；n=1 seed ⇒ 31.6% 也只是这一格。
但"`total_completed_tasks == dest + cleanup` 且 cleanup 无任何送达判定"是与 seed 无关的**结构事实**，这才是立门依据。

采纳 BI 第三处纠正：`completed_task_log` **也不能叫完成真源**（它截断至 120 行）⇒ 实为三套性质不同的数据：
单步缓冲 `completed_tasks`(:239-242,:1528 clear) / 有上限审计记录 `completed_task_log`(:480-481) /
唯一承重的聚合计数器 `total_completed_tasks`(:276)。**没有一套是完整、持久、逐任务的 completion truth source。**
⇒ C1 因此更清楚：唯一承重的是一棵计数器，它没有任何可核对的明细层。

后果登记（README §已知局限 + 本文 §6-7-D）：闭环前所有已归档 `results/compare/*.csv` 与论文侧引用的
完成率/超时率/平均时延一律标 **pending lifecycle-consistency revalidation** —— 不是全部作废，而是不得再默认当可信结果。

修复方向按 BI 第 4 步：**先不定性就不动代码** —— fallback 想表达的语义在
aborted/released/failed/unassigned/特殊终态 五种之间未定，等 #68-B Observer 的事件轨迹反推
（这些任务后续是否又被派发、机巢是否占用、无人机是否 out_of_service）再定业务语义。不删调用、不改计数。

另：我一度把本文 §6 复算命令整节替换掉（那正是我给每篇文档立的规矩），发现后补回并加了一条警告——
T4 靠 traceback 行号归因，**行号随代码改动失效**，重跑前须先重新定位 1211/1224/1239/1244。
V6 编码继续暂停。未改生产代码，VERSION 未动，未新增测试，三条门禁 RC=0。
### 2026-10-07：#68-A 当前状态真源图 —— 撤两处我自己的错判，并实测到一条真的逻辑矛盾

BI 纠正我上一轮两处定性，均接受：① `Task.status` 应称 **stale shadow state / 状态真源分裂风险**，不是"已发生双重解释冲突"；
② `predicted_*` 缺失证明的是 **C6 Plan-vs-Actual 不可审计**，不能拿来宣称"时间一致性失败"（那是 C3，查事件顺序）。
Gate 体系按 C1–C6 重排替换我的 I1–I5。交付 [`docs/当前状态真源图.md`](docs/当前状态真源图.md)。

**我又撤了两条更严重的自己的错**（都在本轮实测中暴露）：
- 「完成由 `completed_tasks` 列表决定」**是错的**：`environment.py:239-242` 注释写明它是**本步临时缓冲**、
  `_compute_reward()` 末尾 `clear()`（`:1528`）⇒ 真源是 `completed_task_log`，且**上限 120 行、超出即删**。承重结构读错了。
- 我在文档初稿把兜底写成「12/12 从未取货」，实测是 **5/12**（`load_time is None`），而 `delivery_time==0` 有 12 个
  （含"取了货但取送同刻"）⇒ **两个数口径不同，不能混用**。已在 §2 就地写出差别与可站住的表述。

§2 实测发现（seed=40907、1200 步跑满、贪心直派驱动）：`_record_task_completion` 共 27 次，
其中 **dest 路径 15 次、is_free 兜底路径 12 次**（`environment.py:1234-1244`）⇒
**12 个未经"抵达 destination"判定即计入 `total_completed_tasks`，其中 5 个明确从未取货**；
机制是 `if load_time is None: load_time = assigned_time` 让未取货任务得到一个看起来正常的 delivery_time 而非"未完成"标记。
这才是 BI 定义的真不自洽（执行结果与业务语义不一致），不是预测误差。
**为什么一直没被发现**：status 从不写终态（前端/API 看不见）、统计只加计数器（聚合值正常）、log 截断 120（明细也会被削）。

边界如实标注：n=1 seed × 1 种驱动方式，且我的驱动非生产 `greedy_action_from_observation` 同源 ⇒
**44% 这个比率不得引用，须先用生产 worker 复算**；但"兜底会计完成"是代码级事实，与驱动无关，足以立门。

§4 顺序采纳 A→E：本轮 #68-A 完，下一轮 **#68-B ConsistencyObserver 旁路事件轨迹**（第一版不是新真源、不参与业务决策，
可做零漂移 gate）；#68-D DecisionRecord **只记当时真算过的量**（Greedy 实际只有 proximity/range_match 就只记这两个，
不许为表格漂亮凭空补 ETA/energy ⇒ 那会造出"展示能力大于模型能力"）。V6 不停但不同时大规模编码。
未改生产代码，VERSION 未动，未新增测试。
### 2026-10-06（第六笔）：三层可信度结构落地第二层 —— E2E 一致性门设计，实测「五条不变量只有两条今天能建门」

BI 提出系统级逻辑自洽判据「前一层假设不得被后一层无声推翻」，要求 V6 之外另立 End-to-End Consistency Gate。
交付 [`docs/端到端一致性门设计.md`](docs/端到端一致性门设计.md)。**本轮先测"哪些不变量有证人"，未写门代码。**

§2 现状实测（每条都是本轮现扫，不是推断）：
| 不变量 | 证人 | 能否今天建门 |
|---|---|---|
| I1 任务守恒 | `Task.update_status` 合法集 5 态，但全仓仅 2 处调用（`environment.py:573→pending`、`:1134→assigned`）；**`completed`/`failed` 零调用** ⇒ 完成实际由 `completed_tasks` 列表决定（`:479`），status 永停 assigned | ❌ 两套并行状态解释，其一从不更新 |
| I2 电量守恒 | `drone.py` 写入点封闭可枚举（`:92,170,219,266`）| 🟡 部分：env 侧事件日志命中 0，跨步核对缺凭据 |
| I3 时间一致 | **预测值无任何留存字段**（`predicted_/estimated_` 在 env+drone 命中 0）| ❌ 「估 100 Wh / 实耗 150 Wh」连被比较的两个数都没同时存在 |
| I4 资源守恒 | 执行层真管容量：`has_berth`=occupied<berths、occupy/vacate（`charging_station.py:30-46`）+ `_manage_berths` 动态仲裁（`:815-840`）| ✅ 今天就能建 |
| I5 统计一致 | 统计不从 Task.status 推（`status=='completed'` 命中 0）⇒ "独立重算"只是换写法读同一列表 | ❌ 无第二证人 |

⇒ 六条预注册门里**只有 EG-1、EG-6 今天能落地**；其余四条的前置是 §4 的最小可观测面（P-1..P-4）。
按项目自己的规矩「期望值为 0 的夹具给不了护栏牙」——不写六个都会绿的门，那比没有门更坏。

§3 你最关注的调度 vs 机巢：**两段论成立**。执行层自洽（泊位容量真在管、满了排队、按紧迫度移交），
调度层缺口真实（`backend_si/*.py` 中 `berth` 0 命中）⇒ 这是**建模间隙不是实现 bug**。
据此把两类差距分开：algorithmic gap = c_GA − c_opt(P_seq)（Oracle 能答）vs
modeling gap（Oracle 答不了，只能由本门 + 实验 C 观测）；并明写 modeling gap 今天**不可量化成单一数字**，写成"gap=X%"就是新的越界。

§4 P-1 的消费链普查结论与我的预期相反：全仓 `\.status` 命中 3 处且全是同名不同物
（server.py:821 实验服务、zip_range_extract.py:38-39 HTTP）⇒ **Task.status 读取方 = 0**，
补终态不会改行为；代价是它今天是纯装饰字段（写了没人读）。真实成本是要把统计接到事件日志才形成互证。仍属产品代码改动，等你点名。

§5 场景矩阵 S-A..S-E（S-D 即你举的 A/B 抢一泊位的例子）；§7 三档措辞不得互相顶替：
内部逻辑自洽性 / 算法正确性 / 现实有效性。未改生产代码，VERSION 未动，未新增测试。
### 2026-10-06（第五笔）：V6 阶段二设计稿 —— 先纠正我自己上一版的两处错

BI 裁定：保留 P_assign / P_seq 两个问题族，**优先 P_seq**；Oracle 与生产隔离、不改四个调度器；
产品权重冻结但分「忠实性口径 / 合理性口径」两套分析；gap 公式须单独定义（含负奖励可能非正）。
交付 [`docs/P_seq精确基准设计.md`](docs/P_seq精确基准设计.md)，**仍未写求解器**。

§0 是我自己上一版（`5435acc`）的三条更正，全部本轮实测：
- **C1 H5（机巢泊位 ≤ berths）作废**：`backend_si/*.py` 里 `berth` **0 命中** ⇒ 泊位从未进入 GA 静态优化，
  解码只在电量 <20% 时插一次机巢往返、不查占用也不竞争时刻。按你「未进入静态优化的机制不得为使问题完整而擅自加入」剔除。
  **这条错误的性质是"把系统应该有的约束当成代码里有的约束"**，正是你要防的那类。
- **C2 漏了一条真硬约束**：`max_chain_tasks = 3`（`config.yaml:117` → `chain_codec.py:159`，局部搜索同受 `:350`）。
- **C3 「最优值可能为负」方向对但要算量级**：用产品权重实跑 `chain_cost` ⇒ 正常解 3968、全弃单退化解 80000
  （罚项 1e4×8 主导）⇒ w_unassigned=1e4 下 cost_opt 大概率正；但不构成定理（match∈[0,1]×80 可压过小 makespan），
  且 **cost_opt=0 时相对 gap 实测抛 ZeroDivisionError**、cost_opt<0 时 Δ/c_opt **符号翻转**
  （构造例 −100/−50 ⇒ −0.5，读起来像"比最优还好"）。⇒ 主口径改绝对间隙 Δ=c_alg−c_opt，相对口径加符号前提。

其余：§2 Oracle 双路径（O1 穷举 / O2 独立 CP-SAT，均不复用 chain_cost·compute_match）+ 隔离验收门；
§3 复杂度**实算而非估**：(J+1)^T×T! 在 (4,2)=1,944 … (6,3)=2,949,120 可暴力，**(8,2)=2.6e8、(8,3)=2.6e9 不可暴**
⇒ |T|=8 那档不承诺穷举互核；§5 三层协议 A/B/C，其中 **PSO 归类待你裁定**（fitness 三项加权 ≠ P_assign 目标，
且不校验 H3 ⇒ 目前不是任一问题的忠实求解者）；§6 七条预注册门，G4「Oracle 独立重算的 J 与 chain_cost 逐位相等」
是承重墙——它检验的是"两边说的是不是同一门数学"，建议实现顺序按 G4 先行。

同步订正 `docs/调度问题数学定义.md` 的 H5/H6 行。未改任何生产代码，VERSION 未动，未新增测试。
### 2026-10-06（第四笔）：V6 第一阶段 —— 调度问题数学定义，结论是「四个算法没在解同一个问题」

BI 指令：独立精确求解器必须求解与当前调度器**相同的数学问题**，否则算出的"最优"无法证明现有解的质量。
本轮只做提取与核查，**未写求解器**（按指令：完成数学定义后先交付审阅）。
交付 [`docs/调度问题数学定义.md`](docs/调度问题数学定义.md)，每条差异带 `文件:行`，且**行号本轮逐条复核过**
（7 处区间断言 + 4 处符号定位全部命中；PSO fitness 装配实测在 `pso_scheduler.py:690`）。

三处不一致，任一都足以否掉"单一基准"：
| | Greedy | PSO | GA | OR-Tools |
|---|---|---|---|---|
| 顺序自由度 | 隐式先到先得 | **无**（按输入序） | **有**（排列+局部搜索） | **无** |
| 目标项 | `0.6·match+0.4·proximity` | `0.6·on_time+0.3·(−delay)+0.1·(−energy)` | `makespan+2·tardy+0.01·dist+1e4·unassigned−80·match` | `1·makespan+1·Σtardy` |
| 允许弃单 | — | — | 是（罚 1e4） | **否**（C1 硬等式 `==1`） |
| 电量约束 | 打分含续航项 | fitness 累计 | **硬约束** ≤ b·(1−0.1) | **完全没有** |

⇒ OR-Tools 的可行集与 GA 的不是包含关系（CP-SAT 解可能违反电量约束；GA 解可能违反"全分配"）。
**⇒ 需要两个基准：`P_assign`（服务 PSO/OR-Tools）与 `P_seq`（服务 GA）**，裁定前不写求解器、不做四算法横向排名。

其余两节：§1 三层分离 L1 静态批次 / L2 滚动触发（阈值 15 决定批次内容 ⇒ "全局最优"在 L2 **未被定义**，不是未证明）/
L3 系统 KPI，并给出允许与禁止的表述各一条；§3 按 BI 要求把 V1–V5 的真实数据误差阈值**全部标为未冻结**并写明各缺什么，
唯一例外是 V6 的 `gap`（纯数学量，合法性来自定义而非实测）。Validation Matrix 同步加 §1-bis/§1-ter。

目标函数单位混合（s + m + 个 + 无量纲×80）是**既有属性**，冻结时原样保留权重 —— 改了基准优化的就不是产品行为。
未改任何调度代码，VERSION 未动，未新增测试。
### 2026-10-06（第三笔）：两处措辞收窄 + 交付 Validation 矩阵

用户收口数据溯源审计于 `c76e8a5`，本轮只改表述精度、不重启审计：

1. **「数据真实性 ✅」是错的**，改成三件各自独立的事：样本完整性 5/5 通过 / 样本类型 5/5 显示 SITL 特征 /
   **真实外场飞行数据尚未确认**。已证的只有前两件；把第三件叫"真实性"会让读者以为验过真值方向。
2. **`code/*` 不在 data.zip ⇒ 只能证 manifest「不是仅由这个 ZIP 生成」**，不能证它来自 `asi_runs.zip` /
   `asi-runs-2.zip`（那两个包不在手上、未核对）。我上一笔写的"它覆盖的是那些上游原始包"属越界，
   现降级为**待验证来源假设**；§4.1 表格里 67 个的归属也标成 manifest 自称、未经核对。README 同步。

新增 [`docs/Validation矩阵.md`](docs/Validation矩阵.md)（#65 的执行载体）：先拆研究对象——
**飞行物理子模型 vs 协同调度模型，参照不可互相顶替**（拿到 CMU 209 次实飞也只证前者，
日志里通常没有多机分配、机巢竞争、订单到达、重规划这些业务事件）；六行矩阵 V1–V6 各带
当前证据 / 待补证据 / 参照档位 R·I·C / 指标 / 优先级 / 适用范围（末列现为"未定"，填死才算设计完成）；
判据冻结规程四条顺序强制（先写判据→切独立验证集→才比对→比对中不改），并明写
**不许一拿到日志就拟合参数**（拟合会把验证集变成训练集）。V3–V6 不需要外部数据即可启动。

### 2026-10-06：Validation 路径收尾 —— 证据等级定格在「官方规格派生」，未锚定项如实保留

新增 [`docs/证据等级与Validation边界.md`](docs/证据等级与Validation边界.md)，把三档口径分开写清：
内部一致性 ✅、外部可回溯 ✅（大部分）、**实机有效性 ❌ 且当前无可用通道**。

要点：能耗链的全部外部输入只有三个官方数字（单块 1984.4 Wh / 空载 28 km / 满载 16 km），
四个派生量是同一组数被除了四次 —— `0.142 × 1.75 = 248` 是恒等式（28 约掉 ⇒ `E/28 × 28/16 = E/16`），
不提供新信息；全仓零拟合实现 ⇒ **项目没有标定环节，只有规格派生**，对外措辞必须用后者。

Zenodo 19617182 的结论：清单与对方持有件逐字节相同（sha256 前缀 `876e5ca895c4fcea`），
真 `.ulg` 共 67 个 / 1526.2 MB，抽样 5 个 md5+尺寸 **5/5** 对账通过 —— 证人确实是外部的。
但每个文件都含 170 个 `SIM_*` 参数（`SIM_BAT_DRAIN`、`SIM_BAT_ENABLE`、16 个 `SIM_GZ_EC_DIS*`）
⇒ Gazebo SITL 输出，电量是模型按设定速率递减的结果。**用它反推 Wh/km 会得到自洽的假验证值，故不产出该数值**，
`世界逻辑规格书 §5-D` 维持「未锚定」。README §已知局限同步加一条。

**本轮我自己的两次误判（都是量具错，不是数据错）**：
1. 先用 `grep -o 'SIM_...'` 扫原始字节得 `SIM_n=0`，据此几乎要下"这批日志不含仿真参数"的反向结论；
   又用"`b[:16]` = magic+version+timestamp"的定长假设分帧，读到第 2 条报文就跑飞。
   实际首条报文是 `'B'` flags（size=40）。唯一可靠的是 token 级正则扫描，结果 5/5 均为 170 个 `SIM_*`。
2. 第一次跑 `--verify` 时把命令接在 `| tail -3` 后面读退出码 —— 拿到的是 `tail` 的 0 而不是生成器的；
   同时 GBK 控制台下 `⇒` 触发 `UnicodeEncodeError`。改成 `PYTHONIOENCODING=utf-8` + 落盘再取 `$?`，
   两条门 RC 均为 0。

套件基线：console `Ran 290 OK (skipped=1)`、experiments `Ran 32 OK`。VERSION 未动（`1.0.0`）。

### 2026-10-06（同日第二笔）：撤回"md5 证人是外部的"这句话，并登记全量分类未完成

上一笔 §4.1 写「manifest 与 Zenodo 逐字节相同 ⇒ 5/5 对账的证人是外部的」。**这句被本轮实测驳回**：
Zenodo 记录 19617182 的文件清单只有 245 条中央目录项，其中 **没有任何 `code/` 成员**；
而仓内 `data/raw/px4_logs/manifest.csv` 登记了 9 个 `code/*` 文件（含上游自己的打包脚本
`make_asi_dataset.py`、`asi_extract.py`）。⇒ 这份 manifest **不是从 data.zip 生成的**，
它覆盖的是 `asi_runs.zip` / `asi-runs-2.zip` 等上游原始包（这些包此刻不在该记录里），
生成者与时点均不可考。按规矩记为 **「md5 原始计算者：未确认」**。

同时如实登记一个口径漏洞：**「抽样 5/5 是 SITL」推不出「全部 67 个都是 SITL」**。
全量分类需要 ~1.5 GB 传输，本轮尝试后中止（只留空目录，已清），因此当前结论的有效范围只有那 5 个文件。
`docs/证据等级与Validation边界.md` 同步订正为三档分离：文件完整性 / 记录来源 / 数据真实性。

顺带取回并入库一份小的上游件 `data/manifests/ulog_manifest.txt`（585 B，md5 `78916e37…` 与登记值吻合）：
它是 E1–E5 × run01–05 = **25 条纯路径列表、不含哈希**，且这 25 条里有 24 条能在我们的 67 行中匹配到 ——
说明"哪些日志入选"确有上游记录，但它**不携带 md5**，因此不能用来认定哈希的计算者。

### 2026-10-05：仓库状态订正 —— "无 remote"这句话从本轮起是错的

本仓**有** remote（`origin = https://gitee.com/acgvgh/swarm-balance.git`，远端默认分支 `master`，
本地分支 `main` 配的是 merge origin/master）。上面 2026-10-02 那批条目里反复出现的
"`VERSION` 仍 1.0.0、**无 remote**"在写下当时就是失实的：真实状态是"有 remote 但未推"，
两者对外行可验证性完全不同（前者云端什么都看不到，后者看得到但滞后）。
按规矩历史条目不改写，只在此处指认 + 给正确版本。

本轮已把 main 快进推到 origin/master：`78dfe6c..2e7dc37`（11 笔，非 force），
推后 `git rev-list --left-right --count origin/master...HEAD` = `0  0` 复验通过。
另一条待办：`origin/dev` 停在初始提交 `4d8ac93`，落后 main 165 笔 —— 是否删除属破坏性操作，等用户点名。

### 2026-10-05：Phase 0 收尾 —— PSO 门「无分母」用修 fixture 闭合，判据与阈值一字未动

`console/test_speed_fallback_gate.py::test_g2...` 长期红：`[pso][NO_DENOMINATOR]`。诊断结论是
**fixture 工况选错**，不是代码缺陷、也不是判据过严：出厂配置 10 机 / 60 任务下 `pending_buffer`
峰值只有 2，而批量优化触发阈值是 15（`backend_si/config.yaml:16`）⇒ `optimize()` 零调用 ⇒
门根本没有分母。门换成 C-1 重载工况后 greedy/pso/ga/ortools 四者均有非零正例。

新增常驻牙线 `test_g2teeth` + `console/phase0_speed_gate_teeth_probe.py`，三面对照（seed=40901、
episode=3600、阈值不变）：`gate`(240/mix6) opt=1477 flush_size=1 peak=15；
`noDenom`(60/mix10) **opt=0** peak=2 ← 原红门所在格；`mutate`(240/mix10) opt=3 **flush_size=0** peak=3。

**本轮我自己两次新误判（与前几轮不同族，单独记）**：
1. 把变异打在 `num_drones` 上当单变量 —— `environment.py:144 build_fleet_drone_types()` 先按
   `fleet_mix` 展开机型再截断/补齐到 `num_drones`，所以 mix 合计 6 时改 `num_drones=10` 仍是那
   6 架机，门照样绿被我差点读成"门无牙"。现在 fixture 里有恒等式（mix 合计 != num_drones 直接抛）。
2. 想拿 `optimize_calls > 0` 当牙 —— 变异后仍有 3 次 timeout 兜底足以糊过去；会归零的只有
   `flush_size`。**"有分母线"与"牙线"必须是两个不同谓词。**
负面对照已实测：阈值 15→2 时 gate 面 buffer 峰值降为 5、本门当场红退码非 0（跑完已还原）。

顺带修掉一个真实的跨模块缺陷：本门 import 期装临时配置，原先 `tearDownClass` 删目录并 pop 变量，
而 `config_loder.py:108` 每次调用重开文件、`charging_station.py:99` 在 import 期就调它 ⇒ 字母序靠后的
`test_swap_time_gate` 吃悬空路径 FileNotFoundError。现改为还原指针、保留目录。

**登记一条影响所有对比实验的口径限制**：轻载（机多单少）下批量优化器不介入 ⇒ PSO/GA 与 Greedy
行为等价。任何"四算法性能对比"必须在重载场景做，否则比的是同一个算法（总纲 §17.3 + README）。

套件：console 286/286 OK(skipped=1)、experiments 32/32 OK。commit `2e7dc37`。

复算：`python console/phase0_speed_gate_teeth_probe.py gate|noDenom|mutate`；
`python -X utf8 -m unittest discover -s console -p "test_*.py"`。

### 2026-10-05：本地运行包入口 `scripts/reproduce_phase1b2.py`（一键复现 1B-2 结论）

预检（解释器/依赖，缺了就报该用的绝对路径）→ 逐格跑 worker → **现算**超时率/完成数对照表与
穷举符号检验精确 p（复用 `console/_paired_readout.py`，与常驻门同一把尺子）→ 打印已知问题清单。
完整模式 = C-1/C-2 × 8 seeds × {w=0.0, w=1.2} = 32 cells；`--quick` 只跑 seed 40901（4 cells），
脚本会显式跳过统计并说明原因（n=1 最小可达 p = 1.0，空表比装饰性 p 值诚实）。
本机实测输出：超时率 4/4 组 8/8 全同号下降、精确 p = 0.0078；完成任务数 6~7/8 变差。
日志写 `results/adhoc/`（已 gitignore）。commit `c81081c`。

### 2026-10-04/05：Phase 1B-2 ETA-aware 调度 —— 以【约束】身份成立、以【奖励】身份被否

设计（`11feca3`，未改代码先行）→ 实现 + 72-cell 实验（`136a04c`）→ 机制诊断 → A 方案落地为
约束式罚分（`6e3b479`）→ n=8 同号性检验 + 演示开关 G14（`a6018a6`）。
公式：`score += W·min(0, slack_full/300)`，`slack_full = rt − ETA(取货) − 送货腿/speed`；
出厂 `reach_weight = 0.0` ⇒ 生产行为零漂移（G14a/b/c 三态钉住：出厂值为 0、config 键被消费、env 优先）。

**奖励式为什么被否**：`clamp((rt − ETA_取货)/300)` 让超时率 6/6 seed 恶化（C1 40901 0.274→0.583）。
一手机制：ETA 只算到取货点而 deadline 管的是送达 —— task_4 取货 slack=245.8 s 看着从容被顶成冠军，
其送货腿 2277 m 要 113.8 s，真余量仅 +132 s；接单瞬间"已注定赶不上"的比例从 25.0% → 52.1%。
⇒ 不是权重问题，是分子用错了段。

**n=8 结果（两半必须一起报）**：超时率与平均时延 4/4 组 8/8 全同号下降（p=0.0078）；
完成任务数 4/4 组里 6~7 个 seed 变差（p=0.0234~0.1406）⇒ 这一层是"用吞吐换履约"。
另：w≥0.4 时 E/P 两面约 2/3 格子逐位相同 ⇒ 1B-3 须预期距离层边际效应缩到约 1/3，各层不可加。

**门被自己的变异教了两次**：G13 第一版被"恒等于 0.5 的假实现"溜过（补">3 distinct values"）；
G13e 只在 step=0 取样被 V6（摘掉送货腿）溜过（补构造夹具 G13f：近单/远单同 rt 只差送货腿）。
我自己的第二个 witness 是构造性不可满足的（drone→pickup 0% 被挡，E/P 的 reachability 不可能不同），
换成合成被挡 OD 测试 G13d。教训：**快照不能替代 episode；判别式夹具必须能区分"没触发"与"没接上"。**

### 2026-10-04：Phase 1B-1 distance-aware 调度 —— H0 被否，且 H0 的依据本身也是错的

`c537e79` 距离口径可切换（Euclidean 控制面 / PlannedDistance 实验面）+ 配对实验；
`1e65009` 撤回 attribution_trace 的追溯链（那是假证据）并用消融把归因钉在 provider 上。

**两处自我撤回**：① 1B-0 探针的分母是伪造的（padding 在截断之后追加），原公布值
7/10676 = 0.07% **作废**，修正后 7/302 = 2.32%；② 全局 RNG 污染（缺陷 g）导致 episode 级归因
不成立 ⇒ 整条追溯链撤回。我第一次的修法（每步 `apply_seed`）是错的 —— 它重置了任务生成器，
对照面完成数从 105 掉到 73，随即回滚并把过程写成教训。

GA 面阴性对照量化成功：`flush_timeout=20` 但 provider 调用=0 ⇒ 批量优化器在该格不介入。
H0（"换距离口径会改变调度决策分布"）在 C-1/C-2 × 3 seeds 两面各测下**未被支持**。

### 2026-10-02：把"配对表不构成显著性结论"从措辞升成双向门（它当场抓到两处裸引用）

上一节自己说了一句"免责声明不能只是措辞"，本轮就把它做成断言：
`console/test_readme_command_side_effects.PairedClaimConsistencyTests`（2 条）。判据两面都要能响：
① 文档里凡出现 `paired_ga_vs_greedy.csv` 这个标记，同一行或其后 6 行内必须有显著性限定语；
② 若有人把三份文档里的限定语**全删了**来绕开 ①，那条声明本身也不能悄悄消失。
另外 ①还带一条"标记一次都没出现就红"的空转保护 —— 引用点被清空同样要被发现。

**新门第一次跑就红了**，抓到两处真实裸引用：`README.md:269` 与
`docs/产品化收口与结项口径审计.md:169` 都只写"描述性配对比较"就完了。已就地补上限定语
（含 n=5 最小可得 p=0.0625 与密度扫描的结论指针）。现在 `[CLAIM_GATE] 引用配对表 3 处，全部带限定语`。

**这条门自己的判别式做了三次才做对，前两次的失败值得记**：
第一版摘掉 README 那行的尾部括号段，门不咬 —— 因为同行开头还有"描述性"三个字在充当限定语，
说明我的限定语集合里有**弱词**；第二版替换字符串写错、文件根本没被改，那次"通过"是空转；
第三版整段摘掉限定语才真的 `FAILED (failures=1)`，还原后 `OK`、`git diff --numstat README.md` = 1/1。
⇒ 教训：**给"文案约束"类门做变异，必须证明改动确实落到了盘上（比对 diff 行数），
并且限定语集合要挑到"删掉它语义就不成立"的程度，否则门只是在检查一个同义词是否存在。**

复算：`_citations --verify rc=0`（checked=78 anchored=74）、相关三个模块 `Ran 18 tests OK`。
VERSION 仍 1.0.0、无 remote、paper/ 未碰、对外产物未动。

### 2026-10-02：密度梯度扫了四档 —— 上一节那个"可判结论"被限定成"只在压力出现之后成立"

单点不能当结论，所以沿密度轴扫了四档（`experiments/presets/density_sweep.yaml`）：
常规 1.0 / 偏密 0.85 / 高密度 0.7 / 极密 0.5，每档 greedy+ga × 6 个共同 seed = 48 局，
跑在 `%TEMP%`（rc=0、未加 `--publish-latest`）。逐档配对（穷举 2⁶=64 置换精确双侧 p）：

| 档位 | 完成率 win/tie/loss（GA vs 贪心） | 精确 p | 判定 | GA 完成率均值 | 该档 <1.0 的局数 |
|---|---|---|---|---|---|
| 常规密度 1.0 | 0/5/1 | 1.0000 | 不可判（无差异） | 0.9972 | 1/12 |
| 偏密 0.85 | 0/5/1 | 1.0000 | 不可判 | 0.9972 | 1/12 |
| 高密度 0.7 | **0/0/6** | **0.0312** | **显著，GA 更差** | 0.9750 | 6/12 |
| 极密 0.5 | **0/0/6** | **0.0312** | **显著，GA 更差** | 0.9194 | 6/12 |

贪心在四档里完成率均值都是 1.0000(sd 0)。超时率方向相反但不显著：常规档 GA 略好
（0.0556 vs 0.0639），极密档 GA 明显差（0.2158 vs 0.1139）—— 逐档 p 未过 α。

**对外必须这么写，不多不少**：本项目**没有**任何一档出现"GA 显著优于贪心基线"；
存在一个压力阈值（本扫描落在 0.85 与 0.7 之间），越过它贪心基线的完成率**显著**更高。
低压力区两者打平不是"GA 也行"，是**这个指标在该场景没有区分度**（天花板效应，12 局里 11 局并列 1.0）。
边界要说清：n=6/档 ⇒ 最小可得 p=0.0312，α 若取 0.01 这两档就又不显著；压力轴只试了 interval_scale
这一种加压方式（任务规模、泊位数没扫）；两档显著是否同一机制未证。

工具侧两处补：`_paired_readout` 原先写死筛 `algorithm_comparison` 且只配 greedy/ga，
对这种"一块里塞多档"的扫描预设会**跨档混合配对**（那是假配对）⇒ 新增 `--value` 与 `--pair`。
第一版我用"运行时替换全局函数"实现筛选，当场把自己咬出 `UnboundLocalError` ⇒ 改成 analyse() 的参数。
复算：`python console/_paired_readout.py --dir <sweep 目录> --experiment task_density --value 高密度 --metric 完成率`。
VERSION 仍 1.0.0、无 remote、paper/ 未碰、`results/experiments/` 仍只有原来两批。

### 2026-10-02：高密度场景 + n=8 —— 项目第一次拿到一个统计上可判的方向性结论（方向对我们不利）

上一节的推论"缺的是场景区分度，不是重复次数"本轮被自己验证：**换成高密度后同一把尺子立刻显著**。

预设 `experiments/presets/ac8_density.yaml`：四算法 × seed 15101–15108（8 个共同 seed）、
`interval_scale: 0.7`、episode 3600。跑在 `%TEMP%`（rc=0、32/32 成功、未加 `--publish-latest`）。
**区分度证据**：32 局里 **23 局完成率 < 1.0**（min 0.90），而常规场景是 0/32 ⇒ 天花板确实压住了差异。

读数（`_paired_readout --experiment task_density`，配对贪心 vs 各候选）：

| 指标 | GA−贪心 逐 seed 差 | 精确双侧 p | PSO p | OR-Tools p |
|---|---|---|---|---|
| 完成率 | 全为负（−0.0167 ~ −0.05） | **0.0078 显著** | **0.0078 显著** | **0.0156 显著** |
| 超时率 | 有正有负 | 0.4453 | 0.5781 | 0.6094 |

贪心完成率 8/8 全是 1.0000(sd 0)，GA 均值 0.9708、PSO 0.9604、OR-Tools 0.9688。
⇒ **在高密度场景下，贪心基线的完成率显著高于三个元启发式/求解器基线**（α=0.05，穷举 256 置换的精确 p）。
这是本项目第一个可判的方向性结论，**方向对我们主推的 GA 不利**，必须照实说；
对外任何"GA 优于基线"的表述都不能引用这一批。超时率仍不显著（sd ≫ 效应）。
它是否推广到别的压力档位仍未验证（只有一个 interval_scale、seed 只有 8 个）。
**（这条已由下一节的四档扫描回答：不是普适 —— 常规与偏密两档两者打平，显著性只出现在 0.7 与 0.5。）**

途中三处自己的错都被当场抓住并修掉：① 第一版把 `values:` 写在 `algorithm_comparison` 下面 ——
runner 根本不读那条路，dry-run 印出来仍是"场景=default"才发现；② 改完留下两行互相矛盾的
`task_density.enabled`，`build_plan()` 返回空、抛"预设没有启用任何实验"；③ `_paired_readout`
写死了筛 `algorithm_comparison`，对真实数据报"算法两侧不齐"却不肯说为什么 ⇒ 加 `--experiment`
并把盘上真有的块名印进诊断。另外独立复算过一遍：用原始差值（不做方向翻转）走同一条穷举，
GA 那一格同样 0.0078，与工具一致。

复算命令：`python run_conclusion.py --preset ac8_density --output-root <临时目录>`
+ `python console/_paired_readout.py --dir <该目录> --experiment task_density --metric 完成率 --require-direction`。
边界：`results/experiments/` 仍只有原来两批，答辩数据源与 plots 15 件未动，`VERSION` 仍 `1.0.0`。

### 2026-10-02：加重复到 n=8 跑了一次 —— 设计问题解决了，但**光加 seed 不解决问题**

新增仓内预设 `experiments/presets/ac8.yaml`：与 `conclusion` 同 base（seed 起点 100、
`episode_steps: 3600`）、同四算法，只把 `algorithm_comparison.repeats` 从 5 提到 **8**；
四个敏感性块 `enabled: false`（不重跑）。dry-run 先核形状：`runs=32`、seed 集合 101–108
是结项那 5 个的**超集**。输出落 `%TEMP%/ac8_out/`（不进仓、不加 `--publish-latest`），
rc=0、32/32 成功、四算法各 8 seed 齐、`git_commit=9c609e6`。耗时合计 107.5 s（min/max 2.97/4.64）。

n=8 的读数（`console/_paired_readout.py --dir <该目录>`）：**最小可得 p 从 0.0625 降到 0.0078 ≤ α**
⇒ "这个实验设计给不出显著性"这条结构性障碍**确实被拆掉了**。但三条指标一条都没显著：

| 指标 | win/tie/loss | 精确双侧 p | greedy 均值±sd | ga 均值±sd |
|---|---|---|---|---|
| 超时率 | 1/4/3 | 0.2500 | 0.0542 ± 0.0194 | 0.0710 ± 0.0354 |
| 无人机利用率 | 3/0/5 | 0.4844 | — | — |
| 从生成到完成总时间平均 | 6/0/2 | 0.7891 | — | — |

**结论要按这个说法写**：α=0.05 下**不能**声称 GA 与 Greedy 有方向性差异；点估计上 greedy 更好
（超时率低 0.0168、时延低 0.674），但 sd 是均值的 1.8–50 倍 ⇒ **效应量小于噪声**。
"要判方向就加 seed"这句只对了一半 —— 加到 n=8 之后仍不显著，说明真正缺的是**区分度更高的场景**
（当前 60 任务/3600 步下四家完成率全是 1.0，天花板压住了差异），不是更多次同样的重复。
这条比"再加 3 个 seed"更值钱，也是这批数据第一次给出可判的设计。

顺手两处：`_paired_readout` 的 `--dir` 指仓外目录会崩（`relative_to(ROOT)`）已修；
新增 `--require-direction`，实测拼错指标 ⇒ rc=1、正常 ⇒ rc=0（防"少测一项还报全绿"）。

边界：`results/experiments/` 下只有原来两批，答辩数据源与 plots 的 15 个入库产物未动；
`VERSION` 仍 `1.0.0`、无 remote、paper/ 未碰。

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
**（本节末句已被上面那节 n=8 实测部分推翻：n=8 确实可判了，但仍不显著 —— 缺的是场景区分度，不是重复次数。）**

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
