# 已纳入主线的研究成果与证据边界

本页区分 **研究/工程已证明的行为** 与 **仍然只是问题、假设或资料**。整合历史来源 SHA 是为了防止把不同版本的结果混写，不代表所有论文推断均已验证。

## A. 作为主线源代码及可核对研究证据保留

| 研究主题 | 对应原始成果（本次采用的代码来源） | 实际已完成内容 | 不应声称 |
|---|---|---|---|
| P1 固定任务到达、配对和压力实验 | L1 累计祖先 P1-B，`docs/P1_B_*.md`、`docs/evidence/P1_B_PAIRED_*` | 具名实验计划与配对数据、复现相关代码 | 所有处理组必然具备独立现实参照 |
| P2 低电量/换电/安全行为 | L1 累计祖先 P2.1～P2.4 B1～B4e，`frontend/drone.py`、`frontend/environment.py`、`scripts/test_p2_*.py` | 电量报价/扣除、机巢可达性、充电改道、风变化后的故障场景与正反用例 | 静态单元测试已经证明真实飞行能耗正确 |
| P2 载货责任与失败恢复 | L1 累计祖先 B5a～B5g，`console/custody_*.py`、`docs/P2_4B_B5_SECURITY_AND_RESEARCH_GATES.md` | 托管日志/事务记录/SQLite 本地对账等实验实现与测试 | 队列和外部世界已拥有单体 ACID 事务或真实货权认证 |
| L1 配送生命周期 | `logic/l1-task-lifecycle-delivery-proof-v1@f1bf21cc42f2566b2981a1a6092cbedf215db809`、`docs/logic-audit/L1_DELIVERY_LIFECYCLE_FIX.md` | 未取货拒绝伪完成、真实送达更新任务终态；历史 RED 与 GREEN 可核 | 全局状态机、恢复、超时率定义全部无缺陷 |
| R1 能耗量纲与模式溯源 | `research/r1-energy-units-and-accounting-provenance-v1@2635141845efaf8e631bf54b16a63f5133982ae5`、`docs/RESEARCH_R1_ENERGY_UNITS_READINESS.md` | 记录 requested/effective energy_accounting_policy，保留模型单位及来源边界 | 由厂家航程反推得到实机标定 |
| R2 真实数据可用性 | `research/r2-flight-data-source-feasibility-v1@f52111df94c5acd98dc8d9565c8a27bd1abfbd3c`、`data/research_r2_sources.json`、`docs/RESEARCH_R2_SOURCE_FEASIBILITY.md` | 公开原始来源、许可和第三方摘要差异；明确未取得原始飞行数据 | 已经完成 DJI/PX4 实机校准 |

**L1 主线累计代码版本的 GitHub workflow:** `SwarmBalance verification` 在 L1 HEAD 上成功。具体时间、测试范围和跳过项须查看相应 Actions 记录；一个 CI PASS 不等于所有研究假设成立。R1/R2 的本批整合增量须由当前候选版本的 CI 和专项目录检查重新确认。

## B. 未作为稳定科研结论合入

1. 9 条 P1/P2 分叉实验含与累计主线不同的独有提交，当前**不把多个互斥实现全部覆盖到一个代码文件**；对它们保留原始 SHA 与分支以供后续单独甄别。
2. ARCH-01～06、CONTRACT-01～05、EXP/VVE 等 PR 的主要交付是设计文本，且 ARCH-06 仍 NO-FREEZE；不把静态契约文档当作已完成的可执行研究。
3. `mvp01-workbench` 的功能链路虽然可运行，但产品形态尚未达到用户的专业仿真工作台目标，不作为本次“严谨研究成果”自动合入。

## C. 与真实世界比较的红线

- 程序执行和单元测试属于软件行为核验；飞行物理模型的绝对精度必须通过有型号和工况约束的原始飞行日志检验。
- E0/E1 与原有 `results/compare/` 的字节和引用语义必须保持，不允许为了取得好看的指标而静默改写。
- 旧报告若与当前源码算法、任务数量、统计分母不同，必须按原 HEAD 保留为历史事实，不升级为当前性能结论。


## D. 原始实验结论索引（保留发现，不把替代实现直接合入）

下列成果源于旧支线上**具名固定 HEAD、GitHub Actions 和/或冻结数据档案**。整合主线时保留已证实的研究发现和追溯入口，而不无条件合入互斥、未共同复核的代码。历史数据不是当前 `master` 上新跑得到的同一批样本。

| 发现及意义 | 直接证据 | 正确解读 / 仍未证明 |
|---|---|---|
| P2.3：常规三档压力实验 30 对 seed 中，旧代码能量短缺航段为 **0**；引入低电可行性门后，这批场景的观测指标差异全为 **0** | [PR #10](https://github.com/159357yangjun/SwarmBalance/pull/10)，源 HEAD `a2be17f061b01a55038eb91d95aea6ab270462f9`，冻结配对数据档案和 ZIP SHA 在 PR 记录中 | **没有触发条件 ≠ 修复无效，也不能证明欠电情景安全**；不能拿零差异替代针对性测试 |
| P2.3b：隔离的强制耗尽、低电触发条件可被构造并观察 | [PR #11](https://github.com/159357yangjun/SwarmBalance/pull/11) [专项成功工作流](https://github.com/159357yangjun/SwarmBalance/actions/runs/38033007846)；[PR #12](https://github.com/159357yangjun/SwarmBalance/pull/12) [专项成功工作流](https://github.com/159357yangjun/SwarmBalance/actions/runs/38034128308) | 证明原三档未覆盖的边界能够被触发，**不是**对常规订单损失、机型安全或现实能耗的统计估计 |
| P2.2：G2 能耗门曾存在源码变更对真实行为的检查混淆，随后定位并修复 | [PR #13](https://github.com/159357yangjun/SwarmBalance/pull/13)，[诊断工作流](https://github.com/159357yangjun/SwarmBalance/actions/runs/38036706534) | 此 PR 是有价值的**历史诊断证据**，其旧候选补丁不得覆盖后续修复；保留原因链，不将诊断分支合并成第二套生产实现 |
| P1.5：保存早期 P1 实验的 ZIP 校验、证据引用与哈希清单 | [PR #8](https://github.com/159357yangjun/SwarmBalance/pull/8)，源 HEAD `1a47f07cc83243e6a345b9857c8cff156aeed73d` | 历史快照和外部档案位置有记录，但**不能把外部存储的存在当成仓库内已持有原始字节** |
| B4b/B4c、B5d/B5e：存在并行的自动充电站身份、风偏移、持久交接日志/事务实现 | [PR #21](https://github.com/159357yangjun/SwarmBalance/pull/21)、[#22](https://github.com/159357yangjun/SwarmBalance/pull/22)、[#30](https://github.com/159357yangjun/SwarmBalance/pull/30)、[#32](https://github.com/159357yangjun/SwarmBalance/pull/32) | 这些是与累计主线分叉的替代实现，可能含单独测试证据；**未获得跨候选行为/兼容性判定前不合入**，也不删除原分支 |

> 审计口径：`master` 保留已通过集成的累计实现与研究证据；对历史尚未被完整集成的研究结果，**保留结论、固定来源及其局限**；对于只证明一个负例/诊断的内容，不把独立实验代码硬并进生产执行器。需要新的生产实现时须有针对当前主线的可复核运行证据。
