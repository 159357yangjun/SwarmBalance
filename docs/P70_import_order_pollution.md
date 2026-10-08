# #70-P1：g2_all_four 聚合红的污染源定位（三方形链，非两方）

基线 `5fc4471`。上位裁定的顺序里第③刀。**先前两处误判先更正**（都记下来防复活）：
- #69-H_terminal.md 与 CHANGELOG 第二十一~二十六笔写的是「r2 + speed_gate **两模块配对**造成污染」⇒ 方向对、机制错；
- 本轮一度改口"r2 不 import 重模块 ⇒ 是第三方"⇒ 也错（我只 grep 了文件头 40 行的 `^import`，漏了函数体内的 import）。

## 真实链条（每步都有行号与实测读数）

| 步 | 位置 | 发生了什么 |
|---|---|---|
| 1 | `console/test_r2_destination_without_load.py:30` | `setUpClass` 把 `SWARM_BALANCE_SIM_CONFIG` 指向**出厂 config**（10 机 / fleet 5-3-2），且**全文件无 tearDownClass、不还原** |
| 2 | `console/test_r2_destination_without_load.py:34` | 紧接着一句 `from environment import Environment` —— **首次 import environment 发生在这一行**（由 `builtins.__import__` 拦截打栈实证，栈顶即 r2:34 in setUpClass） |
| 3 | `frontend/environment.py:87 / :105 / :100` | 模块级冻结：`CFG = get_shared_config()`、`DEFAULT_NUM_DRONES = int(ENV_CFG.get("num_drones", 3))`、`FLEET_MIX = HETERO_CFG["fleet_mix"]` ⇒ 此刻被钉成 **10 / {5,3,2}** |
| 4 | `console/test_speed_fallback_gate.py:146`（`_install_gate_config()` 于 import 期调用） | 门把自己的重载配置（6 机 / fleet 3-2-1 / 240 任务）写进临时文件并 setenv。**但 environment 已在步 3 冻结，换 env 无效** |
| 5 | 结果 | 门拿到 10 机轻载 ⇒ PSO `pending_buffer` 峰 = 2 < 阈值 15 ⇒ `_maybe_flush_buffer` 的 size 触发口不开、optimize 零调用 ⇒ `test_g2_all_four` 报 `[pso][NO_DENOMINATOR]`（test_speed_fallback_gate.py:251） |

关键证据（同进程实测，非推理）：
```
step1 after r2 ran        : env=factory
step2 import env_incidents : environment frozen DEFAULT_NUM_DRONES=10 FLEET_MIX={'light_express':5,'standard_cargo':3,'heavy_cargo':2}
step3 import speed_gate    : env now points to=<tmp>/speedgate_xxx/sim.json     ← 门确实换了 env
step4 environment constants STILL frozen at DEFAULT_NUM_DRONES=10               ← 但常量已冻，换晚了
```
⇒ 单跑 speed_gate 时没有人在它之前 import environment，它自己 import 前已 setenv ⇒ 绿；聚合按字母序 r2(:34) 先到 ⇒ 红。**这就是"同一文件 standalone 绿、聚合红"的全部机制**。

## 为什么这是测试隔离缺陷而不是被测对象缺陷
`speed_gate` 依赖"我在 import 期抢在所有人之前 setenv"这个隐含前提；而 discover 的字母序不保证这一点。任何后来新增的、字母序在 s 之前的模块只要 import environment，都会静默废掉这个门的重载配置——与被测算法无关。

## 第二个污染源（本轮由 G1 变红实测出来，先前结论被推翻）
上面那条链**只解释了 G2**。全量复跑时 `test_g1` 反而报 `[GATE_FROZEN_BY_FOREIGN_IMPORT]`（读数 10/{5,3,2}），
而 r2 那时已经改成按路径加载 ⇒ 说明还有更早的 importer。判别式实测（拦截 `builtins.__import__`、
按 discover 顺序逐模块加载并打印首次命中的栈）：

```
[FIRST environment]
    ... console/sim_session.py:43, in <module>      ← import environment as _env_module
>>> first import happened while loading: console.test_server_guards
```

⇒ **真正的第一个 importer 是生产代码 `console/sim_session.py:43`**，它被
`console/test_server_guards.py:22`（`import console.server` → server → sim_session）在主进程里拉进来，
时序上早于 swap_time_gate / speed_gate。那份名字绑定是 reload 语义所需（`sim_session.py:48` 起
明写"顶层只 import 模块…便于 rebuild 时刷新到 reload 后的新类"），**不该由测试去改**。

