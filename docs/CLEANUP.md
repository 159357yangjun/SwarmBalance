# 2026-11-01 第一轮清理记录（历史）

本文描述模块化前的清理；当前结构见 [ARCHITECTURE.md](ARCHITECTURE.md)，本轮迁移见 [MIGRATION.md](MIGRATION.md)。

整理前基线提交：`2261fea`。整理时工作区无已有 Git 修改。修改留在工作区，未提交或推送。

## 删除的过时代码

| 文件 | 依据 |
|---|---|
| `console/_rewrites.py` | 历史 Git 对象改写报告生成器；调用入口 `_citations.py`、文档和配套测试已删除，运行时代码无引用 |
| `console/_rowsets.py` | 已作废算法产物的行集合/引用门禁；原消费者已删除，当前无引用 |
| `console/phase1b2_timestep_probe.py` | 历史 G12 子进程探针；配套测试与登记流程已删除，当前无引用 |
| `console/_preflight.py` 的测试专用部分 | 旧测试发现、skip 统计、测试模块加载与全局字节码设置；当前唯一调用方只需要运行时依赖检查 |

这些内容可从基线提交的 Git 历史恢复。没有执行 `git clean`，没有删除虚拟环境、用户场景、本地历史项目、地图、风场、来源表或第三方库。

## 归位与统一

- `config/config_loder.py` → `config/loader.py`：修正拼写，同步全部仓内导入；配置加载实现保持不变。外部脚本如曾导入旧名称，需改用 `config.loader`。
- `console/_preflight.py` → `console/dependencies.py`：只保留评测使用的真实导入检查、虚拟环境定位及缺依赖返回码 3；不再更改全局字节码策略。
- `console/zip_range_extract.py` → `tools/zip_range_extract.py`：工具实现不变，更新忽略规则内说明。
- 根目录 `requirements.txt` 保留原有全部固定版本；子模块依赖通过 `-c ../requirements.txt` 共享版本约束，不再另写宽松版本。
- 重写 README、内核/算法模块导航，增加实际架构和目录说明；区分目标功能、已接入功能与独立实验代码。
- 修正静态目录指引中已删除的 TaskUI 前置要求；浏览器页面及 vendor 文件未修改。
- 清理 `.gitignore` 中对不存在证据目录/工具的说明，同时保留对本地遗留数据的忽略保护。

## 保留内容与原因

`frontend/` 与 `backend_si/` 保持目录名称和算法职责，避免改变导入/热重载语义。两个 `matching.py` 存在边界处理差异；独立评测入口仍可使用；货物交接、只读观测与公开适应度类仍有明确用途或导出接口，不能仅因未接入 Web 就判为废弃。

`data/provenance/` 保留为历史登记，并说明生成器已移除、不能复现为当前实验；第三方原始 README 和许可证不改写。`results/mvp/` 中已有 JSON 属用户数据，保持原样。

## 验证范围

配置与依赖检查增加 5 项回归测试，重构前后均通过。另对 Greedy、PSO、GA、OR-Tools 使用相同 seed、真实地图和固定注入任务，各推进 6 步，对比无人机、任务和统计数据；清理前后序列化结果 SHA-256 相同。

已通过的其他检查：

- `console.selfcheck --steps 12`：真实地图、任务注入、Greedy 推进、检查点恢复。
- 6 个 CLI 的 `--help`：控制台、统一评测、GA、PSO、OR-Tools、Greedy。
- GA CLI 真实 2 步评测，CSV 输出至项目外临时验证目录；README 的根目录命令已补齐 `--osm` 路径。
- 临时独立端口启动真实 HTTP 服务：页面、地图实验室脚本、三个 vendor 文件、算法/元数据、两类配置、场景库、空对比数据、重置、快照和静态地图；验证后关闭临时服务。
- Python 源码语法解析、`pip check`、两个子模块依赖的离线 dry-run、`git diff --check`。
- 独立只读代码审查：未发现严重或重要问题。

整理中定点删除了旧配置模块的 `config/__pycache__/config_loder.cpython-310.pyc`，保留其余缓存、`.venv310` 和地图解析缓存。评测与 Web 验证未写入项目配置、用户场景或历史结果。

这次整理不声明全量算法正确性、性能提升或科学模型有效性。批量实验框架、历史大规模测试和历史结果未恢复。
