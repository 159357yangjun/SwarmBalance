# CONTRACT-03 — Reproducibility contract test cases

> Status: PROPOSED FIXTURES ONLY / NOT EXECUTED / no measured results. Each case below is a future acceptance specification. Do not report PASS from a design walkthrough. Upstream HEADs and dependencies are pinned in EXPERIMENT_SEED_CONTRACT.md. No ARCH-02 time interface is fixed here.

## 0. Test protocol and evidence format

Implementation reviewer shall record: contract case ID; frozen ExperimentSeedPlan and FrozenRunSpec hashes; Scenario/World/Dataset/Model/Scheduler manifests; code/runtime/PRNG/distribution/numeric versions; seed derivation test vector; sampling opportunity/tape hashes; Run generation and attempt IDs; event trace and committed state digests; per-stream entry/exit cursor; failed/cancelled attempts; first divergent event/draw address; expected vs actual; decision PASS/FAIL/BLOCKED; test log or CI URL. Input fixture IDs below are illustrative, never claimed as actual run results.

For all examples: two schedulers A and B are different treatment manifestations; r01/r02 denote separate **replication opportunities**; p01/p02 denote matched exogenous exposure groups. Immutable exogenous tape includes independently produced arrival/weather/failure event records with stable IDs/timestamps. Any behavior arising from scheduler-specific state need not be equal. Pre-register measurement windows/metrics/eligibility separately with EXP-01/VVE-01, rather than inferring algorithm superiority.

## C03-T01 — Normal paired scheduler comparison (required case 1)

**Arrange**: Scenario S@1 has seed=101; plan P@1 has seed_plan_root=9001, two treatments Scheduler-A@digestA and Scheduler-B@digestB, replication keys r01 and r02. Freeze `C03C04-IDENTITY-v1`, with `(plan_digest,treatment_id,replicate_key)` mapping to exactly one immutable spec digest. For each key, freeze one external demand tape, wind field and independent static-equipment failure schedule; use identical exposure references across A/B and independent refs across r01/r02. Both RunSpec manifests include own Scheduler digests and per-cell effective master seed. Clock policy and meaning are identical by explicit ARCH-02 reference.

**Act**: Assemble four independent Runs (A,r01), (B,r01), (A,r02), (B,r02); repeat in reverse launch order and parallel. Collect external tape digest, per-stream ledger, state/event/metrics trace, status and plan-to-run binding.

**Must hold**:
- Within r01, A and B share *identical immutable exogenous tape content digest*, event IDs/time coordinates and source spec, despite different full RunSpec digests; r02 has its own allocated tape.
- A/B Scheduler-private root/handles are distinct; parallel scheduling cannot alter external bytes or private logical key identity.
- Matching source tape does not require matching applied event effects, decisions, completion counts, energy, or algorithm quality. Pairing eligibility is conditional on controlled factor and metric gates.
- Repeating the same cell in a pinned deterministic profile meets its claimed R3/R2 acceptance, if supported and tested; independent replications are r01/r02 only, not repeat attempts.

**Negative control**: Derive exogenous key from full treatment RunSpec digest (ARCH-02 original unmodified proposed formula). A/B demand/weather digests become different or cannot be guaranteed equal => FAIL CRN_EXPOSURE_MISMATCH; "same seed" is not evidence of a valid matched pair. Another negative: keep seed=101 but vary NumPy draw order => mark comparison pairing unproven, never PASS merely on seed text.

## C03-T02 — ModelManifest replacement and stream invalidation (required case 2)

**Arrange**: Start from (S@1, P@1, Scheduler-A@x, DynamicsModel-M1@y). Clone a treatment with DynamicsModel-M2@z. Preserve immutable precomputed weather, demand, static failures, World inputs, temporal interpretation and exogenous generators. Model-specific process noise and energy response belong to DynamicsModel-private namespace.

**Act**: Compare stream-key tables and manifest digests before and after M1→M2, and compare fixed exogenous tapes.

**Must hold**:
- Frozen RunSpec digests and Dynamics private roots differ; unchanged external demand/weather/static-equipment failure tape digests equal.
- With private-root policy including entire spec digest, other private roots may also change; audit them and do not falsely claim private bitwise parity.
- Model outputs/energy and subsequent state-dependent hazard exposure can differ with identical weather samples. Statistical comparability requires explicit model-treatment design and domain/metric approval, not pretending only Scheduler changed.

