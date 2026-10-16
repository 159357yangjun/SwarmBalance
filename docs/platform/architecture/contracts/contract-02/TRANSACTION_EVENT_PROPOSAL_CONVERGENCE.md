# CONTRACT-02 增量｜事务 / 事件 / Proposal 统一交换规范与会签矩阵

> **STATUS = PROPOSED / CROSS-SIGN PENDING / DESIGN-ONLY；禁止将本文件称为正式冻结 V1 或可执行通过。**
> Owner = AI-B / CONTRACT-02（只编辑 #55 分支），仅定义组件与 Harness 交界的 canonical **candidate** 和总转换表。AI-A/ARCH-02 对 clock、EventEnvelope、phase、single-boundary semantics 保持最终所有权；AI-C 对 RNG 保持所有权；ARCH-01 对 domain operation 保持所有权；主控作 ADR-002/003/006 冻结决定。此稿不直接修改 #58/#56/#57/#59/#60/旧引擎/主线。
>
> **Immutable input ledger (2026-10-16)**：master `2ab60c69a806a22d7ba20353dee0571752a0e8e5`；#54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`；#58/CONTRACT-01 `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377`；#55/CONTRACT-02 **prior to convergence** `b00cd337de2797b9819089b234a113e36513e003`；#56/CONTRACT-03 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`；#57/CONTRACT-04 `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`；#59 independent review `28daf1e336a1447b098b4d6fa044095b7caa1f4f`；#60 implementation gates `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`. Ancestors: #46 `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048`, #47 `68382c649393057ffbf5a14508ab1ff72d575b09`, #49 `d155621aca66e3a80c388718093a452d17d71e10`, #50 `c4c0c67111ead435062650c1ed776547c477e3e3`, #51 `f2df96bc609ee1e430ea6eff2456c4577347c300`.

## 1. Normative candidate: one logical boundary, three categories of records

- **World committed truth B**: `WorldState` & domain fact ledger; **control C**: `Clock / queue / event admission / RNG cursor`; **component-private causal D**: checkpointable provider state; each strict boundary atomically publishes one coherent B/C/D pointer + **one** `revision` and `step_index` increment. All precommit phases use **immutable ProvisionalView** with `stage_seq`; no public micro-commit. Source = #58 `STATE_COMMIT_CONTRACT §§2–5`. #46 still permits visible micro-commit, so not frozen until ARCH-01+ARCH-02+ARCH-03 & coordinator agree.
- **Proposed operations**: Scheduler emits `ActionProposal`; Dynamics emits `StateDeltaProposal`; Event handler/other providers emit typed `ChangeSet` candidates; **only Harness** converts and validates these into an ordered `ChangeSetV1` staging batch. `ChangeSet` is not an alternative public Scheduler/Dynamics method; `decide/advance` are internal Harness phase names, not provider methods.
- **Queued pending work**: `EventSpecV1` (immutable Scenario source) and `EventIntentV1` (untrusted provider output) **must** be normalized by Harness admission to `EventEnvelopeV1` (single queue schema). A completed service/physical event is a **CommittedDomainFactV1 candidate** in the current ChangeSet, **not** an EventEnvelope accidentally re-entering the past queue. Future time-triggered work is separately emitted as EventIntent and validated.
- **Status and evidence**: committed `BoundaryCommit/CommittedFrame` exist only after atomic publication; precommit attempt diagnostics live outside domain truth; postcommit MetricSamples/RunRecord evidence completeness are separate (CONTRACT-04).

## 2. Canonical ProposalHeaderV1 candidate (shared for all component proposals)

The original #55 proposals have `boundary_ref` and `observed_view_token` / `based_on_view_token`; #58 ChangeSet demands `boundary_id, phase, read_view_token, operations, emitted_event_intents`. The following **common header** replaces ad-hoc name translation at the Harness intake boundary; it is **not yet a frozen wire ABI**.

```python
# PSEUDOTYPES; own schema_version tokens await ARCH-03/02 sign-off.
class ProposalHeaderV1:
    schema_version: str               # action-proposal.v1 | state-delta-proposal.v1 | change-set.v1
    proposal_id: str                  # deterministic within run/generation; idempotency digest pair
    run_id: str
    generation: int                   # uint64; Harness-issued
    boundary_id: str                  # Harness-issued, one logical boundary
    base_revision: int                # uint64, last externally committed revision
    read_view_token: str              # opaque Harness-issued token tied to stage_seq
    producer_id: str                  # registered ComponentDescriptor.id
    capability_ref: str               # frozen versioned capability & allowed operation kinds
    provenance_ref: str               # pinned source/implementation/model/assembly digest
    # body_digest is computed by converter over canonical semantic content; not supplied as trust authority.

class ActionProposalV1:
    header: ProposalHeaderV1
    actions: tuple["AssignTaskChain", ...]         # existing #55 kind and stable EntityId based
    emitted_event_intents: tuple["EventIntentV1", ...]  # default empty, only if capability allowed

class StateDeltaProposalV1:
    header: ProposalHeaderV1
    model_interval_ref: str
    changes: tuple["MotionEnergyChange", ...]
    service_facts: tuple["DomainFactCandidate", ...]
    emitted_event_intents: tuple["EventIntentV1", ...]  # future queue work ONLY

class ChangeSetV1:
    header: ProposalHeaderV1
    phase: "PhaseV1"                 # ARCH-02/AI-A assigned and capability-validated
    operations: tuple["TypedDomainOperation", ...]
    emitted_event_intents: tuple["EventIntentV1", ...]
```

