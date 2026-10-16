# CONTRACT-02｜Component Failure & Compatibility Test Cases

> **状态：设计级契约用例（NOT EXECUTED）**。目标是为未来实施提供可转成 pytest/fixture 的判据；没有运行 Harness 代码、CI、真实物理或 legacy parity 测试。本轮 PR 仅交付 Markdown。合同版本、异常分类、AI-A 的 event/clock 字段均未冻结。
> 输入固定 HEAD：#54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`、#47 `68382c649393057ffbf5a14508ab1ff72d575b09`、#49 `d155621aca66e3a80c388718093a452d17d71e10`、#50 `c4c0c67111ead435062650c1ed776547c477e3e3`、#46 `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048`、#51 `f2df96bc609ee1e430ea6eff2456c4577347c300`。基础 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`。

## 1. Contract test harness 的规范设置（future implementation）

Fixtures 不得通过现有 `frontend.Environment` 假装实现新 Harness。提供一个纯测试的 `RunFixture`：冻结 `world/scenario/assembly digests`、`run_id`、`generation`、`revision`、只读 state、`view_token`、provider registry 与临时可回滚 B/C/D/RNG；用显式 deterministic fake providers 验证协议。时间和事件含义只注入 **AI-A 冻结之后** 的 `ClockFixture/EventEnvelopeFixture`，不能私设 phase/priority/tie-break。

每个 fixture 必须记录：`case_id, contract_version, effective_assembly_digest, provider_digest, input_digest, initial_revision, expected_outcome, actual_outcome, failure_code, failed_operation, committed_revision, world_state_digest_before/after, queue_digest_before/after, rng_cursors_before/after, private_state_digest_before/after, trace_digest, test_command, code_sha`。**当前 actual_outcome=NOT_RUN**，绝不填 PASS。摘要使用版本化 canonical serializer，禁止将演示占位 digest 当真实内容哈希。

验收原则：`REJECT_COMMAND` 表示 proposal/指令整体拒绝，且不得出现部分 B/C/D 提交；`FAIL_RUN` 保存上次已提交 revision 后进入 FAILED；`FAIL_INIT` 不允许 READY/revision 0 发布；`MARK_METRIC_UNAVAILABLE` 不回滚 postcommit；`TAINTED` 用于 Legacy opaque 不可安全继续的 worker。最终错误码别名及 severity 由 ARCH-02 会签。

## 2. B02 行为/模式用例矩阵（全部 NOT_RUN）

| ID | 夹具输入/注入 | 期望诊断和不可变断言 | 分类 |
|---|---|---|---|
| C02-01 | 有效 `ObservationV1`，Scheduler.propose 返回合法派单；Dynamics.propose 返回有限 Wh/运动提案 | staged dispatch 被 Dynamics 视图看到；只有 Harness commit 后 revision +1，Metric 只见 postcommit；从无直接组件 state write | POSITIVE |
| C02-02 | Scheduler 只实现 `decide(WorldView,ClockView)` 不实现 `propose` | `CAPABILITY_MISSING/CONTRACT_VERSION_MISMATCH`，assemble REJECT；不能自动猜 method | NEGATIVE |
| C02-03 | Dynamics 只实现 `advance(interval, view)` 不实现 `propose` | 同上，不能绕过单一 `StateDeltaProposal` | NEGATIVE |
| C02-04 | `ObservationV0`，或直接把旧 `SCHEMA_VERSION="1.0"` dict 当 `observation.v1` | `CONTRACT_VERSION_MISMATCH`；拒绝而非同名强行转换 | NEGATIVE |
| C02-05 | Scheduler 的 observed_revision 等于当前，但 `view_token` 来自上一 stage/generation | `STALE_OBSERVATION`；B/C/D/RNG 不变 | NEGATIVE |
| C02-06 | Dynamics 收到 predecision view_token（没有在派单暂存后更新） | `STALE_OBSERVATION`；不接受不一致的阶段视图 | NEGATIVE |
| C02-07 | `ActionProposal` actor 未知 ID / 用 `drone_index=0` 代稳定 EntityId | `ENTITY_REFERENCE_INVALID`，无任何任务 assignment | NEGATIVE |
| C02-08 | 派同一任务给两架机、超载、机巢 lease 超容量、引用已交付任务 | `INVALID_ACTION/RESOURCE_VIOLATION/STATE_CONFLICT`；整体拒绝，货权/leases/电量不部分变动 | NEGATIVE |
| C02-09 | Action 带未知 kind/未授权 capability/动态读取可变 Environment | `CAPABILITY_MISSING/INVALID_ACTION`；拒绝；无旁路写入 | NEGATIVE |
| C02-10 | Dynamics 输出 NaN/Inf、`energy_consumed_wh<0`、消耗后电量小于零 | `NONFINITE_VALUE/INVALID_STATE_CHANGE`；FAIL_RUN，revision/clock/queue/RNG/D 保持 fence | NEGATIVE |
| C02-11 | Dynamics 提案正常同时私自修改 Drone.battery，或模型与 Harness 双重扣电 | 侦测未授权写入，`COMPONENT_SIDE_EFFECT`，strict REJECT/FAIL_RUN；禁止部分 commit | NEGATIVE |
| C02-12 | Dynamics `service_fact` 缺服务/货权证据，仅接近 dropoff 坐标 | `INVALID_STATE_CHANGE`，不允许 delivered，cargo custody 不丢 | NEGATIVE |
| C02-13 | 不同 World/Scenario Ref、位置坐标 CRS 未声明、路程 km 冒作 m、assigned_mass 代替 onboard_mass | `ENTITY_REFERENCE_INVALID/CRS_MISMATCH/UNIT_MISMATCH/MODEL_ASSUMPTION_CONFLICT`；无默认转换 | NEGATIVE |
| C02-14 | Scheduler 返回合法空 actions tuple | 明确 no-op，非异常；后续 phases 及 world 约束照常运行 | POSITIVE |
| C02-15 | EventProvider 返回有意图但带旧式 `at_seconds/priority_class` 非规范 envelope | 等 AI-A 冻结映射；无映射或版本不合时 `CONTRACT_VERSION_MISMATCH`；不可私自排事件 | BLOCKED BY AI-A |

