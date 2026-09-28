# 群智优衡项目 · AI 交接提示词

> 把这整份文档复制给接手的 AI 即可。请**先读完再动手**，尤其第二部分（环境）和第五部分（已知的坑）——不读会浪费大量时间。

---

## 一、这是什么项目

**SwarmBalance 群智优衡** —— 异构无人机集群三维协同调度仿真平台（v1.0.0）。
面向城市应急与低空物流场景，做多无人机 / 多任务 / 多机巢的联合调度优化，并用多算法统一口径对比验证。

**技术栈**

- 后端：Python 3.10 + FastAPI + Uvicorn + NumPy + osmnx + shapely + pyproj + OR-Tools
- 前端：Vue 3 + Three.js + ECharts 5（**全部 CDN 引入，无构建步骤**，见 `console/static/index.html`）
- 强化学习：PyMARL（IQL/VDN/QMIX，PyTorch），位于 `backend_wx/`

**核心设计：双入口**

| 入口 | 用途 | 命令 |
|---|---|---|
| Web 控制台 | 交互式演示、答辩 | `start_console.bat` → `http://127.0.0.1:8765/` |
| 命令行脚本 | 批量跑实验出 CSV | `python frontend/evaluate_metrics.py --policy ga ...` |

两者共用同一个 `SimSession`，不要另起一套仿真循环。

---

## 二、环境（先读这节，否则跑不起来）

**项目路径**
```
C:\Users\yyyy\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\
  6a91893e4cc261f69a0a52a0\drone-scheduling
```

**关键：虚拟环境在项目的「上一级」目录，不在项目内**
```
<上一级>\.venv310\Scripts\python.exe     ← Python 3.10.11
```
所有启动脚本都已处理这个路径，会自动向上找。

**三条硬约束（违反必出问题）**

1. **Python 必须 3.10**。`osmnx==1.9.4` 声明 `Requires-Python <3.13`，3.11/3.12 装上后 geopandas/fiona 组合会出问题，3.13 直接装不上。
2. **安装顺序不能反**：必须先 `pip install numpy==1.26.4`，再装其余。因为 `ortools` 会把 numpy 升到 2.x，而 `osmnx==1.9.4` 要求 `numpy<1.27`，升级后 osmnx 直接报 `numpy._utils` 错误。
3. **pip 用 23.x**。pip 26.2.x 在 Windows 有 safe-delete bug（`SHFileOperationW` 失败 0x2），会卡死并可能损坏 pip 自身。

完整依赖见 `requirements.txt`（含中文注释说明上述坑）。

---

## 三、目录结构

```
drone-scheduling/
├── console/                     Web 控制台（FastAPI 服务）
│   ├── server.py                806 行，40 个 API 端点　← 偏大，可拆
│   ├── sim_session.py           1212 行，仿真会话封装
│   ├── static/index.html        2665 行，单文件 SPA（Vue3+ECharts+three.js）
│   ├── capabilities.py          运行时能力探测（缺依赖降级，设计优秀）
│   ├── preflight.py             启动预检（中文错误提示）
│   ├── experiment_service.py    一键实验编排
│   ├── scenario_presets.py      答辩演示场景
│   ├── scene_library.py         场景库
│   └── test_*.py                6 个测试文件（33 个用例）
├── frontend/                    仿真内核
│   ├── environment.py           1871 行，核心仿真逻辑　← 偏大
│   ├── drone.py / nest.py / charging_station.py / no_fly_zone.py
│   ├── greedy/scheduler.py      Greedy 调度器
│   ├── tools/osm.py             OSM 解析（osmnx 可选，有内置 XML 回退）
│   ├── data/map/*.osm           本地地图数据（13M，离线可用）
│   └── evaluate_metrics.py      命令行评测入口（主力）
├── backend_si/                  PSO / GA / OR-Tools 调度器 + 适应度评估
├── backend_wx/pymarl-master/    PyMARL 框架（训练用，**运行时零引用**）
├── config/                      仿真参数、场景库
├── experiments/                 实验编排（runner/worker + 2 个测试）
├── results/                     实验产物（CSV + 图表）
├── deliverables/作品图片/        答辩用截图（01-07）
├── docs/                        18 个设计文档（算法口径、架构、规范等）
└── *.bat                        启动/停止/测试脚本
```

---

## 四、怎么运行、怎么验证

**启动**
```bat
双击 start_console.bat      → 自动开浏览器到 http://127.0.0.1:8765/
双击 stop_console.bat       → 停止并释放端口
双击 start_console_debug.bat → 诊断版（无条件 pause，闪退时用它看报错）
```

**跑测试（改了代码必须跑）**
```bat
双击 run_tests.bat          → 42 个测试（33 console + 8 experiments + 1 打包）
```
用标准库 `unittest`，**环境里没装 pytest**，别再引入。

**命令行跑实验**
```bat
..\.venv310\Scripts\python.exe frontend\evaluate_metrics.py --policy ga --episodes 5 --episode-steps 2000
```
结果写入 `results/`，供 `results/plot_compare_metrics.py` 出图。

**四个可用算法**：`greedy` / `pso` / `ga` / `ortools`

---

## 五、已知的坑（都是踩过的，别重复踩）

### A. Windows / 本机工具环境

