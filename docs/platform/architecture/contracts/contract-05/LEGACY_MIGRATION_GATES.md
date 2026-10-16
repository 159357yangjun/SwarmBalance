# CONTRACT-05 — Legacy Migration Gates and Reversal

> ARCH-04 (#50) companion to implementation M0–M5. **PROPOSED / no executed parity or rollback test in this document**. The current original code, configurations, tests, CSV and recorded E0/E1 experiments are scientifically immutable input, not auto-upgradable platform objects. Existing default remains `legacy_direct`. Do not merge or rewrite prior PRs to make parity appear easier.

## 0. Baseline boundaries (separate research strata)

- **L-A:** `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`, as designed by PR #50. Source hashes include real `frontend/` Python simulation engine (not web frontend), `console/sim_session.py`, `console/server.py`, `experiments/runner.py`, `experiments/worker.py`, `results/compare_gate.py`, `frontend/metrics_schema.py`, OSM/parser mode, config and raw data, dependency lock and old comparison manifests.
- **L-B:** lifecycle/terminal/custody fixes in **unmerged** PR #41 HEAD `f1bf21cc42f2566b2981a1a6092cbedf215db809`; if selected as a second benchmark, its code semantics, model revision and outputs are an **independent stratum**. L-B cannot overwrite L-A golden results or be treated as adapter parity error on L-A.
- **Legacy result baseline:** hash the original raw `results/compare/*.csv`, `results/compare/manifest.json`, `results/compare/README.md`, `results/experiments/*`, E0/E1 source/manifest, old `METRIC_COLUMNS`, all relevant denominators, horizon, task-exposure caps and old compare gate decisions. Record both write-before and write-after hashes per attempted migration. If archival source is unavailable, mark NOT_VERIFIED; never fabricate it.

Neither `legacy_direct` nor `legacy_harness` can claim V1 WorldState B/C/D transactionality. A Legacy partial `env.step()` mutation is `LEGACY_OPAQUE_STEP`, never a trusted strict state snapshot. Backward-compatible visualization/descriptive comparisons are not permission to issue modern research ranking.

## 1. Legacy S0–S6 to M0–M5 crosswalk

| ARCH-04 slice | CONTRACT-05 stage | Minimum engineering action | Must not claim |
|---|---|---|---|
| S0 frozen baseline | M0 | pin source, config, map, seeds, versions, old outputs; test read-only | no software parity simply from a manifest |
| S1 read-only config/resource adapter | M0→M3 preparation | resolve config/OSM/CSV/GeoJSON path, SHA and defaults explicitly | no silent zero/alternate source fallback |
| S2 single isolated worker | M3 compatibility (can develop parallel to M1) | original Greedy function / other scheduler.step, one env.step, subprocess per Run | strict rollback / portable legacy checkpoint |
| S3 read-only old Scene | M3 | transform old scenario via versioned **read-only** importer; reject unsupported checkpoint | no automatic silent semantic migration |
| S4 opt-in new execution path | M3 after M1 signatures | `legacy_direct | legacy_harness | native_strict` distinct identities; legacy default | no promotion of legacy to strict merely via routing |
| S5 sidecar and step comparison | M3 with M2 for experiment parity claims | new run dirs, first divergence and strict comparison gate | no rewrite existing metrics, no rank if UNKNOWN |
| S6 multi-world/model replacement | M3 and later M4 | manifest/CRS/model-domain check and separate validation | new physical model outputs need not equal old engine |

M0 protects legacy independently of M1 native engine. A failed legacy bridge does not roll back accepted M1 implementation; it blocks *M3 parity promotion* and mandates retaining `legacy_direct`.

## 2. Gate matrix with real failure detection required

| Gate | Inputs and executed positive case | Required negative/failure case | Pass evidence | Failure action |
|---|---|---|---|---|
| **G-M0** source/evidence freeze | source SHA, OS/Python/deps, file-byte hashes, stable E0/E1 golden and original legacy command | intentional modified config/OSM/results byte or missing provenance | before/after SHA manifest equal; old command output and receipt | HALT new migration, restore untouched files from verified original ref |
| **G-M1** config/path/data | old default & custom OSM, CSV/GeoJSON, env `SWARM_BALANCE_SIM_CONFIG`, versioned scene | nonexistent path, missing schema field, mismatched CRS, implicit fallback | same resolved path/bytes/source with explicit error diagnostics | disable new resolver; keep original get_shared_config |
| **G-M2** action/step parity | exactly one original `env.step(action)`, step/time/state/observation/action/done for Greedy, GA, PSO (OR-Tools if installed); fixed 0/1/many tasks, wind on/off | Greedy incorrectly routed to `scheduler.step`, GA/PSO `optimize` substitute, two env.step calls, task/energy discrepancy | same-engine identity, per-step first divergence report, predeclared numeric technical tolerances and tested invariants | flag off, stop adapter; no acceptable unexplained semantic divergence |
| **G-M3** lifecycle/fault | pickup/delivery guard, berth queue, near-empty battery, failure/recovery with *pinned version* | phantom completed task, duplicate delivery, fault after partial state mutation | actual witness logs and failure statuses, base-version-stratified | reject claim, isolate TAINTED worker, retain last trusted old result |
| **G-M4** isolation/RNG | same pinned seeds repeated 3 times, interleaved independent workers, cold/warm map caches, own Python+NumPy globals | use shared module globals, change seed in one worker affecting another, checkpoint portable claim | repeat trace digests or predeclared first-divergence report, full process metadata | kill/recreate dirty worker, preserve `legacy_direct` |
| **G-M5** old scenes/checkpoint | read-only import old scene schema/seed/alg, valid patch restore in supported *old process* | unknown schema, old checkpoint across version/generation/model mismatch | explicit import/refusal and unchanged source SHA | disable importer; original scene library remains |
| **G-M6** metrics/results | run dry/short/static E0→calm E1 where eligible; check old `METRIC_COLUMNS`, time windows, numerator/denominator, strict compare gate | mixed GA quarantined 400/600step 22/30tasks 25 cols with OR-Tools 2000step/60tasks 20 cols; missing column filled zero; old result mutation | real compare gate outputs and identical old file hashes before/after; new sidecar distinct directory | block research ranking, no inferred compatibility |
| **G-M7** rollback | feature flag disabled, old console and experiments worker start, new adapter killed, permission/OSM failure injection | old endpoint unavailable after new route, auto-mutated config, schema writeback, hidden algorithm change | actual old path command/smoke, worker cleanup, old SHA match, revert procedure | immediately revert opt-in route only and retain prior verified old path |

All gates are **NOT_RUN for CONTRACT-05 docs**; the table lists minimum acceptance **plans**. Legacy original workflow may have previous historical successful CI on other SHA; those are not this implementation's gate results. Preserve original old CompareGate refusal: strict research cannot convert a descriptive warning into a ranking PASS.

## 3. Research integrity non-negotiables (R01–R12)

[ARCH-04 BACKWARD_COMPATIBILITY](https://github.com/159357yangjun/SwarmBalance/blob/c4c0c67111ead435062650c1ed776547c477e3e3/docs/platform/architecture/migration/BACKWARD_COMPATIBILITY.md) R01–R12 are all migration stop points, not discretionary release polish:
- **R01/R02/R03** power/defaults, distance/CRS/map/parser and event/tick ordering could change energy, mission path, timeout and berth metrics: record first changed source and stage; separate new model revision.
- **R04/R05/R06** Greedy special route, RNG globals/retry and #41 task-completion semantics: preserve old signatures and source-specific lifecycle; never quietly harmonize versions.
- **R07/R08/R09** generated-vs-requested task count/caps, metric denominator/window/schema, historical overwrites: fail closed if changed; no missing→0 imputation for new MetricSample.
- **R10/R11/R12** fallback to different model without trace, cross-generation checkpoint and interleaved globals: reject or TAINTED, never declare same Run provenance.

For K0–K4 labels:
- `K0` schema/config shape only;
- `K1` true same-engine same-input step behavior, version-stratified;
- `K2` historical scene read-only semantics;
- `K3` metrics/report consumer behavior and historical comparison refusal;
- `K4` explicit **different** model version with its own evidence, *not* parity expectation.

## 4. Result sidecar and first divergence

All *new* results must be separate e.g. `results/platform_runs/<unique-run-id>/{manifest.json,steps.jsonl,comparison.json,diagnostics.json}` (proposal only). Manifest contains `execution_mode, engine_commit_sha, adapter_sha, world_scenario_refs, input_OSM_sha, parser_mode, config_sha, runtime/dependency/profile, model_revision, algorithm_ID, normalized seed/worker isolation, event clock/version, MetricDefinition hashes, output sha256, comparison_gate_version`.

At each paired step compare: observation canonical fields, scheduler action order, world task/assignment/onboard custody, position, battery (Wh), resource leases, clock/terminal, actual generated count, metric numerator and denominator. If diff: save `first_divergent_step, observed vs expected, source layer (config/scheduler/dynamics/event/metric), tolerance predeclared, blame/status`. Float tolerance in units, justified **before** seeing actual results. No “same average” or post hoc threshold adjustment can excuse a same-engine state divergence.

Event/clock semantics in a new strict Harness (#58) are **not identical by definition** to legacy `Environment.step()`; matching one coarse step requires explicit K1 reference semantics or else report `NOT_COMPARABLE`, not fake ST-01 parity. If a new DynamicsModel or SpatialProvider is swapped, results are K4, not K1.

## 5. Rollback operational playbook (test before signoff)

1. Freeze current old source/config/manifest/result bytes and verification list, verify old `console` + `experiments` commands still work.
2. New implementations may only add opt-in routes and files. Default `legacy_direct`; never silently change old `/api/*` schema/semantics. Snapshot of any in-flight new Run is tagged by execution mode and cannot restore directly into legacy.
3. On failure, **stop accepting new adapter/native Run requests**; finish or cancel through declared boundary, log run_id/last trusted revision/errors; if legacy opaque partial mutation, mark TAINTED and destroy isolated worker, **do not** continue its state.
4. Disable new flag or new route at process restart; launch untouched old console/headless worker using original pinned config and old results path; verify original hash inventory, simple reset→step→snapshot and old compare gate.
5. Keep new sidecar artifacts **read-only** for forensic study even if invalid. No writeback or automatic schema downgrades, no “fix” by editing old CSV or silently swapping maps/models/algorithms.
6. File failure ticket: gate ID, old/new engine SHA, input/data/metric digests, first divergence, observed rollback command + output, old path health, remaining incomplete Runs and reviewer.

## 6. Implementation PR obligations and stop conditions

Before promotion attach real commands/logs/artifact digests for **G-M0…G-M7** appropriate to the stage. Any unknown provenance, changed historical source, nonisolated global seed, wrong legacy dispatch route, missing denominator, incompatible checkpoint, hidden fallback or failed old UI smoke is **FAIL**, not CONDITIONAL. Tests lacking actual execution are **UNVERIFIED**; the corresponding promoted capability must remain disabled. ARCH-06 architecture signoff does not itself execute this migration.

Owners: ARCH-04 Legacy baseline/adapter/parity; ARCH-02 Harness mode selector and worker lifecycle; ARCH-03 component/manifest/metric; AI-C seed parity; AI-D evidence and comparator; VVE on reality claims; AI-R independent record; coordinator final gate.


## M0–M5 latest identity integration guard (contract candidates)

**唯一规范候选（本任务后续阶段只引用这一版本）**：`C03C04-IDENTITY-v1`，见 [CONTRACT-04 新统一身份/RNG 文档](https://github.com/159357yangjun/SwarmBalance/blob/027fd78589229db3d2308ced5365b7a780703805/docs/platform/architecture/contracts/contract-04/LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md)。`logical_cell_tuple=(plan_digest,treatment_id,replicate_key,frozen_run_spec_digest)`；`cell_key=SHA256(LP4("SB-CELL-v1",plan_digest,treatment_id,replicate_key,frozen_run_spec_digest))`。`replication_id` **仅为旧数据导入别名**，规范对象只写 `replicate_key`，别名冲突拒绝；不同 spec digest 属于新 cell，禁止冒充 retry。每个 cell 的 `attempt_ordinal` 与 `attempt_id`、`run_id` 单独生成并保留不可变记录；attempt/generation/worker/plan_digest/run_id **不进入被哈希的 FrozenRunSpec 内容**（避免 Plan↔Spec 循环、重试扰动），Plan/RunRecord 保存绑定；实验外手动 Run 可 `cell_key=null`。相同 cell 重试只能重用同一冻结 spec/外生暴露/私有流键。A/B 配对共用不可变外生暴露键但不得共享可变 RNG；私有 key 由冻结 Spec 和组件版本派生，不以 attempt/worker 重新取种子。

**批准状态**：这是 #57 的候选、与 #56 的原四元组方向相容，**不是经 #56/EXP/ARCH-02 联合签署的 FROZEN 接口**。实施门采用唯一规范候选避免两套身份并行，但 **M2 不允许放行**，直到 AI-C/AI-D/EXP/ARCH-02/ARCH-03 共同签署、独立复核 G01–G13、执行 ID-N01～16/RCT-ID 正反测试并证明 durable idempotency。仅数学向量一致性不能放行 M2。

No Legacy file's old CSV filename/row index or historical seed may silently become a valid `cell_key`, `replicate_key`, `attempt_id` or CRN-paired exposure. The valid sidecar for provenance-only imports sets `origin=LEGACY_IMPORTED`, keeps original engine/source hash, lacks `cell_key` unless a **separate pre-registered** compatibility audit genuinely proves all required identity inputs; unknown provenance -> `INSUFFICIENT_EVIDENCE` / `ranking=null`. Retrying a native strict run after a Legacy failure must never deserialize opaque Python/NumPy snapshots as new transactional checkpoints. Before G-M6 parity, compare old metrics and run-length/denominator per frozen stratum; never mutate them to match the new schema.

Implementation gate crosswalk: **M0** preserve source/results SHA; **M1** manual RunRecord nullable cell; **M2** only co-signed `C03C04-IDENTITY-v1` permits plan/cell/attempt; **M3** process-isolated `legacy_direct|legacy_harness` with taint and rollback proof; **M4** cite immutable actual attempt refs in claim/evidence, separately validate intended-use physics; **M5** UI displays identity and honest omissions, never fabricates a passing comparison. Negative test for missing/invalid experiment binding, retry seed/spec drift and old-data mutation must be recorded with real output. Design-only status: NOT_RUN.