## 3. B06 rollback/checkpoint/私有 D 用例（全部 NOT_RUN）

| ID | 夹具输入/注入 | 期望判定/可观测断言 |
|---|---|---|
| C06-01 | Scheduler 在消耗两次 `scoped_rng` 后抛异常，内部 staged warm-start 已变化 | 丢弃 B/C/queue/RNG/D，last committed revision 不变，按冻结策略 `COMPONENT_EXCEPTION`→FAILED；绝不下一步偷偷使用新 warm-start |
| C06-02 | Dynamics 在部分生成 delta 后抛异常；先前已暂存合法 scheduler action | 丢弃整个 boundary，不存在“派单成功但物理失败”权威状态；Model failure FAIL_RUN |
| C06-03 | Transactional scheduler `prepare_commit` 抛异常 | 所有组件执行 abort，未发布 B/C/D，旧 private digest 与 RNG cursor 不变，FAIL_RUN |
| C06-04 | Transactional component 的 `publish_prepared` 可抛异常，或写外部文件/发消息且不可撤回 | strict assemble 阶段 `COMPONENT_RECOVERY_UNSUPPORTED`；不得到 commit 时才宣称可恢复 |
| C06-05 | Component 描述 `checkpoint_supported=false`，Run `required_checkpoint=true` | `COMPONENT_RECOVERY_UNSUPPORTED`，FAIL_INIT；不产生 READY |
| C06-06 | Component 描述 `rollback=false` 或 RNG cursor 不能恢复，Run `strict_transactions=true` / `retry_enabled=true` | FAIL_INIT；禁止隐式降为 best-effort transaction |
| C06-07 | `PURE` 标注组件实际保存改变下一次结果的优化器种群/全局缓存 | 检测 purity violation，拒绝 strict assembly 或实测 FAIL_RUN，不允许空 D checkpoint |
| C06-08 | checkpoint 私有 schema / component digest / config digest / run generation 不相容 | `CHECKPOINT_INCOMPATIBLE`；禁止任何 partial restore，保留之前 run 的权威状态 |
| C06-09 | restore 后同一 pinned input 的 event/state/private/RNG trace 不等 | `REPLAY_MISMATCH`，证据为 FAILED，不得标 strict reproducible |
| C06-10 | `reset` 于 FAILED 之后，新 generation 重建；旧 generation 持有旧定时 intent | 不接收旧 event/旧 view token/旧 RNG stream；新 state revision 0；旧 result 不被改写 |
| C06-11 | init 在第 3 个 provider 抛异常 | 逆依赖 close 1–2（以及部分第 3 个）且 close 幂等；没有 revision 0 / READY |
| C06-12 | MetricProvider.observe 在 boundary commit 后异常/中途失败 | 保留已提交 revision 与完整 B/C/D；样本 explicit missing/partial，不能把 null 写 0；`MARK_METRIC_UNAVAILABLE` |
| C06-13 | provider 合作式超时，能干净 cancel + abort D/RNG | 记录 `COMPONENT_TIMEOUT`，不提交部分状态；严格测试必须证明 cleanup；无强制线程 kill 宣称 |
| C06-14 | noncooperative provider 卡死或有进程外副作用 | 没有受控 worker 隔离/kill 时 `TIMEOUT_ENFORCEMENT_NOT_GUARANTEED`，拒绝要求 hard timeout 的装配；不宣称可 rollback |
| C06-15 | 重试同一个请求，第一次 rollback，第二次执行 | 两次输入/版本/token/seed 与 B/C/D/queue 完全一致；仅预批准、bounded、无副作用操作可重试；否则 FAIL_RUN |
| C06-16 | 修改 task 生成子流的全局 np.random，再重试 scheduler | `DETERMINISM_UNSATISFIED`；strict mode 装配拒绝，证明 run/组件之间无共享流 |
| C06-17 | warm-start 优化器队列不暴露 checkpoint，`reset()` 无法清理 | strict REJECT；fresh instance 可替代 reset 仅当依赖、资源、seed 校验等价，否则 FAIL_INIT |
| C06-18 | postcommit logger/export 写盘失败 | 不回滚已提交 world，`MARK_EVIDENCE_INCOMPLETE`；若证据为 hard requirement 按 FrozenRunSpec 标记 run 不合格 |
| C06-19 | `close` 两次，第二次时底层资源已释放 | close 幂等；cleanup 出错另报 `CLEANUP_FAILURE`，不覆写原 terminal reason |

