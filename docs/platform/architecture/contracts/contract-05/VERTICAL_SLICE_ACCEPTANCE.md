# CONTRACT-05 — Vertical Slice Acceptance / M0–M5

> **Acceptance specification, not executed outcomes.** As of this Draft, all proposed fixtures are **NOT_RUN** unless a later implementation PR contains real immutable logs tied to exact code HEAD. Arch design review and GitHub filescope checks alone are not runtime PASS. Read [IMPLEMENTATION_DEPENDENCY_PLAN](IMPLEMENTATION_DEPENDENCY_PLAN.md) for pinned inputs/owners and [LEGACY_MIGRATION_GATES](LEGACY_MIGRATION_GATES.md) for old system K/G gates.

## Common gate protocol (every stage)

Record `stage_id, implementation_pr, exact_source_head, design_contract_head_set, branch/base_sha, fixture_id, positive_or_negative, command, runner_os_python_deps, frozen_run_spec_and_model_digests, input_artifact_sha256, expected, observed, first_divergence, actual_log_url_or_sha256, outcome, reviewer, rollback_action/outcome`. Valid outcome enum: `PASS | CONDITIONAL | FAIL | UNVERIFIED`. A design-only test case has outcome **UNVERIFIED/NOT_RUN**, never PASS. Missing expected baseline, unpinned identity, empty evidence links, unaudited source write → FAIL for that gate.

The implementation must demonstrate **negative controls that genuinely fail closed**: merely asserting a happy-path result is not a stage acceptance. For SW/EX/RV store separate decisions. Stage promotion requires its entire mandatory test set actually PASS, no unresolved P0 and explicitly approved P1 deferrals; conditional successes do not permit advertising stronger guarantees.

## M0 — Legacy and research evidence conservation

- **Inputs**: frozen `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`; historical E0/E1; `results/compare/manifest.json`, `results/compare_gate.py`, `frontend/metrics_schema.py`, `results/experiments`, actual configurations, OSM/CSV data, package/runtime versions; **PR #41** separate stratum if used.
- **Deliverables**: read-only hash inventory; source/model/metric/config/dataset versions; golden legacy step and batch fixtures; archived pre-run CSV/header/denominator/window semantics; comparison-gate result and fallback runbook.
- **Positive**: L0-P1 pin all source/data/config/results sha256 and repeat one deterministic static Legacy fixture; L0-P2 original compare gate accepts a known compatible group under its *historic* purpose, original entry launches; import as read-only reference without rewriting metadata.
- **Negative**: L0-N1 seeded mismatch of map/config/metric or unauthorized old results write **trips hash/scope gate**; L0-N2 mixed quarantined GA 400/600 steps vs OR-Tools 2000 steps is rejected; L0-N3 master and #41 different lifecycle semantics cannot be silently grouped.
- **PASS**: reproducible golden plus immutable before/after SHA list; positive and negative checks actually executed; legacy direct still operable. This is conservation, not new Harness parity. **Owner** ARCH-04, research evidence reviewers. Gate `G-M0,G-M6`.

## M1 — Minimal strict Harness + WorldState + standalone Run (no UI)

