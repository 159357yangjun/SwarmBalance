# CONTRACT-02 增量｜事务 / 事件 / Proposal 统一交换规范与会签矩阵

> **STATUS = PROPOSED / CROSS-SIGN PENDING / DESIGN-ONLY；禁止将本文件称为正式冻结 V1 或可执行通过。**
> Owner = AI-B / CONTRACT-02（只编辑 #55 分支），仅定义组件与 Harness 交界的 canonical **candidate** 和总转换表。AI-A/ARCH-02 对 clock、EventEnvelope、phase、single-boundary semantics 保持最终所有权；AI-C 对 RNG 保持所有权；ARCH-01 对 domain operation 保持所有权；主控作 ADR-002/003/006 冻结决定。此稿不直接修改 #58/#56/#57/#59/#60/旧引擎/主线。
>
> **Immutable input ledger (2026-10-16)**：master `2ab60c69a806a22d7ba20353dee0571752a0e8e5`；#54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`；#58/CONTRACT-01 `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377`；#55/CONTRACT-02 **prior to convergence** `b00cd337de2797b9819089b234a113e36513e003`；#56/CONTRACT-03 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`；#57/CONTRACT-04 `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`；#59 independent review `28daf1e336a1447b098b4d6fa044095b7caa1f4f`；#60 implementation gates `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`. Ancestors: #46 `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048`, #47 `68382c649393057ffbf5a14508ab1ff72d575b09`, #49 `d155621aca66e3a80c388718093a452d17d71e10`, #50 `c4c0c67111ead435062650c1ed776547c477e3e3`, #51 `f2df96bc609ee1e430ea6eff2456c4577347c300`.

## 0. Coordinator-directed strict V1 schema convergence (candidate-2, this amendment takes precedence)