**Negative controls**: (a) M2 changes the weather generation/interpolation sign convention or failure hazard model while leaving exposure digest unchanged => FAIL STREAM_SCHEMA_MISMATCH / CRN_EXPOSURE_MISMATCH; generate a new exposure identity. (b) M2 secretly uses global random state => FAIL RNG_GLOBAL_STATE_FORBIDDEN. (c) Runtime continues M1's checkpoint/cursors after model swap => CHECKPOINT_INCOMPATIBLE. The model's physical validation status remains unassessed.

## C03-T03 — Crash/retry, RNG rollback and double-counting (required case 3)

**Arrange**: One planned cell (P@1,A,r01,spec_digest=k) uses logical cell key K. Inject a deterministic failure after Scheduler consumes some private draws but before boundary commit, or crash just after durable success artifact write but before acknowledgment. Also inject a postcommit MetricProvider export failure. Keep original external tape and seed plan immutable.

**Act**: Launch attempt a1, record FAILED or unacknowledged completion; launch a2 using the SAME logical cell K with a NEW attempt_id. Restore only from a validated transaction fence/checkpoint or clean-run restart. Replay with worker count changed.

**Must hold**:
- a1 failure, terminal reason and draw/trace evidence remain visible; no hidden replacement.
- Before-commit failed boundary does NOT advance committed state/clock/queue/RNG cursors; private nonrollbackable components prevent strict in-place retry.
- a2 uses original keys and exogenous tape; attempt_id NEVER perturbs RNG derivation. An unacknowledged success is reconciled using artifact digest/idempotency before rerun.
- Aggregate selected outcomes count K at most once, even if a1/a2 both have SUCCESS records. Failure/attrition report still lists both attempts.
- After postcommit metric failure, only re-export from immutable committed data; never execute the same domain boundary again to repair metrics.

**Negative controls**: include attempt_id in stream root, restore only Python RNG but not NumPy/component state, or append every attempt's success as separate replication => FAIL. Any changed seed/spec is a new experimental cell, not a "retry".

## C03-T04 — Scenario/Experiment/Run seed precedence and conflict

**Arrange**: Scenario.seed=101; ExperimentPlan.seed_plan_root=9001; plan maps (A,r01) to resolved Run master_seed=m (freeze exact m using golden derivation vectors once defined). A standalone Run can specify seed=888.

**Checks**:
- Experiment-bound Run with master_seed=m succeeds and records Scenario.seed=101 as unused default; a Run master_seed=101 or 888 that differs from m => SEED_PLAN_CONFLICT.
- Standalone explicit master_seed=888 takes priority over Scenario.seed=101; standalone missing master_seed resolves to 101.
- No standalone nor Scenario seed => SEED_UNRESOLVED. No nondeterministic OS/time implicit default.
- Attempt/restart does not change resolved master_seed.

## C03-T05 — RNG component interference and parallel independence

**Arrange**: Two independent RunScopes, stream set {demand,weather,vehicle.failure,scheduler.search,dynamics.process_noise}; invoke Scheduler with different algorithm branch depths, reorder worker launch times and interleave Runs. Inject extra private Scheduler draws into A only.

**Must hold**: A's extra private draws change only explicitly dependent private outcomes; B's RNG cursors, A/B precomputed exogenous tapes, and unrelated fixed external streams are unchanged. Each component can only access declared streams. Reject mutable global random and unordered iteration-based draw addresses. Stable component manifest identity determines substream keys; duplicate owner/name declarations rejected.

## C03-T06 — Frozen event tape vs runtime application

**Arrange**: Same wind update, independently sampled task arrival, and exogenous failure at explicitly pinned time coordinates; two schedulers yield different device positions/availability.

**Must hold**: matched external event tape digests and event identities are identical; whether event is applicable and downstream physical consequences may diverge. Evidence separately records *sampled*, *queued*, *accepted/applied/rejected* events. Event-time conversions and same-time phase ordering are referenced to CONTRACT-01/ARCH-02, not invented in CONTRACT-03. A different time mapping must invalidate CRN until approved.

## C03-T07 — Checkpoint and reset compatibility

**Arrange**: Preserve RunSpec, assembly manifest, RNG generator, stream counters, component-private state and event queue at a valid checkpoint barrier. Resume from same image; also attempt resume with changed Scheduler/ModelManifest, PRNG version, numeric environment or generation.