- **Inputs**: M0 PASS; D01/D02/D03/D04 and RunRecord minimum of D06 signed; static WorldDefinition/Scenario/Entity refs, new schema and simple deterministic providers; no replacement or GUI requirement.
- **Deliverables**: one isolated `RunController`, authoritative StateCommitter/WorldState, frozen clock + EventSpec→EventIntent→EventEnvelope conversion, `Scheduler.propose(ObservationV1,ctx)`, `DynamicsModel.propose(StateSliceView,Conditions,ModelIntervalRef,ctx)`; immutable staged view_token; single postcommit frame, RunRecord+FailureRecord+diagnostics/artifact manifest; `create→initialize→advance boundary→snapshot→stop/result`.
- **Positive**: `ST-01,02,06,09,11,13,15` and `C02-01,C02-14,RCT-01` on actual code; valid same-time pre-input fault/wind affects scheduler, but only one external revision; standalone run with experiment_ref=null owns one RunRecord; step_index not assumed elapsed seconds.
- **Negative**: `ST-03,05,07,08,10,12,16,17`, `C02-02,03,05,06,08,10,11`, `C06-01,04,05,12`, `RCT-03,05`. Inject NaN after staged wind/action, stale provisional token, phase inversion, 0.1 ns, duplicate conflicting event, a component that cannot restore private D and a metric postcommit crash. Precommit B/C/queue/RNG/D digest must remain exactly unchanged; postcommit world must **not** rewind. End-of-interval service facts separated from next-boundary PRE_INPUT events.
- **PASS**: exact types/signatures checked, validator rejects second writer and unsupported recovery *before READY*, actual logs prove positive/negative, immutable committed snapshots, no provisional leak; run/attempt/error record retained; Legacy files untouched. Any claim of transaction durability across process crash requires additional persisted atomicity proof, not M1 by default.
- **Nonblocking**: GUI, registry hot-swap, checkpoint portability across code versions, real aircraft calibration. **Owner** ARCH-01/02/03 + CONTRACT-01/02/04 co-sign; `SW` only.

## M2 — Minimal research experiment and strict analysis (no UI)

- **Inputs**: M1 PASS; D05 seed precedence/stream ownership and D06 metric/comparison/record identity accepted; resolve CONTRACT-03 vs -04 logical cell key before first batch; two conforming scheduler treatments, **two distinct replication keys** at minimum for software fixtures (not a statistical power claim).
- **Deliverables**: versioned `ExperimentDefinition → immutable ExperimentPlan → FrozenRunSpec` with independent exogenous tapes + treatment-private streams; `ExperimentRunner/BatchRecord` enumerating all scheduled/failed/cancelled/retried attempts; same MetricDefinition digest/window/numerator/denominator/missing policy; `AnalysisRecord` with eligibility, comparator reasons, method, refusal and immutable refs.
- **Positive**: `C03-T01,T03,T04,T05,T06`; `RCT-02,06,20,22` when preconditions are genuinely satisfied. At least two algorithms, distinct independent replication cells, paired exogenous A/B **same tape hash per replicate** but different private streams, same inputs across worker order; run→analysis graph hash verifiable.
- **Negative**: `C03-T01` counterexample using treatment-wide RunSpec in exogenous KDF; `C03-T02` model source change, `C03-T03` crash-after-write retry double-count; `RCT-07,09,10,11,12,13,19` reject zero denominator, shifted window/schema, mismatched exposure, missing seed provenance, engine mismatch, tampered artifact and unknown historical seed. `ranking=null` and explicit reasons when NOT_COMPARABLE.
- **PASS**: reproducible manifest and attempts ledger, verified external exposure contents, true KDF golden vectors & PRNG/distribution versions, idempotent selected result per logical cell, actual negative evidence and no fabricated replacement for failed Run. EX eligibility (if supported) is distinct from SW tests and from RV model validity. **Owner** EXP-01/AI-C/AI-D, ARCH-02/03 sign.

## M3 — Actual component replacement and Legacy parity

- **Inputs**: M1; M0 preservation evidence; M2 where comparative ranking/seed integrity is asserted; frozen B02/B06 and ARCH-04 adapter contract.
- **Deliverables**: registry and capability checks, replacement of SpatialProvider (map/CRS), Scheduler (not direct old act/step), DynamicsModel (energy/motion) via manifests **without modifying Harness core**; explicit `legacy_direct` default and opt-in `legacy_harness` isolated subprocess worker; K1 step-by-step sidecar.
- **Positive**: valid replacement with manifest version/source hashes, correct World ref/CRS; same Legacy engine SHA+config+map+seed+model+parser in two isolated worker paths reproduces agreed step/state/metric golden within **predeclared technical tolerances**; `LEG-01…LEG-12` controls evaluated in appropriate modes.
- **Negative**: map lacks CRS / missing height; model requires unavailable fields; unsupported private D; legacy Greedy silently changed to `step()`; GA/PSO path changed to `optimize()`; index→EntityId wrong; legacy worker throws midstep; legacy checkpoint presented as strict/portable. All reject or produce `TAINTED`; no undocumented default fallback.
- **PASS**: contract capability and provenance gates, first-divergence explanation, `G-M1…G-M7` applicable gates with actual logs; Legacy old UI/worker/gates still usable and original results hashes identical. K1 is **same-engine parity**, not proof two different physical models should match. **Owner** ARCH-03/04, ARCH-02, legacy research owner.