由此推翻我自己先前提出的方案："在主进程内核对机队规模、不符就具名 bail"两条挂载点都不成立——
放 setUpClass 会把已免疫顺序的 G2 判死；放用例体内则对着一个合法的生产名字绑定喊狼。
最终做法改为：**需要内核的门自己按路径加载一份，并在加载那一刻核对配置指纹**
（`test_speed_fallback_gate._pf_kernel()`，短码 `[GATE_CONFIG_NOT_APPLIED]`），
使"校验对象"与"消费对象"是同一份模块 ⇒ 与谁先 import 无关。
实测判别式：`server_guards + swap_time_gate + g1` 连跑 52 tests OK，`[G1] … 取值集合=[14.0, 20.0]`
（单跑同值）；P2 白名单因此可归零（基线=空表）。

## 第三次实测驳回：光"按路径加载"还不够，环境变量本身会被改走
上一条修完再跑全量，G1 **仍然红**：`[GATE_CONFIG_NOT_APPLIED] DEFAULT_NUM_DRONES=10 FLEET_MIX={5,3,2}`。
⇒ 说明本门那份重载配置在 G1 取内核时已经不生效了。根因不是 import，而是**环境变量**：
`_install_gate_config()` 原先只在**模块顶层**调一次（`_INSTALLED = ...`），而 discover 里字母序在
speed_gate 之后的 `console/test_swap_time_gate.py:63`（以及 `test_sla_consumption_gate.py:68`）
会把 `SWARM_BALANCE_SIM_CONFIG` 指到自己的临时配置上 ⇒ 我 import 时装的那份早被人顶掉了。

修法（本轮定稿）：`_pf_kernel()` 每次取内核前**重装配置**，把「装配置 → 按路径 exec 内核 →
核对该内核的常量指纹」绑成一个不可拆的动作。这样无论别人怎么改 env、谁先 import，
本门消费的那份模块一定是照本门配置冻结出来的。
判别式两面实测：
```
sla_consumption_gate + g1        → Ran 10 tests OK   [G1] greedy 采样 43200 次 speed=[14.0, 20.0]
r2_destination_without_load + g1 → Ran  5 tests OK   [G1] greedy 采样 28824 次 speed=[14.0, 20.0]
单跑 g1                          → Ran  1 test  OK   [G1] greedy 采样 43200 次 speed=[14.0, 20.0]
```
⚠ 诚实标注：`43200` vs `28824` 这个**采样次数**随前序模块是否已把 `task_generation` 相关配置
改走过而不同（observation 步数不同），它不是本门的判据、也不该被当成判据——
G1 断言的是"取值集合落在机型包络内且无 200"，三面均为 `[14.0, 20.0]`。
若将来要把次数也钉成判据，得先让它对配置注入时序不敏感，否则又是一扇顺序相关的门。

## 残留普查门（console/test_p3_no_cross_test_residue.py）实测到的另外四处
建门时按"真跑完每个模块再 diff 全局态"逐个点名，除 r2 外又抓到四处改了不还原的，本轮一并补上：
`test_c1_destination_leg_semantics`（setUpClass 加记账 + 新增 tearDownClass）、
`test_c4_is_carrying_discriminator`（同上）、`test_h_r7_delivery_detection`（它在**用例体内** setenv ⇒ 用 setUp/tearDown 成对切换）。
复算命令：`python -m unittest console.test_p3_no_cross_test_residue` ⇒
`[P3_CLEAN] 5 个模块全程跑完后残留=0` / `[P3_TEETH] 注入生效…` / `[P3_WITNESS] 正例证人通过…`。

### sys.modules 这一面被实测驳回后撤掉了（别照抄判据③原文的五类清单）
判据③原文列了"全局配置 / 模块缓存 / 注册表单例 / 随机状态 / 环境变量"五类。实测下来
`sys.modules` **不能当残留判据**：任何一次真运行都会把 `drone / task / route_planner /
charging_station / config.config_loder …` 正常导进来（第一版读数就是这 12 个名字），
那是运行的副作用不是"改了没还原"；拿它当判据 ⇒ 门永远红、只能靠放宽条目来过活。
⇒ 该面从运行时判据里撤掉，改由 `console/test_p2_no_name_based_kernel_import.py` 从**源码结构**侧守
（测试不许按名字 import 内核），不需要在运行时再猜一次。随机状态与注册表单例**未测**，
因为本轮没实测到"确有模块改了它且不还原"——没有这种样本就明写"无人证得过"，不写都会绿的门。




## 门自己没跑起来时，报红还是静默？（补条：半坏自检实验）
问题不是"门会不会漏检"，而是"量具崩了的时候它给的是哪种信号"。实测做法：把三扇门在**缺依赖的解释器**
（`Python310/python.exe`，实测无 shapely/fastapi）下各跑一次，与清洁树+venv 那轮并列，原始输出全部落盘在
`docs/取证输出/p70_p1/`（A_* = 坏解释器，B_* = 清洁面，`C_gate_did_not_boot_answer.md` = 对照表与结论）。