**Field name authority & explicit aliases**:

| Concept | #55 prior shape | #58 target | Candidate rule | Reject |
|---|---|---|---|---|
| Run/generation | `run_id,generation` | same | exact equality with RunScope | RUN_MISMATCH / STALE_GENERATION |
| Boundary | `boundary_ref` opaque | `boundary_id` string | Harness resolves/ref→ID via one-to-one RunScope registry; never parse token or choose ID client-side | BOUNDARY_ID_CONFLICT |
| Base state | `observed_revision` or `base_committed_revision` | `base_revision` | exact committed revision; neither stage counter nor step number | REVISION_CONFLICT |
| Stage | `observed_view_token` / `based_on_view_token` | `read_view_token` | token must belong to expected *stage_seq* and same run/gen/boundary; same revision does not imply same stage | STALE_PROVISIONAL_VIEW (public alias STALE_OBSERVATION) |
| Producer | `source_component_id` | `producer_id` | equality with trusted descriptor identity | CAPABILITY_MISMATCH |
| Phase | inferred Scheduler/Dynamics call context | required `PhaseV1` | **Harness assigns** from registered category+phase capability; Scheduler APPLY_COMMAND; Dynamics ADVANCE_MODEL **proposal context only**, service fact POST_MODEL as separate validated domain stage; no component-enforced event order | INVALID_PHASE |
| Operations | `actions` / `changes` / `service_facts` | `operations` | typed, versioned and deterministic conversion; see §3 | INPUT_SCHEMA_INVALID |
| Emissions | service_facts ambiguous in #55 | `emitted_event_intents` | service fact becomes domain fact operation, not queue item; future scheduled events are separate intents | EVENT_ORDER_INVALID |
| Source digests | `capability_ref,provenance_ref,model_manifest_digest` | `provenance` on operation | require pinned manifest/reference + conversion version; no ad hoc missing value | PROVENANCE_MISSING |
| Identity digest | `proposal_id` only | idempotency ledger + canonical content digest | same ID & semantic digest returns recorded decision, same ID/different digest hard reject; no double effects | PROPOSAL_ID_CONFLICT |

**Token rules**: `ProvisionalView` carries base revision, boundary_id, stage_seq and read_view_token; `ObservationV1` echoes these through `ProposalContext` and never manufactures tokens. Scheduler view comes after PRE_INPUT/PRE_DECISION staging; Dynamics view after accepted APPLY_COMMAND staging; metrics see only `CommittedFrame`. Any token from prior generation/phase, even with same base revision, fails closed.

## 3. Deterministic, total-or-reject conversions to ChangeSet

```text
[Harness ReadWorldView/ProvisionalView]
   -> ObservationV1 (deep immutable read, run/gen/boundary/stage/ref)
   -> Scheduler.propose -> ActionProposalV1
   -> validate(header, view_token, registered capability)
   -> each AssignTaskChain -> typed AssignTaskChainOperation (single atomic chain)
   -> prevalidate domain refs, versions, task lifecycle, unique ownership, leases, payload & battery
   -> ChangeSetV1{phase=APPLY_COMMAND, operations=[...], event_intents=[allowed future events]}
   -> stage to overlay (NO commit)
   -> signed new ProvisionalView (same committed revision, incremented stage_seq)
   -> DynamicsModel.propose -> StateDeltaProposalV1
   -> motion/energy -> typed MoveAndConsumeOperation (atomic vehicle delta, finite Wh >= 0)
   -> service_facts -> typed ServiceOrCustodyFactOperation (ARCH-01 evidence and transition validation)
   -> ChangeSetV1{phase=ADVANCE_MODEL and validated post-model fact stage}
   -> validate all B/C/D + queue/RNG, then ONE boundary publish -> CommittedFrame -> MetricSample
```

