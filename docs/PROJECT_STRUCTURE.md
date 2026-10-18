# SwarmBalance｜主分支项目结构与真实入口

本页为**代码和研究材料导航**，不是新架构规范。主分支必须只有一份可检出的完整源树；原始研究 Git SHA、失败证据和历史结果仍可追溯。

| 路径 | 当前作用 / 权威入口 | 维护原则 |
|---|---|---|
| `frontend/` | 历史命名的 Python 仿真内核、无人机动力学和状态推进；并非现代 Web 前端 | **不要按字面搬家**，许多 Python import、测试及 E0/E1 证据依赖该路径 |
| `backend_si/` | Greedy 相关配置及 GA/PSO/OR-Tools 算法实现 | 维持算法基线，变化时单独比较 |
| `console/` | FastAPI、`SimSession`、旧 2D/3D 场景控制台及 HTTP 服务 | `python -m console.run`；独立于实验脚本 |
| `experiments/` | Run 管理、统计报告、`reproducibility.py` 来源清单和固定预设 | 旧 E0/E1 不原地重写 |
| `config/` | `simulation.json` 以及场景输入和固定默认值 | 单一明确默认来源，禁止 CI 或 demo 悄然覆写 |
| `data/` | OSM/样本/公开资料元数据；`research_r2_sources.json` **只代表来源准入审计** | 原始数据的许可、文件 SHA-256 与派生量分开 |
| `results/` | 保存历史实验/对比/出图证据 | 将 `results/adhoc/` 与冻结结果分开，不覆盖已引用成果 |
| `scripts/` | 科研复现实验和故障条件验证脚本 | 只把真正执行的结果称为通过 |
| `docs/` | 方法、审计与研究结果证据；入口见 `docs/research/README.md` | 文献与证据不冒充程序实现 |
| `paper/` | 论文及图表 | 不凭测试自动重写科研结论 |
| `.github/workflows/` | 遗留分阶段 CI、复现性及约束性检查 | 历史工作流保留事实，后续按真实使用裁减 |

## 两类能被实际运行的入口

- 原有交互仿真：`python -m console.run`，浏览器 `/`；具有旧控制台的地图/状态/任务交互。
- 无 UI 单次科研运行：例如在 `frontend/` 下 `python evaluate_metrics.py --policy ga --episodes 1 --episode-steps 600 --seed 100`；默认使用 `results/adhoc/`，不可未经授权覆盖 `results/compare/`。

## 当前代码线的边界

- 本次研究整合源：`logic/l1-task-lifecycle-delivery-proof-v1@f1bf21cc42f2566b2981a1a6092cbedf215db809`，含 P1/P2 研究链及 L1 配送生命周期修复。
- `mvp01-backend` 的本地项目 API 和 `mvp01-integration` 的表单工作台来自旧 `master`，与研究修复代码**尚未共同运行验收**；因此本批不以 UI 通过 8/8 冒充研究集成成功，也不把不符合产品目标的界面作为强制主线。
- 既有 `platform/arch-*`、`platform/contract-*` 是设计和审查草稿，不是新的可执行 Harness。源分支保留追溯，主分支研究合入无需把全部草稿搬进产品代码。

## 结构调整规则

旧路径被 README、Python imports、结果哈希、历史实验或源码行号引用时，**先提供迁移兼容性证明，再移动**。本次先建立可用目录导航与研究索引，清理使用入口，不进行会使数据来源记录和运行脚本失效的大规模重命名；并非宣称已经完成全面重构。