## 4. Legacy 兼容性/污染负例（全部 NOT_RUN）

| ID | 条件 | 预期结果 |
|---|---|---|
| LEG-01 | greedy 时把原 `greedy_action_from_observation(obs)` 替换为 `scheduler.step(obs,time)` | parity golden 首分叉即 FAIL；禁止为了接口统一改旧路径 |
| LEG-02 | GA/PSO/OR-Tools 用 `optimize` 直接替代既有 scheduler.step | FAIL parity；warm-start、排队/排序状态差异必须显式记录 |
| LEG-03 | 同一次 Legacy step 调用 env.step 两次 | 拒绝；step/time/任务流/电量不可出现双推进 |
| LEG-04 | 原 observation 在本轮重排 drone list，而 adapter 复用上一轮 index→EntityId 表 | `LEGACY_OBSERVATION_UNMAPPABLE`；不得随便派任务到错误实体 |
| LEG-05 | Legacy 观察缺可行 mask、route 单位不明、充电站/货权字段缺失 | strict facade `CAPABILITY_MISSING/LEGACY_OBSERVATION_UNMAPPABLE`；不得补假数据；允许隔离 legacy worker 原始运行 |
| LEG-06 | OR-Tools 不可用/算法 unknown，legacy SimSession 可能默认回 Greedy | 新受控 adapter REJECT + diagnostic，不可静默将模型身份改成 Greedy；原 legacy_direct 保留现状 |
| LEG-07 | env.step 完成部分 Drone 更新后抛异常、进程 RNG 已消耗 | `LEGACY_OPAQUE_STEP` worker `TAINTED/FAILED`；禁止继续 step/claim checkpoint，销毁后新 worker 基于 pinned inputs 重启 |
| LEG-08 | 旧 SimSession deepcopy checkpoint 被当作新 portable checkpoint 或跨 generation 恢复 | `CHECKPOINT_INCOMPATIBLE`；保持旧路径原有单进程语义 |
| LEG-09 | legacy worker 改全局 `SWARM_BALANCE_SIM_CONFIG`，两个 run 同进程交织 | 违反 isolation；strict/multi-run REJECT；每个 legacy run 独立 worker |
| LEG-10 | adapter 自行修复旧“当前载重”/风符号或重算 stats | K1 首差定位并 FAIL；不允许借适配更改 physics/指标 |
| LEG-11 | parity sidecar 修改历史 `results/compare/*.csv`、旧 manifest 或 `compare_gate.py` | 旧源 SHA 必须未变，否则 G-M0/G-M6 FAIL；旧文件永远只读 |
| LEG-12 | 仅凭相同 seed 宣称旧/new 动作、模型和比较结果等价 | 拒绝结论：必须 engine SHA、配置/map/算法 digest、时序、RNG、模型与指标口径通过门禁 |

## 5. 测试执行伪代码（建议给未来实现方）