**Must hold**: compatible resume maintains committed trace/stream cursor according to R3 profile; incompatible restore rejected with deterministic diagnostics. A new reset generation owns new independent mutable handles with deliberate seed resolution. No leakage of discarded generation events/draws. Strict R3 is unavailable for noncheckpointable private component or legacy opaque in-memory snapshot unless separately demonstrated.

## C03-T08 — Three claim levels and scientific refusal

**R3 full replay**: bit-equal committed trace/state/event and RNG cursor digests within fixed supported profile and frozen immutable tape; any mismatch => fail R3 and report first divergence. **R2 same-input determinism**: compare outputs under pre-registered numeric tolerances, preserving first divergence and domain semantics, never retroactively widen thresholds. **R1 statistical comparability**: verify control-factor equality or declared treatment, pairing exposure digests, replication identities, model/metric compatibility, failure/censoring rules, and analysis scope; R1 can be eligible even if A/B traces are inherently different. None of R1/R2/R3 licenses a physical Validation PASS or superiority claim. Under missing metric denominator, silent fallback or missing attempt ledger => NOT_COMPARABLE.

## C03-T09 — Legacy protected evidence and process isolation

**Arrange**: At fixed legacy commit SHA, same config/OSM/parser/dependency hash and seed, run legacy_direct and proposed legacy_harness in separate worker processes; run interleaved fixed seeds and cold/warm cache conditions.

**Must hold**: preserve old metric columns, old results as read-only, record engine/adapter identities, first divergent step, Python+NumPy global RNG and isolation limits. No assertion that raw legacy process checkpoint is a portable scoped RNG checkpoint. Legacy parity depends on separate ARCH-04 G-M0–G-M7 execution; this document is not proof those gates pass.

## 1. Required golden vectors before cross-group freeze

Freeze canonical input byte encoding and exact outputs for: (a) seed roots for exogenous and private namespaces, (b) two shared treatments with different spec digests generating the same exogenous stream key, (c) two replication keys generating distinct exposure roots, (d) Scheduler manifest change rekeying private stream only as prescribed, (e) keyed draw addressing with stable entity/time/ordinal, (f) checkpoint cursor restore, (g) distribution sampler versions and numeric profile. Reference implementation must be provided by implementation owner and independently verified in at least a second execution path; no values are fabricated here.

## 2. Acceptance summary and responsibilities

| Gate | Evidence expected | Primary owner | Current status |
|---|---|---|---|
| C03-G0 | 3 docs, precise SHA upstream ledger, only docs changed | CONTRACT-03 | DESIGN SUBMITTED; review required |
| C03-G1 | Seed precedence, frozen plan schema, independent replicas/attempts | EXP-01 + ARCH-01 | OPEN for joint sign-off |
| C03-G2 | Scoped RNG APIs, checkpoint/rollback and Run concurrency | ARCH-02 + ARCH-03 | OPEN |
| C03-G3 | Canonical KDF/PRNG/sampling specification and golden vectors | EXP-01 + ARCH-02 | OPEN |
| C03-G4 | T01–T09 executed with artifacts; both positive/negative cases | implementation team + independent reviewer | NOT RUN |
| C03-G5 | Metric comparability and VVE claims independently gated | EXP-01 / VVE-01 | OPEN |
| C03-G6 | Legacy isolation and old evidence SHA protected | ARCH-04 + implementation review | NOT RUN |
| C03-G7 | Upstream HEAD refresh, cross-signature, coordinator ADR | ARCH-05 reviewer + coordinator | OPEN |

### Handoff decision

This task **resolves B04 at proposed documentation level only**, pending co-signature, implementation and tests. Cross-group B01/B02/B03/B05/B06/B07 are not overridden. Do not merge this Draft PR; do not freeze a time API; do not run studies and then claim ranking/real-world credibility without independent measured evidence.


## 3. Formal C03 × C04 PR #57 review regression cases (AI-C addendum)

Review source: CONTRACT-04 PR #57 `027fd78589229db3d2308ced5365b7a780703805` and its `LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md`; CONTRACT-03 original PR #56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`. This section is *design fixtures*, except explicitly noted independent arithmetic checks. PR #57 HEAD advanced by four commits after the first review; AI-C has now reviewed that delta and the new `FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md`. Its `SB-FROZEN-RUN-SPEC-v1` + `SB-CJSON-1` is the single proposed full-spec format; earlier AI-C JCS candidate was withdrawn. Exact LP4/HKDF derivation and complete FrozenRunSpec serialization candidate are in `EXPERIMENT_SEED_CONTRACT.md §9`.