**Source of direction:** coordinator [ARCH-06 PR #61](https://github.com/159357yangjun/SwarmBalance/pull/61) at `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc`; AI-A [CONTRACT-01 PR #58](https://github.com/159357yangjun/SwarmBalance/pull/58) at `bd5e47266d79d1e087ca8cfc6fe68ea28a03496b` (`STATE_COMMIT_CONTRACT §8`, `TIME_AND_EVENT_CONTRACT §7`). This revision **replaces the ambiguous public ChangeSet and boundary_ref examples later in this document** with **exactly one component public header and one internal Harness normalized type**. `state-event-proposal.v1-candidate-2` is an aligning **proposal**, not a frozen/approved V1. #58 currently contains old `window_ref:ModelIntervalRef` and public `boundary_ref` in addenda; **those are documented differences for AI-A to correct**, not a second accepted ABI.

### 0.1 Single public header and two public proposal outputs

```python
# PSEUDO-PROTOCOL / ONE public header, ARCH-06 names; NOT implemented.
class ProposalHeaderV1:
    schema_version: Literal["proposal-header.v1-candidate"]
    run_id: str
    generation: uint64
    boundary_id: str                 # explicit Harness-minted Run-local public ID
    base_revision: uint64            # last published revision (not stage_seq)
    read_view_token: OpaqueViewToken  # Harness-minted (run,generation,boundary,stage_seq,slot)
    proposal_id: str                 # idempotent with canonical payload digest
    producer_id: str                 # frozen ComponentDescriptor identity
    capability_ref: str
    provenance_ref: str

class ActionProposalV1:
    schema_version: Literal["action-proposal.v1"]
    header: ProposalHeaderV1
    actions: tuple[AssignTaskChain, ...]
    emitted_event_intents: tuple[EventIntentV1, ...]   # only registered capability; else ()

class StateDeltaProposalV1:
    schema_version: Literal["state-delta-proposal.v1"]
    header: ProposalHeaderV1
    model_interval_ref: ModelIntervalRef   # Dynamics integration ONLY
    changes: tuple[MotionEnergyChange, ...]
    service_facts: tuple[ServiceFactCandidate, ...]
    emitted_event_intents: tuple[EventIntentV1, ...]

# NOT a component Protocol: a type owned and emitted solely by Harness.
class NormalizedChangeSetV1:
    schema_version: Literal["normalized-changeset.v1"]
    proposal_id: str
    producer_id: str
    run_id: str
    generation: uint64
    boundary_id: str
    base_revision: uint64
    read_view_token: OpaqueViewToken
    phase: PhaseV1                    # Harness assigns invocation phase
    operations: tuple[OperationV1, ...]  # ARCH-01 allowlisted typed reducers
    capability_ref: str
    source_digest: str               # canonical source proposal bytes + versioned converter
    model_interval_ref: ModelIntervalRef | None
    emitted_event_intents: tuple[EventIntentV1, ...]

class EventIntentBatchV1:
    schema_version: Literal["event-intent-batch.v1"]
    run_id: str
    generation: uint64
    boundary_id: str
    read_view_token: OpaqueViewToken
    producer_id: str
    window_ref: EventWindowRefV1    # EVENT polling ONLY; NEVER ModelIntervalRef
    intents: tuple[EventIntentV1, ...]
    source_manifest_digest: str
```

**No `NormalizedChangeSetV1` public component return**; `NormalizedChangeSetV1` is an internal conversion result and cannot be submitted by a component. The `ProposalHeaderV1` is embedded in Action/StateDelta public outputs; EventIntentBatch shares the exact identity fence but is **a batch of event intents, not a Scheduler/Dynamics Proposal or ChangeSet**. All public `boundary_id` and `read_view_token` are explicit, not derivable from one another. `ProposalContext` carries both directly. Its optional internal `BoundaryRef` is separate and never a public alternate identity. A legacy source `boundary_ref` ingress may be accepted **only** by a named versioned converter that resolves the minted public ID via a one-to-one Harness lookup; unknown/stale reference → `BOUNDARY_REF_INVALID`. No structural duck-typing to swap `EventWindowRefV1`, `ModelIntervalRef`, `ClockRef`, or `BoundaryRef`: wrong class/scope/generation → `WINDOW_REF_TYPE_MISMATCH` or `INTERVAL_MISMATCH`.

### 0.2 Exact normalization, operation and failure correspondence to AI-A

| Component ingress | Required transformation by Harness | Internal output | Rejection |
|---|---|---|---|
| ActionProposalV1 header + actions | verify public header and stage token, resolve kind `task.assign_chain.v1`, preserve ordered task IDs and atomic assignment group | `NormalizedChangeSetV1(phase=APPLY_COMMAND, model_interval_ref=None)` | `STALE_OBSERVATION`, `INVALID_ACTION`, `DOMAIN_OPERATION_UNMAPPED` |
| StateDeltaProposalV1 + interval | verify post-assignment view token, interval issued to **Dynamics**; one `dynamics.motion_energy.v1` operation per vehicle; convert valid `ServiceFactCandidate` to `domain.service_fact.v1` for separate POST_MODEL stage | `NormalizedChangeSetV1(phase=ADVANCE_MODEL, model_interval_ref=validated_ref)` + post-model fact staging, no event reenqueue | `INTERVAL_MISMATCH`, `NONFINITE_VALUE`, `SERVICE_FACT_INVALID` |
| EventIntentBatchV1 | resolve `EventWindowRefV1` from **EventProvider polling window**; validate batch as a whole; normalize each accepted intent through Harness event admission, not directly through Scheduler public propose | `EventEnvelopeV1[]` (queue C); event handlers later produce internal `NormalizedChangeSetV1` in authorized phase | `WINDOW_REF_TYPE_MISMATCH`, `INVALID_EVENT_ORDER`, `EVENT_ID_CONFLICT` |
| Scenario EventSpecV1 | pin scenario source ordinal, convert exact decimal seconds→ns, map registered kind→phase, preserve failure policy and ID | only Harness `EventEnvelopeV1` | `TIME_PRECISION_LOSS`, `UNKNOWN_PHASE_MAPPING` |
| Any previous `NormalizedChangeSetV1` / `change-set.v1` submitted by component | **no converter as a public runtime interface**; only explicitly versioned import of historical *source proposal* accepted at offline migration boundary | none | `CONTRACT_VERSION_MISMATCH` |

**Public header ingress v0→v1 mapping (only named/versioned adapters, never silent):**
`boundary_ref→boundary_id` by Harness ledger; `observed_revision/base_committed_revision→base_revision`; `observed_view_token/based_on_view_token→read_view_token`; `source_component_id→producer_id`; `capability_ref/provenance_ref` checked against immutable registry. Header schema and message schema are **distinct**. `ProposalContext` must not introduce a second public header version. For each `NormalizedChangeSetV1`, validate `proposal_id + source_digest` idempotency and all `OperationV1` reducers before staging; identical ID/digest is one decision, conflicting digest rejects `PROPOSAL_ID_CONFLICT`.

Typed operation variants exactly track #58 §8.3: `task.assign_chain.v1`, `dynamics.motion_energy.v1`, `domain.service_fact.v1`, `domain.event_effect.v1`. Service facts carry `fact_time_ns=model_interval.end_ns`, evidence, deterministic ordinal/ID, and validated custody/service reducer. Position+single battery debit atomic; an `EventEnvelopeV1` is *future queue work*, never the completion fact. Unknown kind/reducer `DOMAIN_OPERATION_UNMAPPED`, not generic JSON field assignment.

**Failure disposition is stage-sensitive, not component-chosen** and maps #58 `ContractFailureV1`: `REJECT_ASSEMBLY` unsupported checkpoint/ABI; `REJECT_REQUEST` invalid pre-admission external command/batch; `ROLLBACK_BOUNDARY` fatal Scheduler/Dynamics/committed-boundary-stage error and full B/C/D/queue/RNG/producer-seq restoration; `SKIP_EVENT` only for predeclared `record_and_skip`, recorded only when full boundary commits; `POSTCOMMIT_PARTIAL` does not rewind physical state; `TAINT_LEGACY` destroys trust in partial legacy worker. `source_code` retains original error alias. Same Run generation only one externally visible revision per accepted boundary. Strict V1 supersedes old ARCH-01 public phase micro-commit **only upon accepted ADR-002**; until then old proposal is not silently edited.

### 0.3 Event-window and timestamp edge-policy proposal for AI-A/ARCH-02/03 co-sign

```python
class EventWindowRefV1:  # opaque, minted by Harness; not interchangeable
    run_id: str
    generation: uint64
    boundary_id: str
    window_token: str
    start_ns: uint64
    end_ns: uint64
    include_start: bool
    include_end: bool
    # start/end and inclusion are validated by Harness, not chosen by provider.
```

**Candidate polling convention**: after the initial t=0 queue is loaded from Scenario, ordinary EventProvider incremental windows use `(start_ns,end_ns]` (exclude start, include end); repeated window identity resolves idempotently and may not resample a logical event. Predeclaration of event source/window must prevent events at exact zero being lost or sampled twice. EventIntentBatch may be empty `intents=()` without failure and without producer_seq increment; invalid batch is all-or-reject, never prefix-enqueued. Harness validates event type/ref/run/gen, exact ns, producer_seq, full digest and phase seal before admission.

**Initial t=0**: `initialize` atomically publishes revision 0 at time 0 and pins initial deterministic Scenario events; the **first opened boundary starting at 0** executes all due PRE_INPUT(0) then PRE_DECISION(0) under a single private stage before its Scheduler view. Initial t=0 EventProvider samples must be loaded once via explicit initial-window/source contract (not via an ordinary window excluding t=0). No external micro-revision; consumed IDs committed once with the boundary. Duplicate t0 ID with different digest → `EVENT_ID_CONFLICT`.

**Horizon policy candidate = INCLUDE_ONCE**: process legal, pre-registered events with `time_ns==horizon_ns` exactly once before final termination evaluation, never any event beyond horizon and no dynamics interval beyond horizon. If horizon event remains due after last positive-duration integration, a **bounded, real event-work zero-duration terminal boundary** is allowed; a zero-duration step solely for metrics with no pending eligible event is forbidden. Scheduler cannot dispatch any motion requiring positive-duration integration after horizon. Termination is evaluated on the committed final state; this explicit policy must be pinned in FrozenRunSpec or assembly rejects horizon ambiguity. An explicitly different EXCLUDE policy requires an **independent versioned protocol profile**, not a runtime guess.

**Late same-time policy candidate = REJECT_AFTER_PHASE_SEAL**: a new event at current time targeting a phase already sealed within the boundary is rejected `INVALID_EVENT_ORDER`, with no silent deferral and no past phase reopening; external command may explicitly resubmit as a **new** future-timestamped intent. A same-time allowed *not-yet-sealed* phase may admit only if its producer sequence, event budget and order can be deterministically checked. After boundary commit at that time, any new event with the same timestamp cannot retroactively modify it. `record_and_skip` is for a predeclared event's domain precondition, **not** an excuse to swallow invalid time/order/schema.

**Versioned kind→phase registry**, examples require ARCH-01/02/03 owner approval and a manifest digest before use: `environment.wind.update→PRE_INPUT`, `vehicle.fail→PRE_INPUT`, `vehicle.recover→PRE_INPUT`, `facility.close/open→PRE_INPUT`, `airspace.activate/expire→PRE_INPUT`, `demand.inject/withdraw→PRE_DECISION`. Domain completion `service_fact` is **POST_MODEL committed fact**, never a scenario or queued provider event kind. Unknown kind, missing manifest mapping or provider phase inconsistent with registry → `UNKNOWN_PHASE_MAPPING/PHASE_CAPABILITY_MISMATCH`; never implicit default. Canonical event sort remains #58 `(time_ns,phase_rank,priority,producer_id UTF8 bytes,producer_seq,event_id UTF8 bytes)`. This is **our explicit candidate for AI-A adoption**; not a fabricated sign-off or alteration of #58.

## 1. Normative candidate: one logical boundary, three categories of records

- **World committed truth B**: `WorldState` & domain fact ledger; **control C**: `Clock / queue / event admission / RNG cursor`; **component-private causal D**: checkpointable provider state; each strict boundary atomically publishes one coherent B/C/D pointer + **one** `revision` and `step_index` increment. All precommit phases use **immutable ProvisionalView** with `stage_seq`; no public micro-commit. Source = #58 `STATE_COMMIT_CONTRACT §§2–5`. #46 still permits visible micro-commit, so not frozen until ARCH-01+ARCH-02+ARCH-03 & coordinator agree.
- **Proposed operations**: Scheduler emits `ActionProposal`; Dynamics emits `StateDeltaProposal`; Event handler/other providers emit typed `ChangeSet` candidates; **only Harness** converts and validates these into an ordered `NormalizedChangeSetV1` staging batch. `ChangeSet` is not an alternative public Scheduler/Dynamics method; `decide/advance` are internal Harness phase names, not provider methods.
- **Queued pending work**: `EventSpecV1` (immutable Scenario source) and `EventIntentV1` (untrusted provider output) **must** be normalized by Harness admission to `EventEnvelopeV1` (single queue schema). A completed service/physical event is a **CommittedDomainFactV1 candidate** in the current ChangeSet, **not** an EventEnvelope accidentally re-entering the past queue. Future time-triggered work is separately emitted as EventIntent and validated.
- **Status and evidence**: committed `BoundaryCommit/CommittedFrame` exist only after atomic publication; precommit attempt diagnostics live outside domain truth; postcommit MetricSamples/RunRecord evidence completeness are separate (CONTRACT-04).

## 2. Public-to-internal field crosswalk (no duplicate type declaration)

**Authoritative candidate type declarations are §0.1** and the same shared field vocabulary as AI-A's #58 `STATE_COMMIT_CONTRACT §8`. Earlier #55 pseudo-types with per-class flat `boundary_ref` are legacy design candidates **superseded for strict public wire use**. The canonical nine identity fields are `run_id, generation, boundary_id, base_revision, read_view_token, proposal_id, producer_id, capability_ref, provenance_ref`; the version tag is `proposal-header.v1-candidate`. `NormalizedChangeSetV1` is *not* a public Proposal subtype.

| Source form | Strict public schema | Harness-only normalized schema | Error |
|---|---|---|---|
| `boundary_ref` (old) | `header.boundary_id` (explicit string) | `boundary_id` validated via original minted RunScope mapping | `BOUNDARY_REF_INVALID` |
| `observed_revision` / `base_committed_revision` | `header.base_revision` | `base_revision` | `REVISION_CONFLICT` |
| `observed_view_token` / `based_on_view_token` | `header.read_view_token` | `read_view_token` | `STALE_OBSERVATION` |
| `source_component_id` | `header.producer_id` | `producer_id` | `CAPABILITY_MISMATCH` |
| `actions` | `ActionProposalV1.actions` | registered `task.assign_chain.v1` typed operation | `DOMAIN_OPERATION_UNMAPPED` |
| `changes + service_facts` | `StateDeltaProposalV1.changes/service_facts` | registered `dynamics.motion_energy.v1` and `domain.service_fact.v1` operations | `SERVICE_FACT_INVALID` |
| public proposal version | message `action-proposal.v1` or `state-delta-proposal.v1` + header version | `normalized-changeset.v1` | `CONTRACT_VERSION_MISMATCH` |

The conversion must be explicit, registered, source-and-output-digest-audited, and total-or-reject. `stage_seq` is not published committed revision; token binds the current authorized phase and cannot be copied from prior generation. `EventIntentBatchV1` has its own batch message with **`window_ref:EventWindowRefV1`**, not Dynamics' `ModelIntervalRef`. No `change-set.v1` public bypass.

## 3. Deterministic, total-or-reject conversions to ChangeSet

```text
[Harness ReadWorldView/ProvisionalView]
   -> ObservationV1 (deep immutable read, run/gen/boundary/stage/ref)
   -> Scheduler.propose -> ActionProposalV1
   -> validate(header, view_token, registered capability)
   -> each AssignTaskChain -> typed AssignTaskChainOperation (single atomic chain)
   -> prevalidate domain refs, versions, task lifecycle, unique ownership, leases, payload & battery
   -> NormalizedChangeSetV1{phase=APPLY_COMMAND, operations=[...], event_intents=[allowed future events]}
   -> stage to overlay (NO commit)
   -> signed new ProvisionalView (same committed revision, incremented stage_seq)
   -> DynamicsModel.propose -> StateDeltaProposalV1
   -> motion/energy -> typed MoveAndConsumeOperation (atomic vehicle delta, finite Wh >= 0)
   -> service_facts -> typed ServiceOrCustodyFactOperation (ARCH-01 evidence and transition validation)
   -> NormalizedChangeSetV1{phase=ADVANCE_MODEL and validated post-model fact stage}
   -> validate all B/C/D + queue/RNG, then ONE boundary publish -> CommittedFrame -> MetricSample
```

**Per-operation required canonical shape (from #58)**: `operation_id:str, target_ref:typed, kind:namespaced, expected_version:uint64? (explicitly nullable only for CREATE), value:typed immutable payload, unit?:str, provenance:ref`. For one AssignTaskChain: one compound operation or multiple ops under a shared *atomic group ID* (no per-task partial acceptance); all ordered task IDs must remain ordered, but order cannot be inferred from set iteration. For a motion/energy candidate, one entity-specific aggregate operation must represent both location and energy debit; **only Committer calculates and writes canonical battery**. ServiceFactCandidate requires domain evidence (custody/waypoint transition); submitting a completion fact does not by itself prove delivered status.

**Converter obligations**: reject unknown operation variant, unauthorized field, dangling/foreign refs, wrong state versions, missing unit/CRS, nonfinite number, negative energy consumed, repeated task assignments, conflicting leases, stale stages and unpinned model. Converter cannot mutate source proposal, consume RNG, enqueue events, advance clock or replace optimizer/physics. Its version & source/output canonical digests are recorded in RunSpec/trace. If domain operation lacks an agreed ARCH-01 typed reducer, return `DOMAIN_OPERATION_UNMAPPED` (no untyped JSON field patch fallback). Repeated identical proposal uses stored decision; two operations with colliding operation_id/different digests are rejected as `PROPOSAL_ID_CONFLICT`.

**Superseded v0 ingress aliases; strict public fields in §0 are mandatory**: `boundary_id`, `read_view_token`, `base_revision`, `producer_id`, `emitted_event_intents`, with original names only as **versioned ingress aliases**. Existing #55 `actions` and `changes` remain domain payloads, **not** alternative authority to commit. Exact final fields need ARCH-03 and ARCH-02 signatures; until then no implicit coercion is allowed.

## 4. Event record conversion and same-time admission (AI-A / CONTRACT-01 owner)

This section *references* #58 `TIME_AND_EVENT_CONTRACT §§2–7` at exact head `bd5e47266d79d1e087ca8cfc6fe68ea28a03496b`; it does **not** re-freeze EventEnvelope, clock or phase rank here.

| Stage | Input → normalized output | Mandatory fields | Explicit converter validation | Failure |
|---|---|---|---|---|
| 0 Scenario | ARCH-01 `EventSpecV1` (immutable) | event_id, time_s, priority, kind, target_ref, payload, preconditions, on_failure, provenance; source manifest + deterministic ordinal | schema/kind map, exact decimal seconds→ns, signed priority int32, declared failure policy; phase via **versioned kind→PhaseV1 mapping** | SCHEMA_MISMATCH, TIME_PRECISION_LOSS, UNKNOWN_EVENT_TYPE, INVALID_PHASE |
| 1 Provider | ARCH-03 `EventIntentV1` (untrusted proposal) | schema_version,event_id,at_seconds,phase,priority,producer_id,producer_seq,kind,target_ref,payload,preconditions,failure_policy,causal_parent_id?,provenance | no unpinned priority_class or stable_order_key interpreted as order; class→int mapping must be pinned; producer seq claim validated by Harness | INVALID_PRIORITY_CLASS, INVALID_PRODUCER_SEQUENCE, PROVENANCE_MISSING |
| 2 Admission | ARCH-02 `EventEnvelopeV1` (only executable queue record) | schema_version,event_id,run_id,generation,time_ns,phase,priority,producer_id,producer_seq,kind,target_ref,payload,preconditions,failure_policy,causal_parent_id?,provenance,payload_digest,attempt | Harness assigns run/generation; fixes exact time_ns, reserves deterministic seq & event identity transactionally; validates monotonic/seal/ID digest | STALE_GENERATION, EVENT_ID_CONFLICT, INVALID_EVENT_ORDER, TIME_REGRESSION |
| 3 Execution | EventEnvelope → EventHandler `NormalizedChangeSetV1` | header, phase, typed domain operations, optional future intents | validate preconditions on latest provisional view; rejection consumes queue item only with successful committed disposition (record_and_skip), not on discarded attempt | EVENT_PRECONDITION_FAILED, STATE_INVARIANT_FAILED |
| 4 Fact | `DomainFactCandidate` → committed domain fact | domain ref, evidence, generating boundary + **fact effective time owned by AI-A** | fact staged POST_MODEL; **not** reinsert as due PRE_INPUT event at same timestamp | INVALID_EVENT_ORDER |
| 5 Future event | permitted emitted EventIntent → newly admitted Envelope | typed future effective time + producer seq | may not insert work into sealed/lower phase at same time; late events require explicit future scheduled boundary or rejection per frozen rule | INVALID_EVENT_ORDER |

**Authoritative proposed queue ordering is copied from #58, not independently invented**:
`(time_ns, phase_rank, priority, producer_id UTF-8 bytes, producer_seq, event_id UTF-8 bytes)`, ascending. PhaseV1 names/ranks proposed by #58: PRE_INPUT(0), PRE_DECISION(1), APPLY_COMMAND(2), ADVANCE_MODEL(3), POST_MODEL(4), OBSERVE(5). `OBSERVE` is postcommit only, not a world-mutating queue phase. Exact-input seconds use decimal×10^9 and must be exact uint64 integral nanoseconds; `3.5` seconds → 3_500_000_000 ns, `3.0000000001` seconds rejected `TIME_PRECISION_LOSS`. No float sort keys, no rounding, no implicit fallback from missing phase/priority.

**Concrete coordinator-directed candidate in §0.3, not yet co-signed**: event kind→phase registry, EventWindowRefV1 polling window inclusion, initial t=0 admission, horizon endpoint inclusivity, late same-time REJECT_AFTER_PHASE_SEAL; committed fact effective-time semantics/field names; `EventIntent` when emitted by Scheduler/Dynamics must be explicitly capability-allowed and assigned producer seq without unordered iteration. These need AI-A/ARCH-01/02/03 + coordinator approval, not silent defaulting.

## 5. Unified failure semantics (recommended error taxonomy + transactional effect)

| Window/source | Canonical error/family; legacy/source aliases | Decision | B committed rev/time | C queue/RNG/sequence | D private state | Evidence |
|---|---|---|---|---|---|---|
| Assemble / init: unsupported method, schema, capability, checkpoint | CONTRACT_VERSION_MISMATCH, CAPABILITY_MISMATCH, CHECKPOINT_UNAVAILABLE; #55 `COMPONENT_RECOVERY_UNSUPPORTED` | FAIL_INIT / REJECT ASSEMBLY | no rev0 published | discard staged init | reverse-order close; fresh provider on retry | init diagnostic |
| External command before boundary admission: stale ref/token or invalid dispatch | STALE_COMMAND, STALE_GENERATION, STALE_PROVISIONAL_VIEW; #55 `STALE_OBSERVATION` | REJECT_COMMAND | unchanged | unchanged | unchanged | rejection-only trace |
| Component proposal after boundary begins: invalid action, energy NaN, unregistered reducer | INPUT_SCHEMA_INVALID, INVALID_STATE_CHANGE, STATE_INVARIANT_FAILED, STATE_CONFLICT, DOMAIN_OPERATION_UNMAPPED | FAIL_RUN by default (**not** silent no-op); only explicit frozen narrow rejection policy may differ | unchanged r | restore fence | abort/restore entire D | precommit failure attempt trace |
| Fatal provider raise/timeout, RNG draw then exception, undo failure | COMPONENT_EXCEPTION / COMPONENT_TIMEOUT / COMPONENT_RECOVERY_UNSUPPORTED | FAIL_RUN; no blind retry | unchanged r | restore if proven; otherwise strict run capability claim invalid, FAILED | restore or TAINTED if proof fails | record first divergence/cause |
| Event with *predeclared* `record_and_skip` and failed precondition | EVENT_PRECONDITION_FAILED / TARGET_NOT_FOUND | REJECT_EVENT disposition **staged**; successful boundary publishes consumed/rejected ledger | exactly one rev if boundary commits | consumption/seq applied only on successful commit | no event's partial effects | rejected event record |
| Event `abort_run` or unbounded/invalid retry | INVALID_EVENT_ORDER, EVENT_CYCLE, EVENT_RETRY_EXHAUSTED | FAIL_RUN & rollback full boundary | unchanged r | restore fence | restore D | terminal diagnostic |
| Event bounded retry `retry_with_limit` | same original event identity + attempt, future exact schedule under frozen policy | only authorized after full retry proof; no zero-backoff retry | depends on later successful boundary | monotonic sequencing, never duplicate RNG draws for logical same event | restore stage before retry | attempt lineage |
| After successful world commit: MetricProvider / export / log failure | OUTPUT_FAILURE / METRIC_UNAVAILABLE / EVIDENCE_INCOMPLETE | MARK_METRIC_UNAVAILABLE or MARK_EVIDENCE_INCOMPLETE; mandatory audit may mark FAILED **at committed revision** | retain r+1 | retain committed | retain committed; metric E may be partial | missing_reason / RunRecord taint |
| Legacy opaque `env.step` partially mutates before exception | LEGACY_TAINTED / COMPONENT_EXCEPTION | TAINTED / FAILED worker; cannot step/checkpoint as strict | no trustworthy rollback assertion | unknown, not assumed restorable | unknown | separate worker restart from pinned input |
| Cleanup after terminal status | CLEANUP_FAILURE | REPORT_CLEANUP_FAILURE | unchanged | unchanged | release best-effort | never overwrite original reason |

**One diagnostic adapter**: `FailureRecordV1` candidate contains `code,severity,run_id,generation,boundary_id?,base_revision?,phase?,component_id?,proposal_id?,event_id?,field_path?,cause_chain,policy,retryable,committed_revision?,trace_ref`. `policy` and `retryable` are frozen decision outputs, not model suggestions. Existing #55 error labels map *to* #58/#49 canonical failure family at Harness boundary; aliases remain in source trace; never relabel `failed` to `success with empty proposals`.

**Rollback invariant**: on any fatal precommit failure, compare before/after canonical digests for B/C/queue/RNG/producer seq/D, plus revision, step_index, sim_time_ns. Aborted stage may append **attempt** logs only, not committed facts. No half-assignment/half-battery debit/half-station lease. Postcommit errors never replay physics; committed RunRecord records partial evidence.

## 6. Co-sign matrix — request is NOT approval

| Decision ID | Owner(s) requested | Expected explicit response on PR #55/#58/#56/#57 | Current |
|---|---|---|---|
| SIG-01 | AI-A / ARCH-02; ARCH-01, ARCH-03 | approve/change/reject single boundary revision; `boundary_ref ↔ boundary_id`, `stage_seq/view_token`, ChangeSet header + ErrorRecord mapping | PENDING |
| SIG-02 | AI-A / ARCH-02; ARCH-01 EventSpec; ARCH-03 EventIntent | approve/change/reject field table and `EventSpec→Intent→Envelope`; kind→phase, producer_seq allocation, t=0, horizon, late work, facts vs queue | PENDING |
| SIG-03 | AI-B / ARCH-03; ARCH-02 & ARCH-01 | approve/change/reject header + `ActionProposal/StateDeltaProposal→ChangeSet` typed reducer mapping, no double debit, allowed emitted intents | PENDING |
| SIG-04 | AI-C / EXP-01; ARCH-02/03 | approve/change/reject transactional RNG port, draw/cursor checkpoint, producer seq and stochastic event identity; no extra RNG on converter | PENDING |
| SIG-05 | AI-D / CONTRACT-04; ARCH-02/03 | approve/change/reject `CommittedFrame→MetricSample/RunRecord` postcommit partial/evidence fields, artifact durability claim | PENDING |
| SIG-06 | ARCH-04 Legacy / AI-E | acknowledge legacy-only Greedy callable vs PSO/GA/OR-Tools `step`, opaque TAINTED/fail-closed; strict vs legacy mode split | PENDING |
| SIG-07 | independent AI-R + coordinator | review all changed immutable HEADs, publish conditional/fail/pass by gate; coordinator records accepted ADR-002/003/006 if approved | PENDING |

**Sign-off evidence must be written by the named owner or authorized reviewer** (PR review/comment or accepted ADR), identify **exact new HEAD SHA**, affected decision IDs and explicit `APPROVE / REQUEST_CHANGES / REJECT`; silence, this author's text, other agents' prior Draft proposals and GitHub posting by AI-B **do not** constitute co-signatures. If input HEAD changes, re-check changed blobs and re-request impacted signatures. PR #59's existing review is against #55 old HEAD, so this change invalidates its #55 schema conclusion scope until incremental re-review.

## 7. Design-only reconciliation acceptance matrix (all NOT_RUN)

| Case | Test input and required observable result | Current |
|---|---|---|
| XW-01 | Scheduler valid Observation(token A) → ActionProposal → ChangeSet(APPLY_COMMAND), Dynamics reads token B, stage→single commit; exactly one r→r+1 | NOT_RUN |
| XW-02 | Same revision but stale stage token; `STALE_PROVISIONAL_VIEW`, B/C/D/RNG/queue unchanged, no further Dynamics call | NOT_RUN |
| XW-03 | Action chain duplicate task or resource conflict; entire boundary rejected/FAILED under declared policy, no half-lease/assignment | NOT_RUN |
| XW-04 | Model NaN Wh, negative Wh, double debit, or missing domain reducer; fatal precommit rollback B/C/D/RNG | NOT_RUN |
| XW-05 | EventSpec 3.5 seconds → exact 3_500_000_000 ns envelope, versioned kind→phase, repeat identical ID idempotent | NOT_RUN |
| XW-06 | 3.0000000001 s / missing phase map / ambiguous priority_class / same ID different digest → hard REJECT with specific code | NOT_RUN |
| XW-07 | POST_MODEL service fact mistakenly queued at earlier PRE_INPUT same time → INVALID_EVENT_ORDER; no retroactive queue work | NOT_RUN |
| XW-08 | Scheduler consumes RNG + mutates staged D then throws: full fence restored; retry only if explicitly allowed and equivalent | NOT_RUN |
| XW-09 | `checkpoint_supported=false` with strict checkpoint/retry request, assemble REJECT, no rev0 | NOT_RUN |
| XW-10 | Event `record_and_skip` failed precondition: rejection ledger+queue consumption only after successful boundary; abort full on subsequent failure | NOT_RUN |
| XW-11 | postcommit MetricProvider exception: world stays at r+1; MetricSample missing_reason and incomplete RunRecord evidence | NOT_RUN |
| XW-12 | Legacy worker partial `env.step` mutation and throw: TAINTED, no trusted checkpoint; historical files SHA unchanged | NOT_RUN |
| XW-13 | Two components same `proposal_id` under same run/gen but different payload digests: PROPOSAL_ID_CONFLICT; no duplicate effect | NOT_RUN |
| XW-14 | Old `SCHEMA_VERSION="1.0"` Legacy observation directly as `ObservationV1`: CONTRACT_VERSION_MISMATCH, no implicit conversion | NOT_RUN |

**Evidence separation**: GitHub commit/changed-file checks prove only documentation delivery, not XW-01..14. Future code PR must run fixtures ST-03/16, C02-05/06/11, C06-01/04, XW-01..14 with command, observed output, code SHA, state/queue/RNG/D digest, and failure trace. Runtime, CI, Legacy parity and physical Validation remain UNVERIFIED.

## 8. Specific review input for #59 / main coordinator

Proposed freeze candidate for B02+B06 is a **single header → typed ChangeSet → staged B/C/D + queue/RNG → one publication** pipeline, with EventEnvelope created only by Harness. Remaining **blocking choices**: (a) #46 micro-commit vs #58; (b) Domain Operation variant/reducer registry; (c) t0/horizon/late-event/phase-kind mapping; (d) exact error code aliases and strict/no-checkpoint gate; (e) RNG cursor/proposer sequence linkage; (f) RunRecord evidence durability. ARCH-06 remains HOLD until signatures + independent tests. A separate B05 `logical_cell_key` mismatch (#56 vs #57) is outside AI-B's edit scope and remains unchanged; does not become resolved by this crosswalk.