**Per-operation required canonical shape (from #58)**: `operation_id:str, target_ref:typed, kind:namespaced, expected_version:uint64? (explicitly nullable only for CREATE), value:typed immutable payload, unit?:str, provenance:ref`. For one AssignTaskChain: one compound operation or multiple ops under a shared *atomic group ID* (no per-task partial acceptance); all ordered task IDs must remain ordered, but order cannot be inferred from set iteration. For a motion/energy candidate, one entity-specific aggregate operation must represent both location and energy debit; **only Committer calculates and writes canonical battery**. ServiceFactCandidate requires domain evidence (custody/waypoint transition); submitting a completion fact does not by itself prove delivered status.

**Converter obligations**: reject unknown operation variant, unauthorized field, dangling/foreign refs, wrong state versions, missing unit/CRS, nonfinite number, negative energy consumed, repeated task assignments, conflicting leases, stale stages and unpinned model. Converter cannot mutate source proposal, consume RNG, enqueue events, advance clock or replace optimizer/physics. Its version & source/output canonical digests are recorded in RunSpec/trace. If domain operation lacks an agreed ARCH-01 typed reducer, return `DOMAIN_OPERATION_UNMAPPED` (no untyped JSON field patch fallback). Repeated identical proposal uses stored decision; two operations with colliding operation_id/different digests are rejected as `PROPOSAL_ID_CONFLICT`.

**Required proposed fields on #55 existing types**: `boundary_id`, `read_view_token`, `base_revision`, `producer_id`, `emitted_event_intents`, with original names only as **versioned ingress aliases**. Existing #55 `actions` and `changes` remain domain payloads, **not** alternative authority to commit. Exact final fields need ARCH-03 and ARCH-02 signatures; until then no implicit coercion is allowed.

## 4. Event record conversion and same-time admission (AI-A / CONTRACT-01 owner)

This section *references* #58 `TIME_AND_EVENT_CONTRACT §§2–6` at exact head `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377`; it does **not** re-freeze EventEnvelope, clock or phase rank here.

| Stage | Input → normalized output | Mandatory fields | Explicit converter validation | Failure |
|---|---|---|---|---|
| 0 Scenario | ARCH-01 `EventSpecV1` (immutable) | event_id, time_s, priority, kind, target_ref, payload, preconditions, on_failure, provenance; source manifest + deterministic ordinal | schema/kind map, exact decimal seconds→ns, signed priority int32, declared failure policy; phase via **versioned kind→PhaseV1 mapping** | SCHEMA_MISMATCH, TIME_PRECISION_LOSS, UNKNOWN_EVENT_TYPE, INVALID_PHASE |
| 1 Provider | ARCH-03 `EventIntentV1` (untrusted proposal) | schema_version,event_id,at_seconds,phase,priority,producer_id,producer_seq,kind,target_ref,payload,preconditions,failure_policy,causal_parent_id?,provenance | no unpinned priority_class or stable_order_key interpreted as order; class→int mapping must be pinned; producer seq claim validated by Harness | INVALID_PRIORITY_CLASS, INVALID_PRODUCER_SEQUENCE, PROVENANCE_MISSING |
| 2 Admission | ARCH-02 `EventEnvelopeV1` (only executable queue record) | schema_version,event_id,run_id,generation,time_ns,phase,priority,producer_id,producer_seq,kind,target_ref,payload,preconditions,failure_policy,causal_parent_id?,provenance,payload_digest,attempt | Harness assigns run/generation; fixes exact time_ns, reserves deterministic seq & event identity transactionally; validates monotonic/seal/ID digest | STALE_GENERATION, EVENT_ID_CONFLICT, INVALID_EVENT_ORDER, TIME_REGRESSION |
| 3 Execution | EventEnvelope → EventHandler `ChangeSetV1` | header, phase, typed domain operations, optional future intents | validate preconditions on latest provisional view; rejection consumes queue item only with successful committed disposition (record_and_skip), not on discarded attempt | EVENT_PRECONDITION_FAILED, STATE_INVARIANT_FAILED |
| 4 Fact | `DomainFactCandidate` → committed domain fact | domain ref, evidence, generating boundary + **fact effective time owned by AI-A** | fact staged POST_MODEL; **not** reinsert as due PRE_INPUT event at same timestamp | INVALID_EVENT_ORDER |
| 5 Future event | permitted emitted EventIntent → newly admitted Envelope | typed future effective time + producer seq | may not insert work into sealed/lower phase at same time; late events require explicit future scheduled boundary or rejection per frozen rule | INVALID_EVENT_ORDER |

**Authoritative proposed queue ordering is copied from #58, not independently invented**:
`(time_ns, phase_rank, priority, producer_id UTF-8 bytes, producer_seq, event_id UTF-8 bytes)`, ascending. PhaseV1 names/ranks proposed by #58: PRE_INPUT(0), PRE_DECISION(1), APPLY_COMMAND(2), ADVANCE_MODEL(3), POST_MODEL(4), OBSERVE(5). `OBSERVE` is postcommit only, not a world-mutating queue phase. Exact-input seconds use decimal×10^9 and must be exact uint64 integral nanoseconds; `3.5` seconds → 3_500_000_000 ns, `3.0000000001` seconds rejected `TIME_PRECISION_LOSS`. No float sort keys, no rounding, no implicit fallback from missing phase/priority.

**Open, not independently decided here**: event kind→phase registry, EventProvider polling window inclusion, initial t=0 event admission, horizon endpoint inclusion, late same-time policy; committed fact effective-time semantics/field names; `EventIntent` when emitted by Scheduler/Dynamics must be explicitly capability-allowed and assigned producer seq without unordered iteration. These need AI-A/ARCH-01/02/03 + coordinator approval, not silent defaulting.

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