### 3.1 Actually computed vs never executed

**Actually executed by AI-C:** separate Python stdlib `hashlib/hmac/struct` implementation of LP4, HKDF Extract/Expand and indexed draw recomputed all PR #57 synthetic fixture inputs and G01–G13 (13/13 exact matches). This includes G01 cell A `sha256:41957ee33f111aa9fc24d694fa09c2261e0621ff8be41be653e5be32665164fb`; G03/G04 distinct attempt hashes; G07 master uint64 `5928125456373989572`; G08 `7174855733580601445`; G09 exo key `71431f83f3cd9855fc1351335a3197d78cba1bce8adedb2fdcaf1f2e5a779f99`; G10 alternative exposure `c6409fab9be559fac3c034bbec2e5ca7a26d054903976f40779590d41a865d11`; G11 private A `a914a88477f24edb367427e591562680c62fb05a40483e0a29e67e021868648e`; G12 private B `5b27c63dd4abceac6893f1a766f180efc742f5591cad633a965d67190ec06f65`; G13 indexed draw first 8 bytes `2276e70cab9bca45`, `draw_u64=2483426286146144837`, `draw_u53=1212610491282297`.

**NOT executed:** repo-sourced LP4/HKDF implementation, integration tests, Python/Node comparison for all Unicode cases, SB-CJSON-1 RFC8785 full-spec implementations, distribution samplers, time/event engine, multiworker or crash replay, CI, actual RunRecord queries and complete simulator R1/R2/R3 replay. Do not mark these PASS.

### 3.2 Required future conformance and negative oracle

| Case | Positive/negative input | Expected (NOT EXECUTED) |
|---|---|---|
| C03-ID-01 | Exact Plan triple (plan_digest,A,r02) is bound to spec SA; resubmit same digest | idempotent same cell_key, no second replication |
| C03-ID-02 | Same frozen Plan triple requests different SB digest | `PLAN_CELL_SPEC_CONFLICT`; no new sample under that plan; new plan revision required |
| C03-ID-03 | RunSpec contains plan_digest, run_id, attempt_id, ordinal, generation, time or spec_digest itself | `CYCLIC_SPEC_PLAN_DIGEST` or `ATTEMPT_FIELDS_IN_SPEC`; fail before hashing |
| C03-ID-04 | Full FrozenRunSpec SB-CJSON-1 serialize/parse in two conformant implementations; permute JSON key order | identical canonical bytes + spec digest; strict field validation; no path/clock from host |
| C03-ID-05 | Non-NFC strings, duplicate normalized IDs/keys, invalid surrogate, float 9007199254740993, uint64 numeric JSON, NaN, negative zero, leading zero ordinal | `IDENTITY_ENCODING_INVALID` or `FROZEN_SPEC_CONTENT_MISMATCH`; reject rather than silently normalize/reseed |
| C03-ID-06 | G01–G13 full identity/KDF/draw fixtures via two independent implementations | exact published bytes including BE64, 13/13 or fail and first mismatch |
| C03-ID-07 | Two treatments A/B share p02,r02 and same frozen exo source; different Scheduler manifests | same exo G09; distinct private G11/G12; separate mutable handles |
| C03-ID-08 | Attempt 1 persisted terminal SUCCEEDED but acknowledgment lost; redeliver same ordinal | durable `(cell_key,ordinal)` lookup returns existing attempt_id/run_id, no second worker/sample |
| C03-ID-09 | Attempt 1 UNKNOWN or worker possibly live after crash; attempted new ordinal | fence/reconcile committed artifacts first; `ATTEMPT_OUTCOME_UNRESOLVED`, no optimistic rerun/double count |
| C03-ID-10 | Verified FAILED attempt followed by preregistered attempt 2 (same spec/master/exposure) | distinct attempt_id/run_id; identical stream keys; two records, only one selected statistical outcome |
| C03-ID-11 | Metric lock changes with new execution under full-spec private KDF | new frozen spec/cell and possibly different private keys; exo tape only if source same. Reanalysis of immutable old artifacts does not draw new RNG |
| C03-ID-12 | Use uniform indexed sampler, change opportunity address or reuse address for two different opportunities | unique stable keys; duplicate => `RNG_DRAW_ADDRESS_COLLISION` |
| C03-ID-13 | Ask R3 replay with unspecified Poisson/Gaussian sampler, PRNG implementation or numeric profile | `RNG_VERSION_UNPINNED` / `REPLAY_CLAIM_UNSUPPORTED`; 13/13 math is insufficient |
| C03-ID-14 | Missing MetricDefinition, altered code/source/clock digests, scheduler-private checkpoint mismatch | incompatible RunSpec/restore; compare/resume refused with reason, no silent fallback |
| C03-ID-15 | Two independent logical replicates share the same external exposure unintentionally | `REPLICATION_EXPOSURE_COLLISION` unless explicit predesignated shared-tape dependence; never count as independent |
| C03-ID-16 | Manual ad hoc Run with no ExperimentPlan | RunRecord with `cell_key=null` and distinct request idempotency; no fake replicate_key |