```python
# PSEUDOCODE ONLY — NOT executable in current repository
def test_scheduler_rng_and_private_state_rollback(strict_harness):
    run = strict_harness.assemble("frozen-run", scheduler="fault_after_rng")
    before = run.fence_digests(["world", "clock", "queue", "rng", "private_D"])
    outcome = run.advance_boundary()
    assert outcome.failure.code == "COMPONENT_EXCEPTION"
    assert run.state == "FAILED"
    assert run.fence_digests(["world", "clock", "queue", "rng", "private_D"]) == before

def test_checkpoint_unsupported_must_fail_before_ready(resolver):
    run = resolver.assemble({
        "strict_transactions": True,
        "required_checkpoint": True,
        "scheduler": {"checkpoint_supported": False}
    })
    assert run.rejected
    assert "COMPONENT_RECOVERY_UNSUPPORTED" in run.errors
    assert not run.has_published_revision_zero

def test_legacy_partial_mutation_taints_worker(isolated_legacy_worker):
    isolated_legacy_worker.inject_fault("after_partial_env_mutation")
    result = isolated_legacy_worker.step_once()
    assert result.status in ("TAINTED", "FAILED")
    assert not isolated_legacy_worker.can_continue
    assert not isolated_legacy_worker.can_export_trusted_checkpoint
```

以上只是预期断言，不是测试通过的日志。真实 Python 测试要独立实施 PR 并对齐实际产物和 CI 环境。若某 fixture 无法从现有 API 观测 private D/RNG digest，不能“用 world snapshot 没变”替代 D/RNG 恢复证明，应补测试钩子或保持 BLOCK。

## 6. 阶段门和会签阻断

| Gate | 必须证据 | 当前状态 |
|---|---|---|
| D0：设计交付 | 本目录三 MD、完整 input SHA、Protocol/schema、负例、文件白名单、Draft PR | 待交付核查 |
| D1：ARCH-02/03 统一接口 | 唯一 `propose` API、ReadView token、Dynamics stage、拒绝错误映射和字段级兼容 | PROPOSED / NOT SIGNED |
| D2：AI-A 事件和时钟 | EventEnvelope/BoundaryRef/Phase 及同刻事件/时钟舍入/commit 粒度 | BLOCKED / AI-A OWNER |
| D3：AI-C RNG | Seed plan、stream key、cursor rollback、paired run 规则 | BLOCKED / AI-C OWNER |
| D4：ARCH-04 Legacy | 两条路由、worker isolation、opaque failure + K1 golden parity | PROPOSED / NOT EXECUTED |
| D5：可执行合约与 CI | C02-01..15、C06-01..19、LEG-01..12 转成真实 fixture 执行、日志/工件 | NOT_RUN |
| D6：主控准入 | 跨组会签 + 独立审查 + ADR ACCEPTED + ARCH-06 | HOLD / NO-FREEZE |

当前计划共 **46** 条场景（15 + 19 + 12），均为设计预期而非已经通过。不得因为 PR 成功创建而将 G-ARCH-3/B02/B06 标为通过。

## 7. 交付核查指南

用 GitHub API 核验此 PR 实际 HEAD + base SHA、Draft 状态和改变文件集合；预期仅以下三文件：
- `docs/platform/architecture/contracts/contract-02/COMPONENT_RUNTIME_CONTRACT.md`
- `docs/platform/architecture/contracts/contract-02/PROPOSAL_AND_OBSERVATION_SCHEMA.md`
- `docs/platform/architecture/contracts/contract-02/COMPONENT_FAILURE_TEST_CASES.md`

以 `git diff --name-only <base>...<head>` 或 GitHub changed-files 列表核对不出现旧源码、其他设计、旧数据或主线变更。所有评论和下一步决策由主控按治理协议更新，不在此 PR 修改共享治理台账。

## 8. CONTRACT-01 × CONTRACT-02 横向收敛测试追加（全部 NOT_RUN）

已在 [TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md](TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md) §7 追加 **XW-01..XW-14（14 项设计用例）**，覆盖 `ProposalHeaderV1` 身份映射、`Action/StateDelta→ChangeSet` typed reducer、`EventSpec/Intent→Envelope` exact-ns conversion、同刻服务事实不倒灌、whole-boundary D/RNG rollback、合法 `record_and_skip` 仅在 commit 后消费、postcommit partial 及 Legacy TAINTED。加上原 46 项，现有 CONTRACT-02 **共 60 项设计测试描述，实际运行 0 项**。原测试表里的 `STALE_OBSERVATION` / `COMPONENT_RECOVERY_UNSUPPORTED` 为原有局部诊断名称，最新 `FailureRecord` 归一规则见收敛文件 §5；不可把诊断别名混作额外成功结果。

Cross-PR input: #58 `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377`、#56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`、#57 `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`、#59 `28daf1e336a1447b098b4d6fa044095b7caa1f4f`、#60 `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`。任何后续源 HEAD 改变须独立增量复审，不允许在此 PR 标为测试通过。
