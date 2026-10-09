<div align="center">

# SwarmBalance · 群智优衡

**异构无人机集群三维协同调度仿真平台**

[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](README.md)
[![Algorithms](https://img.shields.io/badge/algorithms-4%20families-orange.svg)](README.md)

面向城市低空物流配送场景，构建**任务生成 → 调度决策 → 飞行仿真 → 指标评估 → 可视化**的完整闭环，
在同一物理口径下横向对比四类调度方法。

**当前进度（2026-10-08）**：Phase 0（真实性审计与算法有效性）+ Phase 1A（RoutePlanner 抽离）+
Phase 1B-0/1B-1/1B-2 已闭合；#69 生命周期一致性、#70-P1 测试隔离、#70 阶段② g2teeth 重标定亦已闭合。
防"重新引入全局污染 / 结果依赖发现顺序"的常驻门共四扇：P1（G2 消费路径两向对撞）、
P2（源码结构：测试不许按名字 import 内核）、P3（运行时残留 diff + 覆盖集恒等式）、
P4（子集逐用例状态集合两向对撞，单成员进程构造）。判据与残余边界见
`docs/P70_which_gate_is_the_resident_one.md`、`docs/P70_import_order_pollution.md`。
另有一扇守**冻结实验产物溯源**的门 `console/test_frozen_artifact_source_pins.py`：凡被代码/文档引用到的
`results/experiments/<目录>` 都要核对 `core_source_sha256` 与盘上是否一致 —— 不一致且 CHANGELOG 里没有
**带该目录名**的过期声明就红；有声明则降级为信息并印出是哪一条（本轮把"字段一直在、只是没人比"的侥幸变成常驻）。
套件真值以 `python console/_readme_counts.py --verify` **现算**为准：console **53 文件 / 373 用例**、
experiments 3 文件 / 32 用例、frontend 2 文件 / 19 用例、仓库根窄模式 `test_build*.py` 1 文件 / 3 用例。
（下面那句"286 例"是 2026-10-05 的旧快照，留着是为了不假装它没写过；
从 #70-P1 起一律按 `_readme_counts.py` 报数，别手抄。）
调度层两项增强**默认全部关闭** ⇒ 生产行为与基线一致。下一步是 1B-3（续航可行性）与 1C（状态机单一真源）。
诚实边界见 [§已知局限](#️-已知局限) 与总纲 §3、§17。

</div>

---

## ✨ 核心特性

| 特性 | 说明 |
|---|---|
| **四类算法统一评测** | Greedy / PSO / GA / OR-Tools(CP-SAT)，共享同一仿真环境与指标口径 |
| **异构机队** | 轻载·标准·重载三种机型，参数取自美团、顺丰丰翼、大疆公开产品规格 |
| **任务链调度** | GA 采用**排列编码 + 贪婪分割解码**，输出每机一条有序任务链 |
| **顺路接入** | 在途无人机按绕行半径 / 载重 / 电量 / 时间窗约束，把下一单直接挂到当前航线 |
| **禁飞区约束** | 支持圆形与多边形禁飞区（含安全余量），接入 A\* 路径规划实现真绕飞 |
| **机巢地面资源** | 有限泊位 + 动态优先级仲裁（电量紧迫度 + 等待时长 + 任务紧迫度），整组换电 180 秒 |
| **Web 控制台可视化** | 浏览器端 2D/3D 指挥台（FastAPI + Vue3 + Three.js），服务端全程无头 |
| **运行中交互调度** | 播放 / 暂停 / 单步 / 1x·2x·5x·10x，支持在当前状态中人工注入普通、重货、紧急任务 |
| **调度过程可解释** | Web“调度”页实时展示无人机任务链、机巢泊位队列、动态优先级和调度事件日志 |
| **可点击调度指挥台** | 2D / 3D 地图可直接点无人机、任务、机巢查看实时详情；待调度任务可查看候选无人机能力匹配、ETA 与约束解释 |
| **运行时场景事件** | 可模拟无人机故障停飞 / 恢复、机巢临时关闭 / 重开；未完成任务自动回收，补能请求自动改道，并继续由当前算法滚动重调度 |
| **场景布局编辑** | Web 端可直接增删/移动机巢、修改泊位，并用 2D 地图新增/移动圆形禁飞区；保存后安全热重建，失败自动回滚 |
| **运行时运营控制** | 可暂停/恢复自动订单流、动态修改待调度任务优先级/SLA/重量/类别，并人工调无人机前往开放机巢补能 |
| **一键答辩演示场景** | 内置应急医疗、机巢拥堵、故障韧性、标准综合四套可复现场景，固定算法/Seed，并提供“下一幕”真实控制剧本 |
| **运行态快照** | 当前服务内可保存/恢复完整动态节点（无人机/机巢/任务/调度缓存/随机数状态/事件/轨迹/趋势），便于从同一节点重复答辩演示 |
| **实时态势与趋势** | 服务端记录完成率、超时率、机队利用率、待调度数量历史，并汇总紧急积压、资源故障与低电风险 |
| **可持久化场景库** | 保存“初始配置 + 算法 + Seed + 可选算法超参”，支持 JSON 导入/导出；与运行态快照分工明确，便于答辩和实验复现 |
| **启动预检与操作引导** | 启动前检查 Python、关键依赖和配置一致性；Web 首次进入提供操作流程，态势页根据异常状态给出下一步建议 |
| **科研结果可复现** | 正式批量实验自动保存原始 Seed 级结果、均值/标准差/中位数、GA↔Greedy 同 Seed 描述性配对表和 `reproducibility.json` 环境清单 |
| **一键结项归档** | `finalize_project.bat` 串联严格发布检查 → 标准结项实验 → 生成带 SHA-256 的结项证据包，Web 实验页也可下载最新正式证据包 |
| **真实数据接入** | 随机 / CSV / GeoJSON / 企业 REST 网关四种数据源，可插拔 |

---

## 🚀 快速开始

### 环境要求

> ⚠️ **必须使用 Python 3.10**。`osmnx==1.9.4` 声明 `Requires-Python <3.13`，实测 3.11/3.12 会出现
> geopandas 组合问题，3.13 直接装不上。推荐 3.10.11。

```bash
git clone https://gitee.com/acgvgh/swarm-balance.git
cd swarm-balance

# 1) 创建虚拟环境
python -m venv .venv310
source .venv310/bin/activate          # Windows: .venv310\Scripts\activate

# 2) pip 固定到 23.x（pip 26.2.x 在 Windows 有 safe-delete bug，会卡死甚至损坏 pip）
python -m pip install "pip==23.3.2"

# 3) 先钉 numpy，再装其余（顺序不能反！）
pip install numpy==1.26.4
pip install -r requirements.txt
```

> **为什么必须先装 numpy？** `ortools` 会把 numpy 升到 2.x，而 `osmnx==1.9.4` 要求 `numpy<1.27`，
> 升级后 osmnx 会报 `numpy._utils` 错误、甚至被连带卸载 geopandas。

### 跑一次评测

```bash
cd frontend
python evaluate_metrics.py --policy ga --episodes 1 --episode-steps 600 --seed 100
```

> **这条命令会写入哪里**：默认只写 `results/adhoc/frontend_ga_metrics.csv`（一行均值），
> 该目录已在 `.gitignore` 里，**跑完 `git status --porcelain` 仍为空**。
> 想改道到别处用 `--output ../results/adhoc/ga.csv`；
> 确实要刷新「算法对比」页的入库数据源时，必须显式加 `--record-into-evidence`，
> 那会**追加一行到已入库的** `results/compare/<该算法>.csv` 并弄脏工作区。
> **解释器不对时的退出码**：`evaluate_metrics.py` 缺依赖会打印一句人话（缺哪个包 +
> 项目正式解释器的绝对路径 + 同一条命令的重跑写法）并以 **退出码 3** 结束，不再抛
> `ModuleNotFoundError` 的满屏栈；`python -m console.run` 与 `python -m console.selfcheck`
> 走各自的前置检查，退出码是 2。CI 与文档自检据此把「环境不够」与「仿真跑挂了」分开。
> 默认值过去是直接写 `results/compare/`，评审照本节跑一次就出现
> `M results/compare/backend_ga_metrics.csv`（实测 7 行 → 8 行），故改为显式开关。

输出示例（2026-09-29 在当前代码下实测；数值来自本机一次运行，非人工整理）：

```
Episode 1 (seed=101): 完成率=0.7667, 超时率=0.0435, 平均时延=0.4565,
完成=23/30, 利用率=0.705, 空载率=0.498, 顺路接入=5, 禁飞绕飞=7
```

> 示例里 `利用率=0.705 / 空载率=0.498` 是同一份数据的 **`.3f` 显示值**，程序末尾的
> Mean Metrics 用 `.4f` 打的是 `0.7045 / 0.4984` —— 差值来自显示位数，不是另一次运行。
> 同命令连跑 5 次的逐位一致性见 [`docs/数据来源与可追溯性登记表.md`](docs/数据来源与可追溯性登记表.md) 的确定性小节，
> 那里给的是实测方差而不是"应该是四舍五入"。

### 打开可视化

```bash
# 浏览器控制台（唯一的可视化入口）
# Windows 推荐：双击 start_console.bat（自动预检并打开浏览器）
python -m console.run          # 其它平台同样可用，默认自动打开浏览器
```

> **停止控制台**：在运行它的终端按 `Ctrl+C`；Windows 也可双击 `stop_console.bat`，
> 它会清理所有 `console.run` 进程并释放 8765 端口。`start_console*.bat` 在启动前会清理
> **命令行含 `console.run` 的 Python 进程**（本项目自己的残留实例）；若 8765 被别的程序
> 占用，它只会提示而不会替你终止对方，此时请用 `--port` 换一个端口。

### 答辩应急：便携 Web 模式

正式实验仍建议使用上面的 Python 3.10 完整环境。如果答辩机临时缺少 OSMnx / OR-Tools，可以使用：

```bash
python -m console.run --portable
```

Windows 直接双击 `start_console_portable.bat`。此模式会使用项目自带 `part_of_yangpu.osm` 的离线 XML 回退解析器；缺少 OR-Tools 时界面会把该算法标记为不可用，Greedy / GA / PSO 与浏览器指挥台仍可运行。**便携模式用于演示兜底，不用于最终论文实验数据。**

发布/答辩前可以先运行真实主链路自检：

> ⚠️ **先激活 `.venv310`，否则有一部分用例不可跑。**
> 用系统 `python`（例如 Anaconda 3.13）直接跑会缺 `shapely / fastapi / uvicorn / osmnx / ortools`。
> 现在这类情况**不再报 traceback** —— 以前会报 `ModuleNotFoundError`，以及一个
> `AttributeError: module 'environment' has no attribute 'DEFAULT_EPISODE_MAX_STEPS'`
> （后者是被别的测试装的 `environment` 桩顶掉了：名字对了但不是那个文件，
> 看起来像仿真坏了，其实只是解释器不对）。缺依赖时相关测试整体 skip，
> 原因里会打印**该用的解释器绝对路径**与可直接粘贴的重跑命令。
>
> 不确定环境就先跑 `python console/_preflight.py`，它会列出缺哪些包与该用哪个解释器。
>
> **skip 不算通过。** `OK (skipped=12)` 这种尾行很容易被读成"过了 12 条"，
> 所以 `python console/_preflight.py --skips`（`release_check.py` 的控制台测试步骤也会自动打印）
> 会把每条 skip 归因成 **缺哪个包 → 哪个测试模块 → 几条不可跑**。
> 数字直接取自 `unittest` 结果对象的 `skipped` 列表，不是手工维护的"哪个用例要哪个包"对照表
> （那种表一定过期，本仓已被手抄计数咬过两次）。
>
> 本 README 里所有"N 个文件 / M 个用例"都**不是手抄的**：由
> `python console/_readme_counts.py --verify` 每次真 discover 一遍核对，不一致退出码 1
> （`console/test_readme_counts.py` 把同一段判据接进 discover，所以漂了会让测试红）。
> 测量固定用项目 venv 解释器起子进程跑，**换解释器不会得到不同的数**；
> 找不到 `.venv310` 时直接报错，不会退化成"用当前解释器凑一个数"。
> **改了测试就跑 `python console/_readme_counts.py --fix`** —— 它是这两处数字的唯一写入者，
> 别手改；它按字节读写、只动数字不动行尾，README 已是实测值时是零改动（有测试钉着这点）。
> 这里刻意不写"系统 python 下你会看到 Ran X tests"，
> 因为那个数取决于读者机器上缺哪些包 —— 写死它就是一个必然过期、又没人核对的手抄值。
>
> 登记表/README 里的 `路径:行号` 引用由 `console/_citations.py` 核对（同一份判据也接进 discover）。
> 光判"文件存在 + 行号不越界"是**半盲**的：行号漂到范围内另一处时它照样绿。
> 所以代码事实类引用要写成 `config/simulation.json:89#carrying_capacity` ——
> 锚点是被引行必须含的一段字，改了代码位置而忘了改引用就会红。
> 引用已删除的文件时按约定写 `path:line 已移除@<sha>` 并附 `git show <sha>^:<path>` 取回命令。
> **引用「作废产物」必须声明行集合**：被标作废的目录（判定=目录里有写着「作废」的
> `README.md`，不写死名单，写死的清单会过期）里的 `.csv`/`.png` 被引用时，紧跟其后写
> `行集=core4`（只取 4 个核心算法）或 `行集=all10`（含 6 个已撤除）。为什么值得这么严：
> 同一列在两种行集合下能差出 0.24（`Weighted Overall Score` 0.833768 vs 0.588907，
> 全表见 `results/compare/plots/ROW_SETS.md`，由 `python results/row_set_delta.py --write`
> 生成、`--verify` 不一致退出码 1），且混进来的是六个较弱变体、方向是拉低。
> 声明 `all10` 还要与表里实际算法集合相符 —— 表重生成后标注自己会红（双向）。
> 汇总行会印「扫到几条 / 其中几条带锚点」：没带锚点的只判越界，别把这条门当成全覆盖。
> 两种历史标注**紧跟在它描述的那条引用后面**（一行里两条引用时各管各的，不整行共享）：
> `path:line 已移除@<sha>` 表示文件在该提交被删，`path:line#锚点 已失效@<sha>` 表示文件还在、
> 但引的是那次修复**之前**的行号 —— 两者都按 `git show <sha>^:<path>` 取正文核对，
> 且 `已失效@` 必须带锚点：历史行号没法跟磁盘比，只有锚点能证明它当时真的对过。
>
> **同一把尺子伸进 `paper/`，但只报不改。** `console/_paperscan.py` 扫 `main.tex` 与
> `paper/figure/*`，产出 `docs/论文侧撤除未达清单.md`（`--paper-report --write` 生成、
> `--paper-report --verify` 不一致退出码 1，并已接进上面那条 `--verify` 总门）。
> 清单**按语义分两类**：结果表行/图注/正文里的"我们评了这六个"＝待作者定夺，
> 「相关工作」叙述与 `\cite`/`\bibitem` 引用键＝合法、**不当缺陷报**。
> 分类本身就是判据的一半：混成一锅报，下一轮为了变绿就会去删真的相关工作引用，
> 那是比重复数字更坏的修法 —— 所以 `console/test_paper_void_scan.py` 双向钉：
> 待夺类漏报要红，合法类误报也要红。删哪几行、改成什么口径是**作者权决定**，
> 这道门只核「清单还是不是代码现在算出来的那一份」，不自动改 `paper/` 任何文件。
> 清单里那句"撤除从未到达论文"也是算出来的：`6b8c4c8` 动过 `paper/` 的文件数 = 0，
> `main.tex` 最后一次入库改动停在 `4d8ac93`，10 张图最后一次改动全部早于该撤除
> （图的**像素内容未单独核验**，位图读不出列，能核的只有入库批次）。
>
> **门报红的每一行都以 ASCII 短码开头**（`[FAIL][ANCHOR_MISS] 文档:行 … | fix: …`，中文解释跟在
> 后面）。原因实测过：这台机的通道是 GBK 系，中文会被换成 `??????` —— **只有中文诊断的红等于
> 没有门**。短码与 `_citations.py` 头部那张表的互印、以及"整行按 ASCII 有损编码后短码/文件:行/
> `| fix:` 仍在"都由 `console/test_gate_ascii_diagnostics.py` 钉住。断言一律打在短码上而不是
> 中文措辞上（`assertIn("找不到", …)` 那种写法，文案一改判据就假红 —— 与 `env_shortfall`
> 那一轮"判据寄生在报错文案上"是同一个错）。
>
> **非 raw 字符串里的非法转义**（`"\cite"` 那一类，被 import 就喷一行噪声）有常驻门：
> `console/test_source_escape_sequences.py` 逐文件 `compile()` 并强制 `simplefilter("always")`，
> 带范围下限（下限 80，实测条数**不写在文档里**，只印在行上）、两面夹具（植一条必红、当前仓必绿），
> 普查数印在行上（`[ESCAPE_CENSUS] py_files=… hits=…`）。为什么不用 `-W error` 当证据、
> 以及为什么不能按警告类别过滤（3.10 抛 `DeprecationWarning`、3.12+ 才升成 `SyntaxWarning`），
> 实测表写在那个文件的模块注释里。
>
> **别用 `cp -p`（或任何保留 mtime 的拷贝/还原）往这棵树里写 `.py`。**
> CPython 默认按「源文件 mtime + size」判定 `.pyc` 是否过期：内容改了而 mtime 被按回旧值、
> 长度又没变，旧的字节码就"仍然相符"，import 跑的是**盘上已经不存在的代码**，
> 用例数与 `OK` 都是在测缓存。本机真实踩过一次（系统 python 报 7 个错、栈里那一行在当前
> 源文件里 grep 命中 0 次），`console/test_stale_bytecode.py` 把这一类复现并防住：
> 计数、skip 归因、发布检查的子进程统一走 `console/_preflight.py:isolated_env()`，
> 纪律分两半，少一半都不算：
> - **子进程**：`console/_preflight.py:isolated_env()` —— 计数、skip 归因、发布检查起的
>   子进程都走它；
> - **同进程**：每个入口脚本（`release_check.py`、`verify_data_provenance.py`、
>   `console/_preflight.py`、`console/_citations.py`、`console/_readme_counts.py`、
>   `results/compare_gate.py`、`results/plot_compare_metrics.py`）在任何本仓 import **之前**
>   自己设两行裸赋值 —— 这条抽不成公共函数，因为"调函数"本身就得先 import，
>   而那次 import 就可能已经吃到过期缓存。
> 缓存前缀取系统临时目录下**每次运行唯一**的子目录：读必 miss，又不会把仓库弄脏
> （前缀指在仓库里时，`release_check` 第一步的 `compileall` 在树里长出 77 个 `.pyc`，
> git 都被 "Filename too long" 噎住 —— 这坑是我自己踩的，之后由
> `console/test_stale_bytecode.py` 逐条钉住）。`python release_check.py` 现在印一行
> 「字节码纪律（跑绿的前提）」，值是从子进程里问出来的（`sys.dont_write_bytecode` /
> `sys.pycache_prefix`），不是看启动命令里写了什么。
> 反过来一句话：**任何"跑绿了"的证据，只要没声明字节码纪律，就只算未验证。**

```bash
python console/_preflight.py        # 依赖预检：缺包时直接说清缺哪些、用哪个解释器
python console/_citations.py --verify   # 文档引用门禁：行号越界 / 锚点找不到都退出码 1
python console/_citations.py --paper-report --write   # 论文侧「撤除未达」具名清单（只报不改）
python console/_suite_ab.py --capture /tmp/ab && python console/_suite_ab.py --compare /tmp/ab
#   ^ 换了"套件输出怎么采集"之后逐行对账：改前那条命令 vs 现在的采集器，
#     两侧同尺比可比单元，only_before 必须为 0（`--ablate` 演示这把尺子会咬）
python -m console.selfcheck
python release_check.py             # 普通发布检查
python release_check.py --strict    # Python 3.10 正式环境最终检查

# 配对实验"能不能下结论"的判读（只进报告行，默认不影响退出码）：
#   印逐 seed 差值、精确置换 p、以及**这组重复次数在数学上能达到的最小 p**。
#   结项预设每算法 5 个 seed ⇒ 双侧符号检验最小可得 p = 0.0625 > α=0.05，
#   所以 `paired_ga_vs_greedy.csv` 的胜/平/负列在任何数据下都不构成显著性结论。
python console/_paired_readout.py --metric 超时率 --metric 无人机利用率

# 配置哑键门禁（改了不起作用的键）—— 已并入 console 测试，随 discover 自动执行：
python -m unittest discover -s console -p "test_*.py"
python -m unittest console.test_config_keys_coverage -v   # 或单独跑这一项

# ⚠ frontend/ 里另有 2 个文件 / 19 个用例**不在上面那条命令内**：`frontend/` 没有 `__init__.py`，
#   以仓库根为顶层时 discover 直接抛 "Start directory is not importable"（本轮实测）。必须显式给顶层：
python -m unittest discover -s frontend -t frontend -p "test_*.py"   # E1 风能耗两把门；其中等价门当前为红

# ⚠ 仓库根还有 1 个文件 / 3 个用例（守对外交付物完整性），复算只能用**窄模式**：
python -m unittest discover -s . -t . -p "test_build*.py"
#   根下若用宽模式 `test_*.py`，console/ 与 experiments/ 两个包会被递归吃进来 ⇒ 实测 1 文件 / 408 用例
#   （373+32+3 双计）。这个 408 不许出现在任何分母里。

# 数据来源可追溯性 + 环境基线漂移门禁（默认阻断，退出码非零）：
python verify_data_provenance.py
python verify_data_provenance.py --mapfile       # 只核输入地图的内容哈希是否就是被钉住那份
python verify_data_provenance.py --write-mapfile-baseline   # 重新钉：只在确认盘上这份就是归档那份时用
python verify_data_provenance.py --allow-loader-drift     # 确认接受当前环境时才加
```

详细说明见 [`离线便携与端到端自检.md`](docs/离线便携与端到端自检.md)。

### v1.0 最终结项流水线

在**正式 Python 3.10 完整环境**中，Windows 可以直接执行：

```bat
finalize_project.bat
```

它会依次执行：

1. `python release_check.py --strict`：要求正式依赖与真实主链路全部通过；
2. `python run_conclusion.py --preset conclusion`：执行标准结项实验；
3. `python build_conclusion_package.py`：把最新正式实验、配置、复现清单、关键文档与校验和打成证据包。

标准实验除了原有 `algorithm_comparison.csv` 和敏感性分析 CSV，还会生成：

- `algorithm_comparison_stats.csv`：关键指标的均值、样本标准差和中位数；
- `paired_ga_vs_greedy.csv`：同一 Seed 下 GA 与 Greedy 的描述性配对比较，**不代表统计显著性**（n=5 时双侧符号检验最小可得 p=0.0625 > α=0.05，设计上就给不出显著性；复算见 `console/_paired_readout.py`）；
- `reproducibility.json`：Python/平台/关键包版本、输入配置/OSM 哈希、算法列表等复现信息；
- `summary.md`：明确写出结果解释边界，不把描述性差异表述成统计显著性。

> 若正式结果不支持“GA 在某个指标上更优”，结项报告应如实呈现。项目目标是验证联合调度方法，而不是为了符合预设结论而修改实验口径。

最终验收门槛见 [`结项最终验收清单.md`](docs/结项最终验收清单.md)。

### Web 控制台推荐交互流程

Web 控制台不是“只跑一次结果”的算法跑分页面，而是自由仿真入口：

1. 选择算法和 Seed，点“重置”；
2. 用“播放 / 暂停 / 单步 / 1x·2x·5x·10x”推进当前仿真；
3. 点“＋ 新任务”可在**当前运行状态**中加入任务，既可随机生成合法起终点，也可在 2D 地图上依次点击起点和终点；
4. 在 2D / 3D 地图上直接点击无人机、任务或机巢，打开“调度指挥台”详情；待调度任务会显示候选无人机的能力匹配分、ETA、载重/电量/时限约束解释；
5. 切到“调度”页查看按时限排序的待调度任务、每架无人机任务链、机巢泊位占用/排队与实时事件，列表和事件都可点击联动地图详情；
6. 在“场景事件注入”中可随机制造无人机故障或机巢关闭，也可直接点击具体无人机 / 机巢做精确控制；故障机未完成任务回到待调度池，关闭机巢的新补能请求会改道；
7. 需要控制订单压力时，可在“调度”页暂停/恢复**自动任务流**；点击待调度任务还可现场修改优先级、剩余 SLA、重量和类别，观察下一步分配是否改变；
8. 点击无人机可执行“调往最近机巢补能”。执行中无人机会先挂起剩余任务航线，经过真实泊位排队/换电后继续原任务；
9. 顶部“场景编辑”用于**结构性场景设计**：可增删/移动机巢、调整泊位、添加/移动圆形禁飞区。保存后会重建当前环境，因此建议在演示开始前完成布局设计；
10. 顶部“场景库”可保存当前初始配置，或导入/导出 JSON 场景包。它用于跨启动复现；“运行态快照”用于当前服务进程内恢复某个动态节点；
11. 态势页可直接加载“应急医疗高峰 / 机巢拥堵 / 故障韧性 / 标准综合”答辩预设，并按“下一幕”逐步执行真实控制动作；首次加载前的配置可以一键恢复；
12. 在故障、插单或拥堵等关键节点前可保存“运行态快照”，之后恢复到完全相同的动态节点重复演示；结构性场景重建不再清空旧快照，但跨环境代恢复会被拒绝并提示；
13. 继续“单步/播放”即可观察同一 GA / Greedy / PSO / OR-Tools 在当前状态上的重新调度；需要论文或结项数据时，再进入“实验”页运行标准化批量实验。

人工任务、任务属性调整、订单流开关、人工补能和运行时事故都不会重置环境；它们会刷新 observation，并在下一仿真步参与滚动重调度。**场景布局编辑属于结构性变更，保存后会重建环境并写回 `simulation.json`**，两类操作在系统中明确分开。

> 故障回收采用可复现的简化模型：故障机未完成任务回滚到原任务起点重新入池，不模拟空中货物交接。机巢关闭采用“软关闭”：停止接收新请求，已经开始的换电允许正常完成。

详细演示流程见 [`交互式仿真与答辩演示.md`](docs/交互式仿真与答辩演示.md)。v0.8 的场景库、启动预检与结项口径审计见 [`产品化收口与结项口径审计.md`](docs/产品化收口与结项口径审计.md)。

---

## 🧠 调度算法

| 方法 | 定位 | 编码 / 求解 | 代码位置 | **作用域（T10）** |
|---|---|---|---|---|
| **Greedy** | 基线 | 距离 + 优先级 + 紧迫度 + 电量 + 载荷 实时打分 | `frontend/greedy/` | 每步即时出解；**任何工况下都在工作**，也是另外三者的共用派发通道 |
| **PSO** | 群体智能 | 偏好矩阵编码，粒子群批量优化 + 事件驱动 | `backend_si/pso_scheduler.py` | **仅当 `pending_buffer` 触发批量 flush 时介入**（阈值 `buffer_size_threshold=15`）⇒ 轻载下不工作 |
| **GA** | 群体智能（主推） | **排列编码 + 贪婪分割解码** / 分配矩阵（可切换） | `backend_si/ga_scheduler.py`、`chain_codec.py` | 同上（与 PSO 共用外层与触发条件） |
| **OR-Tools** | 经典求解器基线 | CP-SAT，0/1 分配，目标 `makespan + Σ超时量` | `backend_si/ortools_scheduler.py` | 同上；且需本机装有 OR-Tools，缺失时界面标为不可用 |

> ⚠ **四算法对比的作用域限定（T10，必读）**：后三种"批量优化"算法**只在重载工况下才真正介入**。
> 双通道设计里即时派发优先，只有待分配积压到阈值（15）或紧急/超时兜底时才调用优化器 ——
> 而**出厂默认配置就是轻载**（10 机 / 60 任务，`pending_buffer` 峰值实测仅 2）。
> 该格实测 `optimize_calls = 0`、`flush_size = 0` ⇒ 三者跑的其实是共用的即时贪心通道。
> 因此：**不能用默认轻载工况的数据声称"四种算法性能有差异"**；在压力工况（如 C-1/C-2/S）下
> 优化器确实被调用并产生不同结果，那时比较成立。这条由常驻门
> `console/test_speed_fallback_gate.py::test_g2teeth_*` 的三面对照守着（size 触发口本身的语义
> 另由 `console/test_g2teeth_calibration.py` K1–K6 守着，见 §Phase 0 收尾），复算：
> `python console/phase0_speed_gate_teeth_probe.py gate|noDenom|mutate`。
> 换句话说，本项目对外的可比结论是**「同一环境下 Greedy 与各优化器的差」而非「四个算法天然不同」**，
> 且必须写明该环境是否触发了批量优化。

**GA 的两种编码**（`backend_si/config.yaml` 的 `ga.encoding` 切换）：

| 编码 | 染色体 | 解码 | 遗传算子 | 用途 |
|---|---|---|---|---|
| `permutation`（**默认**） | 任务排列 | 贪婪分割 → 每机有序任务链 | OX 顺序交叉 + 交换/插入/片段逆序变异 | 任务链优化引擎的落地实现 |
| `assignment` | 任务 → 无人机下标 | 直接分配 | 均匀交叉 + 负载感知变异 + 容量修复 | 与 PSO 同构，用于 A/B 对照 |

> 项目申请书规划的是「贪心 / 经典求解器 / 本项目优化算法」三种方案，PSO 属于实现阶段的扩展对比。
> 口径对应关系与扩展理由见 [`算法口径说明.md`](docs/算法口径说明.md)。

### 调度器的两层增强（Phase 1B，均有对照实验；**默认全部关闭**）

| 层 | 被替换的量 | 开关 | 实测效应（n=8 穷举符号检验） |
|---|---|---|---|
| **1B-1 距离感知** | Greedy 打分里的直线距离 → A\* 实际航路长度 | `SWARM_BALANCE_ROUTE_COST=planned_distance` | 完成任务数逐 seed Δ ∈ {−3…+4}、超时率最大 \|Δ\|=0.074 ⇒ **H0「几乎不变」已被否**；GA 面三档全逐位不变（阴性对照） |
| **1B-2 履约保护** | 新增罚分项 `W·min(0, slack_full/300)`，`slack_full = 剩余时限 − ETA取货 − 送货腿/速度` | `config.environment.greedy.reach_weight`（出厂 **0.0**）或同名环境变量覆盖 | 超时率 **4/4 组 8/8 全同号下降**（C1/40901 0.274→0.102，迟到 29→11）、平均时延同向 8/8；**代价：完成任务数 4/4 组里 6~7 个 seed 变差** |

两条必须一起讲：**1B-2 买的是履约、付的是吞吐**，只报超时率等于把代价藏起来。
奖励式 ETA（`clamp(slack/300)` 当加分项）已在实测中被否掉——它让超时率 6/6 seed 恶化，
根因是分子只算了取货段而 deadline 管送达（证据与一手机制见
[`phase1b2_mechanism_diagnosis.md`](docs/取证输出/phase1b2_mechanism_diagnosis.md)）。

答辩演示打开履约保护的命令（不改仓库默认值）：

```bash
SWARM_BALANCE_REACH_WEIGHT=1.2 python frontend/evaluate_metrics.py --policy greedy \
       --episodes 1 --episode-steps 3600 --seed 40901
```

> 这条命令会写 `results/adhoc/frontend_greedy_metrics.csv`（已在 `.gitignore` 里），不碰已入库产物；
> 上面这行本机实跑退出码 0，输出含 `禁飞区绕飞次数: 8.0000`（⇒ 距离口径确实在被使用）。
> 权重走环境变量而不是改 config：两者等价（`G14c` 断言 env 优先），但演示不该动仓库默认值。

门：G1–G9（1B-1）+ G10–G14（1B-2），共 15 项常驻用例；六个变异 V1–V6 + M1/M2 全部先红后绿。
阶段状态与撤回记录见 [`SwarmBalance总体架构与真实性演进总纲.md`](docs/SwarmBalance总体架构与真实性演进总纲.md) §17.0–17.3。

> ⚠ **读这两行结论前先确认工况是重载**：Phase 0 收尾时实测发现，轻载（机多单少）下批量优化器
> 根本不介入 ⇒ PSO / GA 与 Greedy 行为等价。出厂默认配置就是轻载（10 机 / 60 任务，buffer 峰值 2
> 对触发阈值 15）。所以任何"四算法性能对比"必须在重载场景做，否则比的是同一个算法。
> 三面对照复算：`python console/phase0_speed_gate_teeth_probe.py gate|noDenom|mutate`（见 §Phase 0 收尾）。

### 任务链与顺路接入

1. **优化器侧**：排列经贪婪分割解码后直接产出「每机一条有序任务链」，链内顺序不再被动态贪心重排打散；
2. **调度器侧**：`PSOScheduler` 每步检查在途无人机，若链条未满、取货点在绕行半径内、载重与电量允许、且接入后不超时，就把下一单挂到当前航线尾部，省掉「送完回巢/待命 → 再出发」的空驶与等待。

配置在 `config/simulation.json`：

```json
"task_chain": {
  "enabled": true,
  "max_chain_tasks": 3,
  "max_detour_m": 1500.0,
  "battery_reserve_ratio": 0.15
}
```

机制开/关对照实验：

```bash
cd frontend
python ab_chain_test.py --policies pso ga --episodes 1 --episode-steps 1200
```

### 禁飞区

`config/simulation.json` 的 `no_fly_zones` 段，支持 `circle` / `polygon`，含安全余量外扩：

```json
"no_fly_zones": {
  "enabled": true,
  "reserve_margin_m": 15.0,
  "zones": [
    { "name": "医院应急通道", "type": "circle", "center": [358300.0, 3462500.0], "radius": 150.0 },
    { "name": "管制空域A", "type": "polygon", "points": [[358950,3462750],[359150,3462750],[359150,3462950],[358950,3462950]] }
  ]
}
```

禁飞区与建筑物同等参与 `is_path_clear()` 判定，A\* 可见图补充外沿采样点实现真绕飞；
落在禁飞区内的取送货点会被自动过滤，避免生成不可达任务污染完成率。
实现见 `frontend/no_fly_zone.py`。

---

## 🗂 项目结构

```text
swarm-balance/
├─ run_conclusion.py             # 结项实验入口（11 行 shim → experiments.runner.main）
├─ run_tests.bat / run_conclusion.bat / release_check.bat / finalize_project.bat
├─ start_console.bat             # 启动 Web 控制台（8765）；portable 版走精简依赖
├─ stop_console.bat
├─ build_conclusion_package.py   # 结项证据包；DOCS/CONFIGS 白名单缺文件即抛错
├─ release_check.py / selfcheck  # 交付前静态检查（含内联 JS 语法）
├─ verify_data_provenance.py     # 数据来源可追溯性自检（登记表的可执行版；结项实验/加载路径两段）
├─ test_build*.py                # .: 1 个文件 / 3 个用例 —— 守对外交付物完整性（白名单缺文件即红）
│                              #   ⚠ 复算只能用窄模式：`discover -s . -t . -p "test_build*.py"`。
│                              #     根下用宽模式 `test_*.py` 会把 console/ 与 experiments/ 两个包
│                              #     递归吃进来 ⇒ 实测 **1 个文件 / 408 个用例**（373+32+3 双计）。
├─ README.md / CHANGELOG.md / CONTRIBUTING.md / CITATION.cff / LICENSE / VERSION
├─ requirements.txt              # 完整实验环境（Python 3.10）
│
├─ console/                      # Web 控制台（FastAPI）
│  ├─ run.py                     # 启动入口
│  ├─ server.py                  # REST 层（40 个路由）
│  ├─ sim_session.py             # Web 与 CLI 共用的唯一仿真会话入口
│  ├─ capabilities.py            # 运行时能力探测（可选依赖是否可用）
│  ├─ preflight.py               # 启动前环境自检（完整 / 便携两套必需清单）
│  ├─ config_validation.py       # 配置写入前的校验
│  ├─ scenario_presets.py        # 答辩预设（应急医疗高峰 / 机巢拥堵 / …）
│  ├─ scene_library.py           # 场景库持久化（config/scenes/）
│  ├─ experiment_service.py      # 一键实验的子进程编排与状态文件
│  ├─ static/index.html          # 单文件 Vue 3 应用（无构建步骤；行数用 wc -l 现数）
│  ├─ static/spec.html           # 「规范」页正文，由 /spec 路由渲染进 iframe
│  ├─ static/vendor/             # 内置 vue.global.prod.js / echarts.min.js /
│  │                             #   three.min.js + README（版本、来源、SHA-256）
│  └─ test_*.py                  # console: 53 个文件 / 373 个用例（标准库 unittest）
│
├─ frontend/                     # 仿真内核与可视化
│  ├─ environment.py             # 世界状态、障碍判定、统计口径
│  ├─ drone.py                   # STEP_SECONDS 等显式常量在此
│  ├─ task.py / charging_station.py / no_fly_zone.py / matching.py
│  ├─ scheduling_interface.py    # 调度器抽象基类
│  ├─ metrics_schema.py          # 统一指标列名（CSV 表头单一来源）
│  ├─ data_source.py / enterprise_data_source.py / mock_enterprise_api.py
│  ├─ greedy/                    # 贪心基线（scheduler.py + run_greedy.py）
│  ├─ tools/osm.py               # OSM 解析 + 结果落盘缓存（frontend/data/.osm_cache/）
│  ├─ data/                      # map/part_of_yangpu.osm（约 10.6 MB，唯一内置地图）
│  │                             #   + .osm_cache/（OSM 解析与通行判定缓存，已 gitignore）
│  └─ test_*.py                  # frontend: 2 个文件 / 19 个用例
│                                #   ⚠ 这 19 例**不在** `discover -s console` 里：frontend/ 没有
│                                #     __init__.py，以仓库根为顶层时 discover 直接抛
│                                #     "Start directory is not importable"（本轮实测）。
│                                #     复算须用 `python -m unittest discover -s frontend -t frontend`；
│                                #     其中 E1↔E0 等价门当前为红，接线经过与规模见
│                                #     docs/P70_invisible_gate_census.md。
│
├─ backend_si/                   # 经典基线算法
│  ├─ ga_scheduler.py / chain_codec.py / fitness_evaluator.py / matching.py
│  ├─ pso_scheduler.py / ortools_scheduler.py   # OR-Tools 缺失时降级并标记不可用
│  └─ config.yaml
│
│
├─ config/
│  ├─ simulation.json            # 环境/任务/无人机/禁飞区/机巢配置
│  ├─ config_loder.py            # 共享配置读取 + 来源签名（缓存失效判据）
│  ├─ positions.json
│  ├─ scenes/                    # 场景库落盘目录（scene_*.json 不入库）
│  └─ import/                    # 外部数据导入工作区
│
├─ experiments/
│  ├─ runner.py                  # 预设解析、子进程编排、聚合
│  ├─ worker.py                  # 单个 episode 的隔离执行（独立配置副本）
│  ├─ reporting.py               # 统计与配对检验
│  ├─ reproducibility.py         # 复现清单（schema v2：按算法登记源码哈希）
│  ├─ presets/                   # quick.yaml / conclusion.yaml / paper.yaml
│  └─ test_*.py                  # experiments: 3 个文件 / 32 个用例
│
├─ results/
│  ├─ compare/                   # 对比 CSV（答辩对比页数据源；两份清单见 console/server.py
│  │                             #   的 _CSV_FILES 与 results/plot_compare_metrics.py 的 CSV_FILES，
│  │                             #   两边不一致 —— 差异与后果写在 results/compare_gate.py 开头）+ plots/
│  ├─ experiments/               # conclusion_<时间戳>/ 正式实验目录
│  └─ plot_compare_metrics.py
│
├─ deliverables/                 # 作品图片、界面展示
├─ paper/                        # 论文正文与图件
└─ docs/                         # 说明文档 + Word 交付（逐份见文末索引，不写份数）
```

> 根目录另有结项工具链（`release_check.py`、`run_conclusion.py`、`build_conclusion_package.py`、`finalize_project.bat`）、
> 一键启动脚本（`start_console.bat` / `start_console_portable.bat` / `stop_console.bat`）与项目文档（见文末「文档」索引）。

---

## 🛩 仿真场景

统一 **1 步 = 1 秒** 时间口径，机巢**整组换电**（约 180 秒，换电期间不可接单）。

- 10 架异构无人机，三种机型；
- 最多 60 个配送任务，重量按「外卖/小件 → 快递包裹 → 重货」三档真实分布抽样；
- 任务含重量、体积、类别、优先级、起终点与 SLA 截止时间；
- 任务按高峰期 / 非高峰期 / 热点区域动态生成；
- 默认单回合 3600 步（1 小时）。

### 异构机队配置档（三档载重档位，仅一档有厂商机型锚点）

| 配置档 key | 型号来源 | 航速 (m/s) ¹ | 载重 (kg) ¹ | 电池 (Wh) ¹ | 满载续航 (km) ² |
|---|---|---|---|---|---|
| `light_express` | 轻载通用配置档｜无厂商机型对应，电池与能耗为情景参数 | 20 | 2.4 | 380 | 10 |
| `standard_cargo` | 中载通用配置档｜无厂商机型对应，电池与能耗为情景参数 | 14 | 10 | 1600 | 20 |
| `heavy_cargo` | DJI FlyCart 30｜官方规格锚点，能耗参数由官方电池与航程派生 | 20 | 30 | 3968.8 | 16 |

> ⚠️ **不要把前两档读成真实机型。** 它们的载重/速度量级参考了公开报道，但电池容量与能耗系数**没有任何厂商依据**（相关厂商均未公布），属于我方设定的情景参数；证据等级、原始出处与禁用表述见 `data/provenance/parameters.csv` 与 `docs/真实性审计表.md`。只有 `heavy_cargo` 可溯源到大疆官方规格页。

> ¹ **仿真输入**：对应 `heterogeneous.drone_types.<key>` 的 `speed` / `carrying_capacity` / `battery_capacity`，由 `frontend/drone.py` 读取并参与计算。
> ² **仅展示，不参与仿真计算**：`full_load_range_km` 写在配置里但代码从不读取；实际续航由 `battery_capacity` 与放电模型（`battery_consumption_base` × `battery_load_penalty_factor`）推导，改这一列不改变任何仿真结果。该结论由 `console/test_config_keys_coverage.py` 守住。
> 上述为公开规格近似取值，用于仿真对比，实际以官方最新发布为准。
> 载重与电池容量可对到公开规格；**航速一列（含 `standard_cargo` 的 14 m/s 与 `sla_reference_speed=14`）在仓库内未标注出处**，
> 逐条溯源见 [`数据来源与可追溯性登记表.md`](docs/数据来源与可追溯性登记表.md) 第二节（P1–P3）。

### 真实数据接入

`data_source.type` 支持 `random` / `csv` / `geojson` / `enterprise`。
新增一个 `DataSource` 子类（实现 `load_drones` / `load_nests` / `load_tasks` / `build_task_source`）
即可接入企业真实订单、机队与机巢数据，**无需改动环境与调度算法**。

```python
from environment import Environment
from enterprise_data_source import EnterpriseDataSource

ds = EnterpriseDataSource(base_url="https://tms.example.com", api_token="…", coord_system="lonlat")
env = Environment("data/map/part_of_yangpu.osm", data_source=ds)
```

- `coord_system="lonlat"` 时自动用 pyproj 把 WGS84 经纬度投影为 UTM 平面坐标（米）；
- `live=true` 每步轮询接口并按订单号去重，对应真实订单持续到达；
- 无网关时可运行 `frontend/mock_enterprise_api.py` + `run_enterprise_demo.py` 预览。

---

## 📊 评估指标

| 指标 | 含义 | 方向 |
|---|---|---|
| Completion Rate | 已完成任务数 / 已生成任务数 | 越高越好 |
| Timeout Rate | 超时任务 / **已完成**任务（未完成任务不进分子分母，属幸存者口径，须与 Completion Rate 联读） | 越低越好 |
| Average Delay | **全部**完成任务的平均超时时长（准时任务按 0 计入分母），恒等于 `超时率 × 超时任务的平均晚到时长` | 越低越好 |
| Generation-to-Assignment Wait | 生成 → 被分配的等待时间 | 越低越好 |
| Assignment-to-Loading Wait | 分配 → 实际装载的等待时间 | 越低越好 |
| Loading-to-Delivery Time | 装载 → 送达的平均时间 | 越低越好 |
| Avg / Max Generation-to-Completion | 全流程平均 / 最大耗时 | 越低越好 |
| Priority Average Delay | 各优先级任务平均时延 | 越低越好 |
| Total Energy Consumption | 机队累计能耗 | 越低越好 |
| **Drone Utilization** | 机队利用率 = 忙步数 /（仿真秒数 × 机队规模）；**仅当 `drone.time_step = 1`** 时才等价于「忙步数 / 总步数」 | 越高越好 |
| **Empty Load Ratio** | 空载率 = 空载里程 / 总飞行里程；「空载」= 机上无货 **或** 下一任务航点是取货点（运力回收段） | 越低越好 |
| **Chain Insertions** | 顺路接入次数 | 机制生效观测 |
| **No-Fly Detours** | 禁飞区绕飞次数 | 机制生效观测 |
| Berth Utilization / Nest Turnover / Avg Berth Wait | 机巢泊位利用率、周转率、排队等待 | 视运营目标 |

指标列定义集中在 `frontend/metrics_schema.py`（单一事实来源），所有评测入口共用同一份表头，
新增指标只需改这一处。表头不兼容时会自动备份旧 CSV，不会静默覆盖历史实验结果。

---

## 🧪 复现实验

### 复现 Phase 1B-2 的结论（一键，本地运行包入口）

```bash
# 仓库根目录执行；完整模式 = C-1/C-2 × 8 seeds × {w=0.0, w=1.2} = 32 cells，约 2 分钟
python scripts/reproduce_phase1b2.py

# 快速自检（只跑 seed 40901，4 cells）：验证链路通不通，**不产出统计结论**
python scripts/reproduce_phase1b2.py --quick
```

它做四件事，全部走生产代码路径、不含任何演示用假数据：环境预检（解释器/依赖，缺了就报
该用的绝对路径而不是抛 traceback）→ 逐格跑 worker → **现算**超时率/完成数对照表与穷举符号
检验精确 p（复用 `console/_paired_readout.py`，与常驻门同一把尺子）→ 打印已知问题清单。
日志写 `results/adhoc/reproduce_phase1b2.log`（已 gitignore），临时 config 跑完即删。

本机实测输出（完整模式，退出码 0）：超时率 **4/4 组 8/8 全同号下降**、精确 p = 0.0078
（n=8 可达最小值）；完成任务数 **6~7/8 变差** ⇒ 这一层是"用吞吐换履约"，两半一起看。
判据「≥6/8 同号才算成立」由用户在拍板时给定。证据文件：
[`phase1b2_sign_n8.md`](docs/取证输出/phase1b2_sign_n8.md)。

> ⚠ 别用 `--quick` 的输出当结论：单 seed 没有分母（n=1 最小可达 p = 1.0），脚本会显式跳过
> 符号检验并说明原因——空表比一个装饰性的 p 值诚实。

### Phase 0 收尾：PSO/GA/OR-Tools 的 speed 门为什么曾「无分母」

常驻门 `console/test_speed_fallback_gate.py` 曾报 `[pso][NO_DENOMINATOR]`（一步都没进批量优化器）。
诊断结论：**不是代码缺陷、也不是判据问题，是 fixture 工况选错了** ⇒ 本轮只修 fixture，
判据三条与触发阈值 15（`backend_si/config.yaml:16`）一个字没动。

承重变量是**机队规模**（`heterogeneous.fleet_mix`），不是任务量。三面对照实测
（seed=40901、episode=3600 步、阈值 15 不变；复算命令见下）：

| 工况 | tasks | fleet_mix 合计 | `optimize()` 调用 | `flush_size` | buffer 峰值 | 门状态 |
|---|---|---|---|---|---|---|
| gate（重载，门的真实工况） | 240 | 6 (3,2,1) | 1477 → **1909** | 1 → **0** | 15 → **10** | 有分母 ✓ |
| noDenom（出厂轻载，原红门所在格） | 60 | 10 (5,3,2) | **0** | 0 | 2 | 无分母 ✗ |
| mutate（只把机队 6→10） | 240 | 10 (5,3,2) | 3 → **6** | **0** | 3 | 牙线生效 ✓ |

> ⚠ **上表"→"右侧是 #69-H3 D-iv 树上的本轮实测**（左侧是 pre-D-iv 旧标定）。两列都要读：
> D-iv 把 completion 计时从"后缀规则"改成"执行器真 pop"后，同一工况的 buffer 峰值从 15 降到 10、
> size 触发口从开 1 次变成开 0 次 ⇒ **"真实工况会打开 size 口"不再是可用的判据**（详见
> `docs/#65_rerun_delta.md` §7、§8）。承重变量仍是**机队规模**，这一点两棵树一致。

```bash
# 复算（仓库根目录，逐面打印一行 TEETH 读数）
python console/phase0_speed_gate_teeth_probe.py gate
python console/phase0_speed_gate_teeth_probe.py noDenom
python console/phase0_speed_gate_teeth_probe.py mutate
```

**g2teeth 现在守什么（阶段② 重标定后，2026-10-08）**：原先那条 `[GATE_CALIBRATION_STALE]`
显式 skip 已解除，改为两层各走各的通道——
- **L1 机制层**（常驻、进退出码）：`console/test_g2teeth_calibration.py`，K1–K6 合成夹具。
  size 触发口的语义由"N=阈值−1 / 阈值 / 阈值+1 三格的行为"裁决，标签来自比较式
  `len(pending_buffer) >= buffer_size_threshold`（`backend_si/pso_scheduler.py:1444`）的定义本身，
  **不来自任何正式实验产物**。K6 是整套的牙：把 `>=` 变异成 `>` 后 K2 必须变红。
- **L2 观测层**（只印读数、不进退码）：真实工况的 `buffer_peak` / `flush_size`。
  "当前计时下积压不到 15"是 scheduler 行为事实，不是实现缺陷。

⇒ 所以「四算法对比只在重载才成立」这条口径限制的证人变了：**机队规模是承重变量**仍由三面对照守着；
**size 触发口是否正常工作**改由 L1 合成夹具守着（它不再依赖一次特定运行的峰值刚好摸到 15）。
复算：`python -m unittest -v console.test_g2teeth_calibration`（秒级）。

两条必须说出来的教训：

1. **「切 `num_drones`」不是单变量。** `frontend/environment.py:144 build_fleet_drone_types()`
   先按 `fleet_mix` 展开机型序列、再截断/补齐到 `num_drones`，所以 `num_drones=10` + mix 合计 6
   拿到的仍是那 6 架机。我最初把变异打在 `num_drones` 上，门照样绿，差点误判成"门无牙"。
2. **牙不能挂在 `optimize_calls > 0` 上。** 变异后仍有 timeout 兜底触发（pre-D-iv 是 3 次、
   D-iv 树是 6 次），足以糊过这条线；真正会归零的是 `flush_size`。负面对照已实测：把阈值从 15 降到 2，
   gate 面 buffer 峰值只剩 5 ⇒ 该判据吃的是真实读数，不是恒真式。
   （阶段② 起这条只做**一次性演示**、不再作常驻断言——size 口的语义已由上面的 L1 合成夹具守。）

> ⚠ 由此登记一条口径限制（已写入总纲 §17）：**轻载（机多单少）下 PSO / GA 与 Greedy 行为等价**
> —— 批量优化器根本不介入。任何"四算法性能对比"必须在重载场景做，否则比的是同一个算法。

```bash
cd frontend

# 四类算法（seed 统一 = 100 + episode_id，保证跑同一批场景）
python evaluate_metrics.py --policy greedy  --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy pso     --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy ga      --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy ortools --episodes 5 --episode-steps 2000

# 汇总指标并出图
cd ../../..
python results/plot_compare_metrics.py
```

> **这两段默认都不碰已入库的东西**：上面四条评测只写 `results/adhoc/<算法>.csv`
> （已在 `.gitignore` 里），出图只写 `results/adhoc/plots/`。
> 只有**确实要把结果刷进答辩证据**时才加开关，且两者都会留下 git 改动、需要你显式处置：
>
> ```bash
> # 追加一行到已入库的 results/compare/<该算法>.csv（Web 算法对比页数据源）
> python evaluate_metrics.py --policy ga --episodes 5 --episode-steps 2000 --record-into-evidence
> # 覆盖已入库的 results/compare/plots/ 下 15 个产物（12 张图 + 3 份派生表）
> python results/plot_compare_metrics.py --record-into-evidence
> ```
>
> **但今天这两条都会先被口径门禁拒绝**（实测：`plot_compare_metrics.py` 退出码 1，
> 原文以 `[REFUSED]` 开头，把 400/600 步的 GA 与 2000 步的三个基线分成了两个桶）。
> 想真的刷进证据，得先按结项口径重跑 GA（3600 步 / 5 回合 / seed 101–105），
> 让 `python results/compare_gate.py --check-all` 通过 —— 顺序写在
> `results/compare/plots/README.md` 里。
>
> **`results/compare/plots/` 整目录已标作废**：3 份派生表的算法列仍含 6 个
> 已被 6b8c4c8 撤除的 MARL 算法（数字在登记表 R2 被逐格证伪），因为那 15 件产物
> **逐件**查最后一次入库改动都停在 `fcc7c5f`（2026-09-11），是 `6b8c4c8` 的祖先 ——
> 撤除从未到达这里。注意判据不能问"整个目录"：这份作废通知本身就是往该目录新加的文件，
> 一问目录就会被自己推翻，所以 `console/test_plots_archive_void.py` 按文件逐个问；
> 12 张 PNG 与像素里画的是什么没单独核验（位图读不出列），该目录的通知把这条写成"未实测"。同一目录还并存两份口径不同的 GA
> （归档表 2000 步，入库 CSV 400/600 步）。
> 这件事不再只写在纸上：`console/test_plots_archive_void.py` 逐条断言，并且是**双向**的 ——
> 哪天清掉 MARL 行重生了这个目录，测试会红并要求撤销作废通知。
>
> **已知归档缺口（实测，未自行补齐）**：出图脚本一次生成 **17 张 PNG + 3 份派生表 = 20 个
> 文件**，而 `results/compare/plots/` 只归档了 **12 张图 + 3 份表 = 15 个产物**（目录另有
> `README.md` 与 `ROW_SETS.md` 两份说明，不归这条出图链生成 —— `ROW_SETS.md` 由
> `results/row_set_delta.py --write` 生成）。复算这条不要靠这里的数字：
> `python results/plot_compare_metrics.py --allow-mixed-comparisons` 只写 gitignore 的
> `results/adhoc/plots/`，跑完 `ls results/adhoc/plots/*.png | wc -l` 就是当次张数。
> 若门禁放行后再加 `--record-into-evidence`，
> 除覆盖那 15 个之外，还会在已入库目录里**新添 5 个未跟踪 PNG**
> （`bar_chain_insertions` / `bar_drone_utilization` / `bar_empty_load_ratio` /
> `bar_no_fly_detours` / `bar_total_flight_distance`）—— 这正是 `git add -A` 会顺手扫进
> 提交的那类残留。是否把这 5 张作为正式交付物入库，需要你拍板；在此之前请**不要**对该目录用 `git add -A`。
>
> 为什么默认改成只写 adhoc：原先默认直接写 `results/compare/` 与 `results/compare/plots/`，
> 评审照本节跑一遍就会把入库的评测 CSV 追加行、并把 15 个已提交图表**就地覆盖**，
> 工作区立刻变脏且说不清哪张图还是当初那张。

**复现建议**

- 对比实验应保持 `config/simulation.json` 中机队规模、任务数量、生成模式与截止时间一致；
- 各算法使用相同 `episodes` 与 `episode-steps`；
- 强化学习需固定模型、随机种子与测试回合数，并报告**多种子均值与方差**，不能依据单次训练下结论；
- 生成论文图表前确认 CSV 采用的是目标实验行。

---


## 🧪 一键结项实验（不影响自由仿真）

系统仍以交互式仿真控制台为主；批量对比只是独立的实验编排模式。实验运行时会为每个 episode 生成隔离的 `simulation.json` 副本，**不会修改当前主配置**，并保证同一条件下各算法使用相同随机 Seed。

```bash
# 快速自检：少量 Greedy / GA 运行，先确认链路正常
python run_conclusion.py --preset quick

# 标准结项：Greedy / OR-Tools / GA / PSO + 三类敏感性分析
python run_conclusion.py --preset conclusion

# 论文模式：增加重复次数，耗时更长
python run_conclusion.py --preset paper

# 只看本次会跑哪些组合，不真正启动仿真
python run_conclusion.py --preset conclusion --dry-run

# 只有确认要用本次正式实验覆盖答辩页数据源时，才加发布开关：
python run_conclusion.py --preset conclusion --publish-latest
```

> **这条命令会写入哪里**：结果写到 `results/experiments/<preset>_<timestamp>/`
> （新目录，按秒打时间戳，**不会**覆盖任何一轮归档实验；该命名模式已在 `.gitignore` 里，
> 所以照 README 跑一遍不会给仓库添 `??`）。
> 原先 `--preset conclusion` 跑完还会**截断重写**已入库的
> `results/compare/one_click_latest.csv` —— 那是 Web「算法对比」页按 `keep="last"`
> 实际展示的那份证据，等于一条文档命令悄悄替换答辩数据源。现在必须显式加
> `--publish-latest` 才会写，且不加时会打印"已跳过"。
> Web 控制台「实验」页签内部带 `--publish-latest` 启动，行为与文档一致：
> 页面上点「跑结项实验」仍然会自动刷新对比页。

Windows 也可以直接双击 `run_conclusion.bat`，或在命令行执行 `run_conclusion.bat quick`。Web 控制台右侧新增“**实验**”页签，可选择同样的预设并一键运行；底层与命令行共用 `ExperimentRunner`，不是两套实验逻辑。

结果默认写到 `results/experiments/<preset>_<timestamp>/`，包括：

- `plan.csv`：完整运行计划、Seed 与每组配置补丁；
- `raw_runs.csv`：每个 episode 的原始指标；
- `algorithm_comparison.csv`：算法对比均值；
- `task_density.csv` / `nest_capacity.csv` / `fleet_mix.csv`：三类敏感性分析；
- `figures/`：自动生成的对比与敏感性图；
- `summary.md`：可直接用于整理结项报告的实验摘要。

预设配置位于 `experiments/presets/*.yaml`。如要调整重复次数或扫描范围，优先修改/复制 YAML，而不是改实验代码。

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [`SwarmBalance总体架构与真实性演进总纲.md`](docs/SwarmBalance总体架构与真实性演进总纲.md) | **最高优先级技术设计参考。** 项目双口径定位、能力基线四态标注、当前模型真实性边界（含"建筑高度不进航迹""无 z/yaw/加速度"等诚实条款）、目标分层架构、Phase 0–9 路线与验收条件、新技术准入四问、当前禁止事项。后续开发若与本文冲突：先改本文并说明理由，再改代码 |
| [`数据来源与可追溯性登记表.md`](docs/数据来源与可追溯性登记表.md) | **每个数字从哪来、能不能追溯到一次运算。** 按 A 可追溯 / B 不可追溯 / C 无来源 三级登记物理参数、指标口径与已发布结果，附亲自复现的命令 |
| [`仿真软件设计规范.md`](docs/仿真软件设计规范.md) | 规范正文（单一事实源）。软件内「规范」页由 `console/static/spec.html` 渲染，另有同内容的 `docs/仿真软件设计规范.docx` 供 Word 交付 |
| [`世界逻辑规格书.md`](docs/世界逻辑规格书.md) | 规范 WL 章的展开：世界规则、数值口径与**尚未落实项清单** |
| [`仿真内核分层架构设计.md`](docs/仿真内核分层架构设计.md) | 规范 SA 章的展开：内核分层现状与目标态迁移路线 |
| [`架构与界面改造方案.md`](docs/架构与界面改造方案.md) | 历史改造方案（含改造前基线数字与「为什么不拆目录」的决策理由） |
| [`算法口径说明.md`](docs/算法口径说明.md) | 申请书承诺算法与代码实现范围的对应关系、公平性保障、术语修正 |
| [`可视化操作平台完善计划书.md`](docs/可视化操作平台完善计划书.md) | Web 控制台的架构设计与分阶段路线 |
| [`调度指挥台说明.md`](docs/调度指挥台说明.md) | 2D/3D 指挥台的点击详情、候选机匹配能力与约束解释 |
| [`交互式仿真与答辩演示.md`](docs/交互式仿真与答辩演示.md) | 自由仿真与答辩演示的完整操作流程 |
| [`场景事件与韧性演示.md`](docs/场景事件与韧性演示.md) | 无人机故障、任务回收、机巢关闭/改道与答辩演示流程 |
| [`场景编辑与运行控制.md`](docs/场景编辑与运行控制.md) | v0.6 场景布局编辑、订单流控制、动态任务调整与人工补能 |
| [`演示场景与运行态快照.md`](docs/演示场景与运行态快照.md) | v0.7 一键答辩场景、真实“下一幕”剧本、运行态快照与服务端趋势 |
| [`产品化收口与结项口径审计.md`](docs/产品化收口与结项口径审计.md) | v0.8 场景库、启动预检、配置一致性、代码审计与答辩口径边界 |
| [`离线便携与端到端自检.md`](docs/离线便携与端到端自检.md) | v0.9 离线 OSM 回退、便携启动、真实端到端自检与发布检查 |
| [`结项最终验收清单.md`](docs/结项最终验收清单.md) | v1.0 正式环境、系统交互、实验、口径与证据归档的最终验收门槛 |
| [`结项修改说明.md`](docs/结项修改说明.md) | 结项阶段的修改清单与口径说明 |
| [`提交改写映射表.md`](docs/提交改写映射表.md) | 两轮 message 改写（只改信息、不动树）造成的 旧 sha → 现 sha 映射、复算式，以及"旧对象只靠 reflog 活着、长期引用别用 sha" |
| [`论文侧撤除未达清单.md`](docs/论文侧撤除未达清单.md) | 由 `console/_paperscan.py` 现算的具名清单：论文里哪几处是**待作者定夺**的结论形式、哪几处是**合法**的相关工作引用；只报不改 |
| [`compareCSV普查.md`](docs/compareCSV普查.md) | 由 `console/_csvcensus.py` 现算的 `results/compare/*.csv` 形状（份数/列宽/BOM/seed 列 + 两份清单的三桶与恒等式）；登记表 R4 的那些数归它管，文档只指路不抄数 |
| `frontend/README.md` · `backend_si/README.md` | 仿真环境入口 / PSO 调度器参数与双通道机制详解 |

---

## 🤝 贡献

欢迎 Issue 与 PR，流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。要点：

- 分支用 `ui-member`、`chain-opt` 这类**不带斜杠**的短名；
- 提交前确认 `results/compare/*.csv` 未被误改；
- 新增指标请只改 `metrics_schema.py`，不要在评测脚本里另起表头。

---

## ⚠️ 已知局限

- v0.9 的内置 OSM XML 回退解析器用于答辩/演示兜底，只解析建筑 way 与主干道路 way，不展开复杂 multipolygon relation；正式论文/结项实验仍以 Python 3.10 + OSMnx 完整环境为准；
- GA 排列编码已实现贪婪分割后的**链内 swap / 2-opt + 跨链 relocate**局部搜索；当前尚未实现更复杂的 Or-opt、多链交换与自适应大邻域搜索（ALNS）；
- 顺路接入的绕行判定用**绝对半径**（默认 1500 米，约为本地图跨度 55%），换地图需重新标定；
- 能力匹配目前采用可解释的载重/速度/续航加权函数，权重仍需通过敏感性实验标定；
- 禁飞区可在 Web 场景编辑器中重设布局，但仍属于**场景级静态约束**（保存后重建），尚未实现仿真过程中随时间自动出现/消失的时变空域管制；
- 仿真为离散时间步；无人机故障是运行时状态事件，未进一步模拟电机退化、定位漂移、风场等连续物理过程；
- **轻载工况下 PSO / GA 与 Greedy 行为等价**：批量优化器由 `pending_buffer` 触发（阈值 15），机多单少时
  buffer 峰值只有 2 ⇒ 优化器一步都不介入。出厂默认配置就是轻载（10 机 / 60 任务）。所以四算法对比
  **必须**在重载场景做，否则比的是同一个算法；该结论由常驻门 `test_g2teeth` 三面对照守着（§Phase 0 收尾）；
- ⚠ **完成语义存在已复现的逻辑矛盾，历史 KPI 待重验（P0）**：生产路径 `experiments.worker.run_one(..., "greedy", seed=40907, 1200)`
  实测 38 条完成记录里有 **12 条来自 `is_free` 兜底清理而非抵达送达点**（占 31.6%，其中 3 条连取货证据都没有），
  且这 38 与 KPI「完成任务数=38.0」逐位相等 ⇒ 完成率分子被污染。当前系统没有完整、持久、逐任务的完成真源
  （`completed_tasks` 是单步缓冲、`completed_task_log` 截断至 120 行、只有计数器 `total_completed_tasks` 承重）。
  实测交叉污染：**三个指标共用同一棵被污染的分母**（`timeout_rate = 1 − on_time/total_completed_tasks`、`avg_delay = total_delay/total_completed_tasks`），
  且 cleanup 那 12 条贡献了全部延迟量的 **80.3%**（85.5/106.5）——对平均时延的污染强度远大于对完成率的。
  ⇒ 在闭环（旁路 Observer → C1 完成不变量门 → 业务语义修复 → 重跑）之前，
  **`results/compare/*.csv` 与论文侧引用的完成率/超时率/平均时延一律视为 pending lifecycle-consistency revalidation**。
  取证与设计见 [`docs/当前状态真源图.md`](docs/当前状态真源图.md) §6、`docs/取证输出/prod_completion_repro.json`；
- - **数据可追溯性**：项目内每个"被当作事实呈现的数字"的来源、能否点开验证、能否追溯到一次运算，逐条登记在 [`数据来源与可追溯性登记表.md`](docs/数据来源与可追溯性登记表.md)，可用 `python verify_data_provenance.py` 独立重算。其中两条须如实声明：
  其一是原 MARL 对比（QMIX/VDN/IQL 六行）经逐格核对**在本仓库任何原始记录中都找不到对应运算**（54 个性能格里 23 格优于该算法历史上最好的一局、0 格劣于最差一局、38 格与任何一行都不相等），且其训练产物从未进入版本库，因此该模块与其指标行已一并移除，本项目不再声称 MARL 结果；
  其二是内置地图的碰撞体规模**取决于目标机器能否 `import osmnx`**（108 栋 vs 18 栋），因此结项实验的逐位可重算性只在依赖一致时成立。
- **证据等级：官方规格派生，未达实机独立验证**。能耗链的全部外部输入只有三个官方数字（单块 1984.4 Wh、空载 28 km、满载 16 km），
  四个派生量是同一组数被除了四次（恒等式，非独立校验）；能耗公式的**结构形式**在仓内零拟合实现、无实机日志可接 ⇒ 标为「未锚定」。
  已尝试的 Validation 路径取回了 PX4 ULog 并与所获清单对账（抽样 5 个 md5+尺寸 5/5），但那 5 个含 `SIM_BAT_DRAIN`/`SIM_GZ_*` 参数、
  属 Gazebo 仿真器输出（其余 62 个**未分类**，抽样不外推），用它反推 Wh/km 会得到自洽的假验证值，故**不产出该数值**；
  且该清单的**原始 md5 计算者未确认**（它登记了 Zenodo 当前包里并不存在的 `code/*` 条目 ⇒ **不是仅由该 ZIP 生成**；
  至于来自哪个上游包属**待验证假设**，那两个包未核对）。
  详见 [`docs/证据等级与Validation边界.md`](docs/证据等级与Validation边界.md)。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE)。

## 📖 引用

若本项目对你的研究有帮助，请引用（另见 [`CITATION.cff`](CITATION.cff)）：

```bibtex
@software{swarmbalance2026,
  title  = {SwarmBalance 群智优衡: 异构无人机集群三维协同调度仿真平台},
  author = {群智优衡项目团队},
  year   = {2026},
  url    = {https://gitee.com/acgvgh/swarm-balance}
}
```

---

<div align="center">

北华大学 · 大学生创新创业训练计划项目（2026.06 — 2028.05）

</div>
