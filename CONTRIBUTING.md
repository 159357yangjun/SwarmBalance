# 贡献指南

感谢你参与 SwarmBalance（群智优衡）项目！这份文档说明协作方式与代码约定。

---

## 一、环境准备

**Python 必须是 3.10**（`osmnx==1.9.4` 限制），安装顺序不能反：

```bash
python -m venv .venv310
source .venv310/bin/activate          # Windows: .venv310\Scripts\activate
python -m pip install "pip==23.3.2"   # pip 26.2.x 在 Windows 有 safe-delete bug
pip install numpy==1.26.4             # 必须先钉！否则 ortools 会把它升到 2.x 弄坏 osmnx
pip install -r requirements.txt
```

验证：

```bash
cd frontend
python evaluate_metrics.py --policy greedy --episodes 1 --episode-steps 200
```

---

## 二、分支规范

- `main` 为稳定分支，**受保护**，不直接推送；
- 开发分支用**不带斜杠**的短名（某些权限环境下 `feature/xxx` 这类带子目录的引用创建不成功）：
  - 功能：`chain-opt`、`nest-arbitration`、`console-ui`
  - 修复：`fix-empty-ratio`、`fix-chain-append`
  - 文档：`docs-readme`
- 分支从 `main` 拉起，完成后提 PR 合并。

---

## 三、提交信息

采用 `类型: 简述` 格式，类型限定：

| 类型 | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `perf` | 性能优化 |
| `refactor` | 重构（不改变外部行为） |
| `docs` | 文档 |
| `test` | 测试 |
| `chore` | 构建 / 依赖 / 配置杂项 |

示例：

```
feat: 禁飞区接入 A* 路径规划实现真绕飞
fix: 送达即卸货，修复任务链被载重检查锁死
```

---

## 四、代码约定

### 指标改动（最容易踩坑）

新增或修改评估指标时，**只允许改 `frontend/metrics_schema.py`**：

1. 在 `METRIC_COLUMNS` 加列；
2. 在 `_STAT_KEY_MAP` 补 `列名 → Environment.get_statistics()` 的 key；
3. 若绘图脚本需要新图，同步 `results/plot_compare_metrics.py` 的 `COLUMN_ALIASES`。

**不要在 `evaluate_metrics.py` / `run_pso.py` / `run_ga.py` 里另起表头**——历史上正因如此出现两套互不相通的
CSV 口径，导致汇总脚本 `KeyError`。表头不兼容时 `metrics_schema` 会自动备份旧文件，不会静默覆盖。

### 物理口径

任何涉及时间、距离、耗电的改动，必须与既有口径一致：

- 1 env-step = 1 秒；
- 距离用投影平面坐标（米）；
- 耗电 `base × 距离 × (1 + penalty × 载重比)`；
- 低电量阈值 `battery.capacity × 0.2`，换电 180 秒。

改动机型参数请同步 `config/simulation.json` 与 `backend_si/config.yaml` 的兜底值。

### 配置改动

改 `config/simulation.json` 后，**必须 reload 模块才生效**——
`drone` / `task` / `charging_station` / `environment` 在模块顶层把配置固化成了常量。
Web 控制台走 `console/sim_session.py::reload_sim_modules()`，命令行直接重启进程。

### 通用

- Python 代码保持 4 空格缩进，注释与文档用中文；
- 新增调度器请继承 `frontend/scheduling_interface.py` 的 `Scheduler` 抽象基类；
- 新增数据源请继承 `DataSource`，实现 `load_drones` / `load_nests` / `load_tasks` / `build_task_source`；
- 不要提交 `.idea/`、`.venv*/`、`results/compare/*.bak-*`（已在 `.gitignore` 中）。

---

## 五、Pull Request 流程

1. 从 `main` 拉分支；
2. 完成改动并本地验证（至少跑通一次 1 episode 短评测）；
3. 提 PR，描述里说明：
   - 改动动机（对应申请书哪一条 / 解决什么缺陷）；
   - 影响的指标（贴出改动前后的关键指标对比）；
   - 是否改变实验口径（若改变，需说明历史结果是否仍可比）；
4. 至少 1 人 review 通过后合并；
5. 合并后删除分支。

**若改动影响指标口径**，请在 PR 中明确说明，并在 `算法口径说明.md` 同步更新，
否则历史实验数据将失去可比性。

---

## 六、报告问题

提 Issue 请附上：

- Python 版本、操作系统；
- 复现命令与完整报错；
- 相关配置片段（`config/simulation.json` 中改动过的部分）；
- 若是算法结果异常，附 `results/compare/*.csv` 中对应行。