**Strict acceptance:** independent vector computations do **not** satisfy C03-ID-04..16. For any contract claim, require running implementation commit, fixture input hashes, actual/expected outputs, first mismatch and original logs, plus independent reviewer sign-off. A failing durable attempt-reconciliation test blocks Batch analysis and ranking, even if all mathematical vectors agree.

### 3.3 Newer PR #57 full-spec SPEC-01/02 synthetic checks (actual math only)

The complete mandatory 17-key schema and its byte serialization are now `SB-FROZEN-RUN-SPEC-v1` / `SB-CJSON-1` in PR #57 `FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md` at HEAD `05d406b4ca305752f28392ee382cdc2868a4a5e5`. AI-C independently executed the Python `hashlib/json` synthetic fixture assembly and digest calculation specified there and checked:

| Vector | Actual independently calculated AI-C result | Math verdict |
|---|---|---|
| SPEC-01 full 17-key synthetic object | UTF-8 byte length `2471`; SHA-256 `d2c07f032498322da6130f153d72199052e249559707574559c8791e2959ddf8` | MATCH |
| SPEC-02 metric-version-only change `1.0.0` → `1.0.1` | UTF-8 byte length `2471`; SHA-256 `99353448ec6277f9bac835e82f573bf9f8051832d45db0c5307f38ac5f68e5dd` | MATCH |

These 2/2 values are **not** PR #57's G01–G13 input spec digests; the original vectors use independent fixture-label SHA256 inputs. They cannot be spliced together while expecting G01/G02 identity hashes unchanged. Cross-language complete SB-CJSON-1 conformance including NFC/UTF-8 ordering, control escapes, duplicate keys, uint64 strict rejection and semantic nested digest verification is **NOT EXECUTED** here. The superseded 109-byte AI-C partial JCS fixture is **not** an active contract standard.

Add future negative conformance oracles: attempt Spec hash with `run_id` included -> `ATTEMPT_FIELDS_IN_SPEC`; mutate locked metric version without new spec hash -> `FROZEN_SPEC_CONTENT_MISMATCH`; same immutable Plan triple with new Spec -> `PLAN_CELL_SPEC_CONFLICT`; JSON numeric seed or ambiguous Unicode normalization -> `IDENTITY_ENCODING_INVALID`; unknown Poisson/Gaussian sampler under `C03C04-SAMPLER-MIN-v1` -> `SAMPLER_VERSION_UNPINNED`; missing persisted artifact/late leased worker after crash -> `ATTEMPT_OUTCOME_UNRESOLVED`. All are **NOT RUN**, and must not be marked PASS until implementation tests and logs exist.

### 3.4 Gate

- **Limited math fixture verification:** PASS (AI-C 13/13 exact synthetic G01–G13 plus 2/2 complete-top-level synthetic SPEC-01/02 math hashes). It establishes only arithmetic on supplied inputs, not full manifest hashing or RNG runtime portability.
- **Specification alignment:** PROPOSED; AI-C accepts PR #57 LP4/HKDF rules and C03C04-IDENTITY-v1 at review level, adds SB-FROZEN-RUN-SPEC-v1 as proposed complete-spec byte serializer. No claim of formal cross-team ADR approval.
- **Integration, replay, crash durability, sampler versioned tests:** NOT RUN / HOLD.