**答：三扇都报非零退码，没有一扇静默。** 但两条红是误导性的，本轮据此改了门的形状：
1. **P2 的红起初是自我误伤**：门自己的 `print("…⇒…")` 在 GBK 控制台抛 `UnicodeEncodeError`，
   把 test_A/test_B 双双炸成 ERROR —— 而违规其实是 0。既不是抓到污染也不是通过 ⇒ 典型半坏自检。
   ⇒ 每条门**先**印一行纯 ASCII 证人 `[P*_VERDICT] k=v … exit_criterion=…`，再印中文说明行；
   顺序承重（证人必须在可能被编码异常打断的那条 print 之前）。现在坏解释器的日志里也留有
   `[P2_VERDICT] violations=0` ⇒ 人能分清"量具崩了但判定值是 X"与"根本没到判定这步"。
2. **P3 在坏解释器下的那条红成因不对**：残留项是被测模块 import 失败、setUpClass 半途而废留下的
   env 改动，不是本门要守的"改了全局态不还原"。⇒ 判据写成 `residue_items==0 AND run_errors==0`，
   `run_errors` 非空即 `[P3_BLIND]` 整轮作废；读不到 `RESIDUE_JSON` 同样退 1。
   **共同点：读不到读数 = 红，不是绿。**

## 修复（本笔实施，五条）

1. **让 speed_gate 不再依赖 import 竞速**：`test_g2_all_four` 改为**每个算法各起一个干净子进程**跑完整真路径（子进程自己写重载配置、在 import environment **之前** setenv），主进程常量从此不参与该门的判定。判别式由**子进程自报** `num_drones==6` + `config.drone.speed != 200` 承担（短码 `[GATE_FROZEN_BY_FOREIGN_IMPORT]`）。
   ⚠ 先前写的"在主进程内校验机队规模、不符就具名 bail"这条方案已被后续两轮实测**整体驳回**（见上面 §第二个污染源 与 §第三次实测驳回），不要再照这段实施。
2. **消除"谁先 import / 谁后改 env"这件事本身**：把主进程内按名字加载内核的测试模块统一改成走 `console/_preflight.py:load_kernel_environment()`（按文件路径 exec、不进 `sys.modules["environment"]`、用完还原 sys.path）。本轮迁移 9 个模块（清单见 §残留普查门 与 CHANGELOG 第三十笔）；需要重载配置的 `test_speed_fallback_gate._pf_kernel()` 则把「装配置 → 按路径加载 → 核对该内核常量」绑成一个动作。
   仍留在主进程按名字 import 的只有两类且都是结构上必须的：生产代码 `console/sim_session.py:43`（reload 语义依赖名字绑定，不在测试侧改动范围）与 `console/test_command_console.py`（刻意装桩、自带 `tearDownModule` 复原 ⇒ 由 P2 门的 test_C 单独管"装了必须有复原路径"）。
3. **残留记账还原**（判据③）：给改了全局态却不还原的模块补成对切换 —— r2 / c1_destination_leg / c4_is_carrying 用 `setUpClass`+`tearDownClass`，h_r7 在用例体内 setenv ⇒ 用 `setUp`/`tearDown`。由常驻门 `console/test_p3_no_cross_test_residue.py` 守（两面 + 正例证人）。
4. **order-independence 回归门**（`console/test_p1_order_independence_gate.py`，两面）：GREEN = 两种显式相反顺序（r2→G2 / G2→r2）各跑 fresh process，双双 rc=0 **且** `[G2/pso] optimize` 读数逐字相同（只断"都通过"不够——读数漂移也是顺序相关）；RED = 注入一个已知污染样本（复刻修复前 r2 的形状），断言它确实把 `DEFAULT_NUM_DRONES` 冻成出厂 10 ⇒ 证明这条全局态通道仍然真实存在、这扇门不是在守一件已经不存在的事；注入无效果则报 `[P1_INJECT_NO_EFFECT]` 而不是默默绿。
5. **结构门防复发**（`console/test_p2_no_name_based_kernel_import.py`）：扫 `console/test_*.py` 里主进程按名字加载内核的语句，判据=命中 0、豁免须在册且带理由、并同时核"条目还在/已消失"；基线白名单为**空表**。牙由三面证：负例被抓 / raw-string 子进程脚本不误伤 / 普通字符串单列待确认，另加一次真实变异（把某模块 loader 换回按名字 import）当场变红。