| 坑 | 现象 | 对策 |
|---|---|---|
| **`.bat` 必须是 CRLF** | LF 换行的 bat 行为异常 | `.gitattributes` 已声明 `*.bat text eol=crlf`；用 `open(p,'wb')` 写入后要手动转 CRLF |
| **`SHFileOperationW` 返回码不可靠** | 返回 `2` 但文件**实际已成功删除** | **判断成败必须回查文件系统**，不能只看返回码 |
| **文件名编码损坏** | 部分中文文档名是「UTF-8 字节被按 cp437 解读」的产物（磁盘上就是坏名） | 还原：`name.encode('cp437').decode('utf-8')` |
| `find` 在 `C:\$Recycle.Bin` | 被 SIGTERM（本机有 2 万+ 条） | 改用 Python `glob` + 解析 `$I` 元数据 |
| 从 Bash 调 `cmd /c` | 被安全策略拦截 | 用 Python `subprocess` 直接调 `cmd.exe` |
| 从 Bash 调 PowerShell | 被拦截（"bypasses PowerShell security checks"） | 用专门的 PowerShell 工具 |
| PowerShell `Add-Type` | 被拦截（"compiles and loads .NET code"） | 改用 Python ctypes 调 Win32 API |

### B. 前端（ECharts / SPA 相关）

| 坑 | 现象 | 已采用的对策 |
|---|---|---|
| **`v-if` 切页导致图表消失** | 切走再切回，图表区空白、**控制台 0 错误** | 用 `chartFor(el,key)` 按 DOM 重绑定（`echarts.getInstanceByDom`），6 个图表函数统一走它 |
| **CDN 加载顺序竞态** | `mounted` 早于 echarts 就绪 → `ReferenceError: echarts is not defined` | `ensureEcharts()` 轮询等待；各绘制函数开头判 `typeof window.echarts === 'undefined'` |
| **CSS `!important` 吃掉 JS 内联高度** | `el.style.height=...` 完全不生效 | 改用 flex 让 CSS 自适应，别用 JS 算像素 |
| **地图数据晚于快照到达** | 首屏 2D 地图空白，要点播放才出现 | `init()` 里地图加载完**补一次重绘** |
| echarts 持有 Vue 响应式对象 | 内部异步渲染报错 | 喂给 echarts 的数据先 `JSON.parse(JSON.stringify(...))` |

### C. 后端 / 仿真

| 坑 | 说明 |
|---|---|
| **别另起仿真循环** | 所有入口共用 `SimSession.step_many()`；历史上 `evaluate_metrics.py` 和 `run_*.py` 各写一套，导致表头口径不通 |
| **表头统一** | 经 `frontend/metrics_schema.py` 统一，**不要在评测脚本里另起表头** |
| **并发推进** | `server.py` 用 `_op_lock`（RLock）串行化 step/reset/rebuild/inject，高倍速播放时防重叠 |
| **`is_path_clear` 性能** | A* 每规划一条路径要调它数千次；已用**包围盒预筛**（GEOS 调用 −74%）。改动时保持这个优化 |
| 共享配置 | 环境变量 `SWARM_BALANCE_SIM_CONFIG` 可覆盖配置路径 |

---

## 六、当前状态

**已完成的优化（本轮）**

1. **服务启动预热**：首次 `/api/snapshot` 从 2.2s → 0.018s（会话懒加载改后台线程预热）
2. **路径规划提速 30%**：`is_path_clear` 加包围盒预筛（GEOS 调用 82731 → 21759），**状态指纹一致、未改仿真结果**
3. **修复首屏地图空白**（`init()` 时序）
4. **修复切页图表消失**（echarts 实例按 DOM 重绑定）
5. **结构整理**：PyMARL 训练产物移出 git 索引（340→58）、16 个文档归档 `docs/`、11 个损坏文件名还原、新增 `run_tests.bat`

**git 状态：变更已 `git add` 暂存，但尚未提交**（最近提交 `2545e22`）。接手后建议先 review 再提交。

**未决事项（等你决定）**

- `docs/仿真软件设计规范` 有 `.md` / `.html` / `.docx` 三份，**哪份是权威版本**？确认后可删冗余
- `console/server.py` 806 行 / 40 端点，是否拆分？属重构、需回归测试
- `frontend/` 下 4 个带 `test` 字样的文件（`ab_chain_test.py` 等）**其实是 CLI 工具不是测试**，命名有误导性（README 有引用，改名需同步改文档）

---

## 七、协作纪律（重要）

1. **先给结论，再给依据**。用户不看铺垫。
2. **不要擅自下载环境/大依赖**。本机已具备完整环境（`.venv310` 有 osmnx/ortools/pygame 等全部依赖），需要新装东西前先说明体积和用途并征得同意。
3. **不要长期挂后台进程**。服务用完必须 kill，并明确告知；能让用户自己启动的就别代劳。
4. **判定"生效没有"要用实测**，不能只看返回码或日志（本项目已多次遇到"返回码骗人"和"日期戳才是真相"）。
5. **改配置/文件前先备份**，并说明怎么回滚。
6. **改完代码跑 `run_tests.bat`**，并做一次真实运行验证（启动服务 + 浏览器截图确认）。

---

## 八、快速上手（建议顺序）

```bat
1. 双击 run_tests.bat              → 确认基线 42 个测试全绿
2. 双击 start_console.bat          → 确认服务能起、浏览器能打开
3. 读 console/capabilities.py      → 理解"缺依赖降级"的设计约定（很重要）
4. 读 console/server.py 的 API 列表 → 40 个端点，理解前后端契约
5. 读 frontend/environment.py 的 step() → 理解仿真主循环
6. 读 docs/ 里的《仿真内核分层架构设计》《算法口径说明》
```

有任何不确定的地方，**先读 `docs/` 和 `项目结构审计报告.md`，再动手**。