## M4 — Reality Validation / UQ / evidence-backed scoped claims

- **Inputs**: M2 integrity evidence and appropriate M3 data/model lineage; independent reference dataset and licensed provenance; predeclared intended-use envelope, calibration/validation split, error thresholds.
- **Deliverables**: verification records for target code, independent ValidationRecord with observed error/domain/split/leak audit; UQRecord separating aleatory/epistemic components and justified ranges/replicate plan; content-addressed `CredibilityClaim → EvidenceBundle → Analysis → Batch → Runs → Models/Data/Code`.
- **Positive**: `RCT-13,14,15,16,21` provenance/link integrity and scope tests; real holdout/reference comparison with recorded actual errors and thresholds; UQ interval/sensitivity with full parameter assumptions.
- **Negative**: leak train/calibration into validation; missing independent measurements; out-of-domain 10 m/s claim with only ≤6 m/s validated wind; bundle hash complete but Validation NOT_ASSESSED; attrition hidden; broken claim→run ref. Must output `NOT_ASSESSED/INSUFFICIENT/OUT_OF_SCOPE`, not reality PASS.
- **PASS**: actual source data and computed error in domain against **preregistered** acceptance, actual sensitivity/uncertainty evidence and independent reviewer; otherwise RV remains NOT_ASSESSED or FAIL. M1/M2 software passes remain intact, but **no real-world accuracy/deployment claim**. **Owner** VVE-01, model/data owners, independent evidence reviewer.

## M5 — Professional workbench task closure

- **Inputs**: stable M1/M2/M3 public capabilities, contract version negotiation, separate TaskUI G0/G1 approvals. A UI may display unverified M4 status explicitly.
- **Deliverables**: Project/World/Scenario/Component selection, validation, Run and Experiment launch, failures/cancellation, version/seed/metric/evidence comparison, export/replay/rollback controls; end-to-end auth/task log, accessibility/performance and no direct World mutation.
- **Positive**: user can create frozen world→configure Run/Experiment→launch→inspect comparison refusal or result→export immutable evidence→restart read-only view; snapshot concurrent with boundary is coherent.
- **Negative**: stale UI token/unknown component, invalid dataset, failed job, missing metrics, unauthorized state patch, old results overwrite, UI falsely showing green physical Validation. Must surface stable error + recovery, no hidden defaults.
- **PASS**: actual E2E user-task, API and permission regression, failure rollback, proof audit paths and data provenance; UI G0/G1 separate from SW/EX/RV scientific claims. **Owner** UI/TaskUI team with Harness/EXP/ARCH-04/VVE.

## Required cross-stage invariant checks

1. **No stage auto-promotes the next**. M1 may PASS software under synthetic fixtures while M4 NOT_ASSESSED; M3 hot-swap may PASS infrastructure while Legacy parity FAIL; M5 UI task flow may PASS while reality claims stay unavailable.
2. Strict Run always rejects a component that writes authoritative B/C or has unknown rollback side effects. One externally visible revision per boundary; stage token fences differ even with same committed revision.
3. Paired exogenous tapes use shared exposure identity independent of treatment-specific RunSpec; each Run owns private RNG and isolated D. Never count attempts as replications.
4. RunRecord exists even for standalone/failed Runs after run_id allocation; metrics never silently impute missing values; strict ranking requires comparator PASS and preregistration.
5. Historical result, metric schema and golden artifact bytes remain read-only across all stages; new data is append-only and namespaced.
6. Stage outcomes refer to a full exact commit SHA, executed command and logs; this document describes **future** tests only.
