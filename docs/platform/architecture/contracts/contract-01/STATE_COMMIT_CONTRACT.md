# CONTRACT-01 — STATE_COMMIT_CONTRACT

> Task: CONTRACT-01 / ARCH-05-R2 B01 (and the state side of B03). Status: PROPOSED / Draft design only; not an accepted ADR, executable API, or verified transaction implementation.
>
> Proposed owner: ARCH-02 (Harness transaction); domain-schema co-signer: ARCH-01; component-protocol co-signer: ARCH-03; legacy disclosure: ARCH-04; final freeze: coordinator via ADR-002.
>
> Baseline verified 2026-10-16: master **2ab60c69a806a22d7ba20353dee0571752a0e8e5**, PR #54 **99bd0eb6b910d691d6d7776da0a5fd3f973f2997**, PR #46 **b5f05a70a3306f1799fcae2c3f342f3ed9ee0048**, PR #49 **d155621aca66e3a80c388718093a452d17d71e10**, PR #47 **68382c649393057ffbf5a14508ab1ff72d575b09**, PR #51 **f2df96bc609ee1e430ea6eff2456c4577347c300**. All five were open Draft PRs; PR #54's reviewed heads for #46/#49/#47 still match. Governance registry and ADR-002 remain **PROPOSED/OPEN**.

## 1. Evidence and conflict decision

- ARCH-01 [WORLD_STATE §1–§6](https://github.com/159357yangjun/SwarmBalance/blob/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world/WORLD_STATE.md): one WorldState writer, immutable ReadView, proposals and domain invariants; §3 explicitly permits multiple visible same-time phase micro-commits with independent revisions.
- ARCH-02 [STATE_OWNERSHIP §1–§5](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/STATE_OWNERSHIP.md) and [RUNTIME_SEQUENCE §2](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/RUNTIME_SEQUENCE.md): one atomic *externally visible* execution-boundary commit, internal provisional views, transactional clock/queue/RNG rollback.
- ARCH-03 [COMPONENT_CONTRACTS §1–§4](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md): versioned Observation/ActionProposal/StateDeltaProposal/CommittedFrame and no direct writes; interfaces not yet jointly frozen.
- Independent [ARCH-05-R2 B01/B03](https://github.com/159357yangjun/SwarmBalance/blob/99bd0eb6b910d691d6d7776da0a5fd3f973f2997/docs/platform/architecture/review/ARCH_05_R2_CROSS_REVIEW.md) grades both P0 HOLD.

**CONTRACT-01 resolution proposal:** V1 STRICT_ATOMIC_BOUNDARY mode has **zero externally published micro-commits**. The ARCH-01 phase micro-commit concept is replaced **inside this mode** by a validated, privately versioned provisional overlay. Each successful execution boundary publishes exactly one committed revision and coherent state/control checkpoint. If later required, phase-visible micro-commit is a separate **future protocol/mode and breaking visibility contract**, not an undocumented flag. This file does not silently amend PR #46 or #49; ARCH-01/02/03 must co-sign.

## 2. State authority and mutation matrix

- **A / immutable inputs**: Project/WorldDefinition/Scenario, component lock, datasets and model manifests; pinned by Run assembly; no in-run edits.
- **B / domain truth**: per-(run_id,generation) WorldState: entities, tasks/assignments/cargo custody, resource leases and queues, dynamic fields, applied-event ledger and event cursor. **Only Harness StateCommitter** publishes validated B. ARCH-01 owns B schema, referential and domain invariants, not the mutation capability.
- **C / deterministic control**: Harness clock, event priority queue, admission counters, RNG stream positions, boundary counter, run generation and protocol metadata. Commit with B as a single *logical transaction*; only Harness mutates.
- **D / component-private causal state**: owned by individual provider; allowed only when precommit operations are pure or support reliable snapshot/stage/rollback. Declared checkpoint capability mandatory for strict mutable D; otherwise reject assembly for strict mode. Not a second authority for B.
- **E / read-only projections**: UI, metrics, trace and exports. Observe committed B/C only; never feed world truth via a hidden mutable alias. Non-world diagnostics are an append-only evidence sidecar and cannot be mistaken for a WorldState revision.

**Mutation matrix**

| Actor | Read | May mutate/publish | Forbidden |
|---|---|---|---|
| Harness RunController/StateCommitter (ARCH-02) | A–D via scoped APIs | Validate/stage/publish B; coordinate C; checkpoint D | Invent domain physics/rules |
| ARCH-01 validators | Frozen definitions and proposed state | Pure validation result | Publish B/C or mutate input |
| Data/Spatial/EventProvider (ARCH-03) | Pinned resources and scoped views | Initialization/event/patch proposals; own declared D | Direct B/C mutations |
| Scheduler/Dynamics (ARCH-03) | Immutable provisional observation | Action/StateDelta proposals; own rollback-safe D | Call mutable StateStore; issue phantom commits |
| MetricProvider/UI/Experiment | CommittedFrame/trace | Their derived E; external command **request** into Harness admission API | Mutate world via observations |
| LegacyEnvironmentAdapter (ARCH-04) | Controlled legacy env | In-place opaque legacy step **only in LEGACY_OPAQUE_STEP** | Advertise V1 atomicity or exact rollback without separate proof |

## 3. Core interfaces: fields, types, responsibility, failure

**Canonical types:** string identifiers are stable, case-sensitive and scoped; uint64 is 0…2^64−1; integer nanoseconds uint64 in this proposal with maximum/overflow policy frozen in RunSpec; digest is SHA-256 of canonicalized bytes. All collections exposed to components are deeply immutable/value-copied.

| Interface / field | Type and semantics | Producer / owner | Invalid input or failure |
|---|---|---|---|
| WorldState.schema_version | string, literal worldstate.v1 for this proposal | ARCH-01 defines; Harness checks | SCHEMA_MISMATCH; no publish |
| WorldState.run_id, generation | string, uint64; authoritative per-run identity | Harness | STALE_GENERATION / RUN_MISMATCH |
| WorldState.world_ref, scenario_ref | frozen {id:string,revision:uint64,digest:string} | ARCH-01 definition; Harness pin | UNKNOWN_REFERENCE / DIGEST_MISMATCH |
| WorldState.revision | uint64; increments **once** per successful boundary; starts at 0 after initialization | Harness | REVISION_CONFLICT; no mutation |
| WorldState.sim_time_ns, step_index | uint64, uint64; committed logical time and number of successful boundaries; start at 0 | Harness Clock | TIME_REGRESSION / STEP_CONFLICT |
| WorldState.entities, tasks, resource_ledger, dynamic_fields | typed maps, ARCH-01 domain invariants; stable EntityId, no arbitrary mutable objects | ARCH-01 schema; Harness writes | STATE_INVARIANT_FAILED / CUSTODY_CONFLICT / RESOURCE_CAPACITY_EXCEEDED |
| WorldState.applied_event_ids, event_cursor | canonical event ID→payload digest/status and last executed queue key; run-scoped | Harness | EVENT_ID_CONFLICT / EVENT_ORDER_INVALID |
| ReadWorldView.run_id, generation, revision, sim_time_ns | immutable scalars from **last published** state | Harness | stale view rejected at admission |
| ProvisionalView.base_revision, boundary_id, stage_seq, view_token | uint64, string, uint64, opaque string; private *stage identity*, not committed revision | Harness | STALE_PROVISIONAL_VIEW; never externally exposed as committed |
| ProvisionalView.readonly_state | deep-immutable composed B overlay through stage_seq; does **not** expose C mutable references | Harness | MUTABLE_REFERENCE_LEAK = contract failure |
| NormalizedChangeSetV1.run_id, generation, boundary_id, base_revision | string,uint64,string,uint64: Harness internal optimistic concurrency fence after converting public ProposalHeaderV1 | Harness ARCH-02 only (ARCH-03 supplies ActionProposalV1/StateDeltaProposalV1) | STALE_OBSERVATION / STATE_CONFLICT |
| NormalizedChangeSetV1.producer_id, proposal_id, phase | stable string, stable string, Harness-assigned PhaseV1; unique idempotent producer proposal per run generation | Component supplies ProposalHeaderV1 fields; Harness maps and assigns phase | PROPOSAL_ID_CONFLICT / INVALID_PHASE |
| ProposalHeaderV1.read_view_token → NormalizedChangeSetV1.read_view_token | opaque stage token from Harness, echoed in public header; required in strict mode | Harness issues and validates; component echoes without interpretation | STALE_OBSERVATION (source STALE_PROVISIONAL_VIEW) |
| NormalizedChangeSetV1.operations | ordered array of {operation_id:string, target_ref:typed ref, kind: namespaced string, expected_version:uint64?, value: typed, unit?:string, provenance:ref}; semantically atomic, typed reducer only | Harness converter outputs; ARCH-01 validates; Harness stages and commits | DOMAIN_OPERATION_UNMAPPED, UNKNOWN_REFERENCE, UNIT_MISMATCH, STATE_CONFLICT |
| NormalizedChangeSetV1.emitted_event_intents | EventIntentV1[]: converted from authorized public proposal emissions, never direct queue writes | Harness converter and event-admission owner | INVALID_EVENT_ORDER; staged event rejected |
| BoundaryFence | {run_id, generation, boundary_id, base_revision, start_ns, selected_end_ns, queue_checkpoint, rng_checkpoint, private_state_tokens, admission_counter_checkpoint}; all internal immutable/checkpoint tokens | Harness ARCH-02; ARCH-03 supplies D restore | CHECKPOINT_UNAVAILABLE; refuse strict invocation |
| BoundaryCommit | {boundary_id, from_revision, to_revision, committed_step_index, sim_time_ns, applied_operation_ids[], accepted_event_ids[], rejected_event_ids[], state_digest, control_digest}; only generated upon success | Harness | no BoundaryCommit on rejected boundary |
| CommittedFrame | {run_id,generation,revision,step_index,at_ns,at_seconds,readonly_state,accepted_events,rejected_proposals,boundary_id,commit_digest}; visible only after commit | Harness; ARCH-03 consumes | UNSAFE_FRAME / EVIDENCE_INCOMPLETE if publication fails |

**Proposal idempotency**: identical proposal_id + canonical content digest in one generation yields the recorded decision, never duplicate application; same ID with different content is a hard integrity rejection. Stage-sequence may advance internally without a WorldState revision change. Consumers compare **both** generation and revision; generation reset invalidates old views even if revision reverts to zero.

**Semantics test pairing**: positive ST-01/ST-02/ST-04/ST-06/ST-11 and negative ST-03/ST-05/ST-07/ST-08/ST-12 in STATE_EVENT_TEST_CASES.md; every table row is covered either directly or by one of these family tests.

## 4. Exact V1 boundary algorithm

1. **Admission barrier**: serialize requests; select boundary_id and clock policy. Freeze base committed (B,C,D) fence, time [start_ns,selected_end_ns], event admission order, and input/component digests. Reject stale/unrepresentable commands **before** any stage publication.
2. **Pre-input / pre-decision**: deterministically dequeue due external facts and accepted EventIntent; stage validations against copy-on-write B overlay. Each substage creates an immutable ProvisionalView(stage_seq+1), still **base_revision=r**. Scheduler reads this provisional state, so same-timestamp faults and arrivals accepted before decision affect dispatch.
3. **Commands / model**: apply validated Scheduler operations to the overlay; run Dynamics against the *latest* staged view with an explicit interval and time context. Stage atomic position/energy/status, service/custody/lease consequences and event results. Reject unregistered reducers or hidden second writers. Post-model domain facts are proposals/commit facts, not automatically externally scheduled EventEnvelope (see TIME_AND_EVENT_CONTRACT.md §5).
4. **Prepare**: validate whole candidate B/C/D plus reference/custody/capacity, numeric/CRS/unit, base and view-token fences, event ordering and dedup, event-cycle bound, component private-state rewind capability, RNG/queue cursors. Deterministically resolve only versioned permitted reducers; otherwise STATE_CONFLICT.
5. **Atomic publish**: with a per-run serialized writer, swap coherent committed B/C/D checkpoint pointer **as one logical boundary**, assign revision=r+1 and step_index=s+1, freeze queue/RNG/sequence counters, record BoundaryCommit digest. Readers see wholly r or wholly r+1. Domain effects, time and control never publish separately. Snapshot/CommittedFrame and postcommit observers only run after publish.
6. **No-op**: if no domain/control transition, no elapsed time and no accepted/rejected-event disposition, return NO_BOUNDARY without revision/step_index increment. A legitimately consumed skipped event changes control/ledger and therefore commits one boundary.
7. **Failure precommit**: discard full stage overlay and restore *all* queue/RNG/sequence/D snapshots; last committed B/C and revision/step_index/time remain unchanged. Record a diagnostic outside B. Default fatal component failure marks Run FAILED without fabricating a new world revision. Valid declared per-event record_and_skip policy can discard that event's **entire local proposal** and stage a recorded rejection/queue consumption, then still commit the boundary; never partially apply that event.
8. **Failure postcommit**: do not rewind the committed pointer; preserve r+1 and snapshot visibility; MetricProvider/export/logger failures mark output PARTIAL or EVIDENCE_INCOMPLETE, with a separate FailureRecord. If mandatory audit evidence fails, Run may become FAILED at the committed revision. No automated re-execution of already committed physics.

**Logical atomicity vs durable storage:** the proposal requires in-memory coherent visibility. It does **not** assert that the current code persists B/C/D and evidence on disk in a single durable database transaction. Snapshot/artifact durability and crash-consistency require separate implementation design and CONTRACT-04 co-sign.

## 5. Boundary, clock and snapshot visibility

- Initialization atomically publishes (generation g, revision 0, step_index 0, sim_time_ns 0) after validation. No incomplete initial WorldState is visible.
- Every committed boundary advances **revision and step_index by one** in strict V1, but these are separate concepts: revision fences state identity; step_index counts accepted execution boundaries, **not seconds**. Clock may advance by 0 in a bounded event boundary; no revision changes within a boundary. A reset creates a new generation and rev=0, not a backwards transition within one generation.
- A public snapshot request during a boundary returns latest **previous committed frame** (r), or waits until the barrier depending on a declared consistency API; it never returns provisional slices. Snapshot identity is (run_id,generation,revision) plus digest and pinned definition refs.
- Pausing/stopping is acknowledged only after commit or rollback barrier. No component-private pending output enters a committed snapshot unless its deterministic state is included in the transaction fence.
- An external event exactly at current time must be admitted before that timestamp's input-phase seal; after seal, reject late same-time injection (or ask caller to explicitly schedule a later valid timestamp). Do not reopen a past phase after publication or create ad-hoc visible micro-commits.
- Per-time queue events may cascade **within** the open boundary only while phase is monotonic and the predeclared same-time budget has not been exceeded. A cyclic same-time cascade aborts the entire boundary.
- A terminal/post-model service-completion **fact** belongs to the boundary's committed B and trace; only an explicitly scheduled **future** event is an EventEnvelope. Confusing a completed fact with a pending queue event creates a time-order ambiguity and is forbidden in strict mode.

## 6. Failure outcomes and trust

| Window | Example | Committed state | Queue/RNG/D | Result / snapshot |
|---|---|---|---|---|
| Assembly / init | Bad manifest | no rev=0 | discard staged init | INIT_FAILED; no world snapshot |
| Pre-admission | Stale UI command | unchanged r | unchanged | REJECT_COMMAND; r still visible |
| Precommit hard | NaN, conflicting assignment, fault in Dynamics | unchanged r | restore fence | FAILED by default; r still visible |
| Precommit expected soft event rejection | Missing optional target with frozen record_and_skip | no partial event changes; other stage accepted on declared policy | rejected event consumed **on** successful boundary commit | committed r+1 incl rejection ledger |
| Atomic publish success | Valid boundary | r+1 only | checkpointed with B | one CommittedFrame |
| Postcommit | metric/export failure | r+1 stays | no rewind | PARTIAL/EVIDENCE_INCOMPLETE; r+1 visible |
| Legacy opaque | env.step mutates then throws | unknown partial state | not proven rewindable | TAINTED/FAILED; not strict snapshot |

Required errors identify run_id, generation, boundary_id, base_revision, component, event/proposal ID, code, phase, whether a revision committed, and severity. A failed command is not a successful empty action. A trace written precommit is explicitly **attempt/diagnostic**, not committed domain truth.

## 7. Cross-group signature requests and questions for coordinator

| Decision | Proposed owner / required sign-offs | Remains blocked until |
|---|---|---|
| Single published boundary revision vs ARCH-01 micro-commit | **ARCH-02 owner, ARCH-01 and ARCH-03 sign** | ADR-002 ACCEPTED and PR #46/#49 reconciliation |
| ProvisionalView token and B/C/D fence | **ARCH-02 owner; ARCH-03**, ARCH-01 invariant validator | component retry/private checkpoint protocol agreed (B06 with CONTRACT-02) |
| WorldState entity/task/custody/lease schema | **ARCH-01 owner; ARCH-02/03** | semantic operations and versions co-signed |
| CommittedFrame/Metric postcommit behavior | **ARCH-03 and ARCH-02**, CONTRACT-04 | observation and evidence statuses co-signed |
| Snapshot compatibility, crash durability, legacy opacity | **ARCH-02**, ARCH-04 and CONTRACT-04 | capability gates and durable-evidence scope defined |
| Time/phase/event schema | **ARCH-02**, ARCH-01/03 and CONTRACT-03 for RNG | TIME_AND_EVENT_CONTRACT.md co-signed |

**Coordinator arbitration required** if: any group insists on externally visible phase micro-commits; a strict component cannot checkpoint D; shared-time input admission/rejection or post-model fact-to-event boundary is rejected; or versioned domain reducer conflicts need precedence. Until sign-off this is a proposed resolution, not an unconditional V1 freeze. No Python/runtime, CI, replay, or empirical validation is claimed.


---

## 8. Joint transaction + Proposal normalization amendment (AI-A / CONTRACT-02 alignment, 2026-10-16)

> **Proposed schema pack `state-event-proposal.v1-candidate-1`, NOT jointly accepted.** This addendum refines §§3–7 and specifies the complete correspondence with [CONTRACT-02 PROPOSAL_AND_OBSERVATION_SCHEMA](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/PROPOSAL_AND_OBSERVATION_SCHEMA.md) at PR #55 HEAD `b00cd337de2797b9819089b234a113e36513e003`. #58 pre-amendment HEAD `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377`. CONTRACT-03 #56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`, CONTRACT-04 #57 `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`, CONTRACT-05 #60 `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955` read for cross-contract dependencies; #59 `28daf1e336a1447b098b4d6fa044095b7caa1f4f` identifies the missing Proposal→ChangeSet mapper. This addendum does **not** rewrite or approve the others' Drafts. In case of apparent conflict with the earlier generic `ChangeSet` table, the exact mapping below is the **candidate resolution within CONTRACT-01**; upstream interfaces remain proposed.

### 8.1 Exactly one write path, not three competing protocols

```text
ARCH-03 Scheduler.propose(ObservationV1, ProposalContext)
  -> ActionProposalV1 [COMPONENT OUTPUT, never executable]
    -> Harness ProposalNormalizer -> NormalizedChangeSetV1
ARCH-03 DynamicsModel.propose(StateSliceView, Conditions, ModelIntervalRef, ProposalContext)
  -> StateDeltaProposalV1 [COMPONENT OUTPUT, never executable]
    -> Harness ProposalNormalizer -> NormalizedChangeSetV1
ARCH-03 EventProvider.events_in_window(..., ProposalContext)
  -> EventIntentV1 [QUEUE CANDIDATE] -> Harness event admission -> EventEnvelopeV1
    -> domain event handler returns NormalizedChangeSetV1
All NormalizedChangeSetV1 items
  -> StateCommitter validate + stage B / C / D, single boundary publish
  -> CommittedFrameV1 after commit -> MetricProvider.observe
```

`ChangeSet` is the **internal Harness normalization product**, not a public third component protocol; `ActionProposalV1` and `StateDeltaProposalV1` remain the **only** Scheduler/Dynamics public outputs. `decide/advance` in ARCH-02 remain phase descriptions, not alternative public signatures. Components cannot submit `NormalizedChangeSetV1` as a backdoor.

### 8.2 One canonical scope header / aliases frozen by future co-sign

| Canonical normalized field and type | ActionProposalV1 input | StateDeltaProposalV1 input | Invariant, writer and failure |
|---|---|---|---|
| `schema_version:string` = `normalized-changeset.v1` | `schema_version=action-proposal.v1` | `schema_version=state-delta-proposal.v1` | ARCH-03 provides recognized major; Harness converts or CONTRACT_VERSION_MISMATCH |
| `proposal_id:string` | `proposal_id` | `proposal_id` | Stable run/generation-scoped idempotency; same ID + unequal source digest PROPOSAL_ID_CONFLICT |
| `producer_id:string` | `source_component_id` | `source_component_id` | Must match selected manifest/capability; CAPABILITY_MISMATCH |
| `run_id:string`, `generation:uint64` | same | same | Harness admission fence; RUN_MISMATCH / STALE_GENERATION |
| `boundary_id:string` PUBLIC | `header.boundary_id:string` (prior `boundary_ref` is versioned ingress alias) | `header.boundary_id:string` (prior `boundary_ref` is versioned ingress alias) | Harness-issued run-local boundary identity; alias accepted only through explicitly versioned adapter with registry lookup, never guessed; BOUNDARY_ID_CONFLICT |
| `base_revision:uint64` | `observed_revision` | `base_committed_revision` | Committed fence, never provisional stage number; STALE_OBSERVATION |
| `read_view_token:OpaqueRef` | `observed_view_token` | `based_on_view_token` | Same issued stage and allowed component; STALE_OBSERVATION even if revision equal |
| `phase:PhaseV1` | `APPLY_COMMAND` from authenticated invocation slot | `ADVANCE_MODEL` from authenticated invocation slot | Phase **not component-chosen**; PHASE_CAPABILITY_MISMATCH |
| `operations:OperationV1[]` | normalized `actions[]` | normalized `changes[]` plus `service_facts[]` mapped to candidate facts | Deterministically ordered; domain validity + cross-object atomicity; INPUT_SCHEMA_INVALID / STATE_INVARIANT_FAILED |
| `capability_ref:string` | same | same | Frozen descriptor capability; CAPABILITY_MISSING |
| `source_digest:string` | canonical signed input digest of ActionProposal + `provenance_ref` | canonical signed input digest of StateDelta + `model_manifest_digest` | Deterministic bytes/version pinned before stage; PROVENANCE_MISSING |
| `model_interval_ref:OpaqueRef?` | null (not a model operation) | `model_interval_ref` required | Harness-resolved `{start_ns,end_ns}` with validated `duration_seconds`; INTERVAL_MISMATCH |
| `emitted_event_intents:EventIntentV1[]` | none unless independently authorized operation kind | **not derived from `service_facts`**; only an explicit future scheduling result | Runtime queue insertion via EventEnvelope admission only; INVALID_EVENT_ORDER |

`ProposalContext` is a Harness-issued read-only capability bundle: `run_id:string`, `generation:uint64`, `boundary_id:string`, `read_view_token:OpaqueRef`, `clock_ref:OpaqueRef`, `readonly_resources:FrozenResourcePort`, `scoped_rng:TransactionalRNGPort`, `capability_ref:string`. For Dynamics it also carries `model_interval_ref:OpaqueRef`; no mutable StateStore, writable event queue, wall-clock simulation time or module-global RNG. `ClockRef` resolves **only** within Harness to a read-only clock projection; `BoundaryRef`, `ViewToken`, `ModelIntervalRef` are **distinct opaque identifiers** and MUST NOT be substituted for one another. The Harness may expose numeric `sim_time_ns:uint64` as a read-only view field after time contract co-sign.

### 8.3 Minimal typed OperationV1 union, validation and fact mapping

| Variant | Required fields and types | Canonical mapping / atomic effect | Owner, invalid behavior |
|---|---|---|---|
| `task.assign_chain.v1` | `operation_id:string`, `actor_vehicle_id:EntityId`, `ordered_task_ids:EntityId[]`, `expected_actor_state_version:uint64`, `expected_task_state_versions:uint64[]` | CONTRACT-02 `AssignTaskChain`: reserve task assignment and vehicle task references **within same transaction**; does **not** assert pickup or onboard cargo custody | ARCH-01 validates entity/task lifecycle and exclusivity; duplicate/overweight → INVALID_ACTION or RESOURCE_VIOLATION, no partial task |
| `dynamics.motion_energy.v1` | `operation_id`, `vehicle_id:EntityId`, `expected_vehicle_state_version:uint64`, `new_position:PointWithCoordinateRef`, `energy_consumed_wh:finite float64 ≥0`, `resulting_motion_status:string`, `model_ref:string`, `quality_flags:string[]` | CONTRACT-02 `MotionEnergyChange`: **single atomic** position+mode+one Harness-computed battery debit of exactly `energy_consumed_wh`; no direct provider battery mutation | ARCH-01 energy/CRS validator; negative/nonfinite → NONFINITE_VALUE/STATE_INVARIANT_FAILED, no partial motion |
| `domain.service_fact.v1` | `fact_id:string`, `subject_entity_id:EntityId`, `service_ref:typed Ref`, `evidence_ref:string`, `fact_time_ns:uint64`, `origin_proposal_id:string`, `ordinal:uint64` | From CONTRACT-02 `ServiceFactCandidate` in `service_facts[]`; Harness sets time to validated model interval `end_ns`, derives deterministic `fact_id` from (run,generation,boundary,proposal,ordinal,kind), **then** domain lifecycle validator stages required custody/task/lease transitions as a single fact-associated atomic group. **Not an EventEnvelope** | ARCH-01 owns service completion predicates; proximity-only or missing evidence → SERVICE_FACT_INVALID, no delivery |
| `domain.event_effect.v1` | `operation_id`, `origin_event_id:string`, `target_ref:Ref?`, `effect_kind:namespaced string`, `typed_payload:object`, `preconditions:typed[]` | Normalized domain event-handler patch derived from already admitted EventEnvelope, not provider's direct StateStore write | ARCH-01/02 phase and domain validation; EVENT_PRECONDITION_FAILED; per-event policy applies |
| Unknown variant | any | **Never** accept generic field assignment as escape hatch; new operation variant requires version/manifest registration | CONTRACT_VERSION_MISMATCH / INVALID_ACTION |

Each normalized operation additionally carries `based_on_state_version:uint64?`, `unit_ref:string?`, `provenance_ref:string`, `effect_time_ns:uint64`; `effect_time_ns` is Harness-resolved for the phase (model facts use interval end). Versioned semantic reducers (e.g. lease grant) are ARCH-01-owned and must be allowlisted at assembly. Unknown reducer and cross-proposal conflicting writes reject the **entire** strict boundary; no last-write-wins. If a *single event* has a frozen `record_and_skip` policy and its operations fail, all that event's staged operations are discarded, its failure disposition is durably registered **only upon** an otherwise successful boundary commit. A malformed Scheduler or Dynamics proposal has **no event skip policy**.

**Ordering of validation**: recognized type/major → run/generation/boundary → minted view_token + invocation phase → component capability → unique proposal/operation IDs + source digest → typed ref and expected state versions → units/CRS/finite numbers → task/cargo/lease invariant → event schedule validity → cross-ChangeSet conflict + registered reducer → B/C/D preparation → one publish. Every rejection returns a typed diagnostic; never silently coerce incompatible units, missing indices or versions.

### 8.4 Normative candidate failure envelope, aliases and outcome semantics

One structured `ContractFailureV1` returned by Harness for all three ingress paths:

| Field | Type / meaning | Owner |
|---|---|---|
| `schema_version` | string = `contract-failure.v1` | ARCH-02 |
| `code`, `source_code?` | canonical string enum; original component-specific code preserved when mapped | ARCH-02 maps, ARCH-03/01 supply source |
| `disposition` | `REJECT_REQUEST` / `SKIP_EVENT` / `ROLLBACK_BOUNDARY` / `POSTCOMMIT_PARTIAL` / `REJECT_ASSEMBLY` / `TAINT_LEGACY` | ARCH-02 |
| `severity`, `retryable` | enum INFO/WARN/ERROR/FATAL, bool; retryable true only if policy+full rewind proven | ARCH-02 |
| `run_id`, `generation`, `boundary_id?`, `phase?` | stable id, uint64, optional stable id/PhaseV1 | Harness |
| `committed_revision`, `attempted_revision?` | uint64 last published revision; any attempted revision is not externally visible | Harness |
| `proposal_id?`, `event_id?`, `component_id?`, `field_path?` | IDs/JSON path or null | Harness |
| `policy_ref?`, `diagnostic_ref?`, `cause_chain?` | frozen policy version, trace ref, sanitized cause array | Harness + evidence subsystem |
| `world_commit_occurred`, `evidence_status` | bool; `COMPLETE/PARTIAL/INCOMPLETE/NOT_ASSESSED` | Harness/CONTRACT-04 |

**Canonical error groups and explicit alias mapping** (retain `source_code`, never mask root cause): `STALE_OBSERVATION` ← stale token / `STALE_COMMAND` from a versioned Proposal; `ENTITY_REFERENCE_INVALID` ← `UNKNOWN_REFERENCE` / `TARGET_NOT_FOUND` only for typed ref errors; `RESOURCE_VIOLATION` ← capacity/lease conflicts, with original `RESOURCE_CAPACITY_EXCEEDED` / `CONFLICTING_LEASE` in `source_code`; `NONFINITE_VALUE` ← non-finite numeric proposal; `COMPONENT_RECOVERY_UNSUPPORTED` ← `CHECKPOINT_UNAVAILABLE` or unproven private D; `CONTRACT_VERSION_MISMATCH` ← unsupported major/operation variant. **Do not alias** distinct `TIME_PRECISION_LOSS`, `EVENT_ID_CONFLICT`, `INVALID_EVENT_ORDER`, `EVENT_CYCLE`, `EVENT_PRECONDITION_FAILED`, `STATE_CONFLICT`, `STATE_INVARIANT_FAILED`, `CUSTODY_CONFLICT`, `SERVICE_FACT_INVALID`, `COMPONENT_EXCEPTION`, `OUTPUT_FAILURE`; their causes and remediation differ.

| Failure window | Default disposition | State and control effect | Client/observer rule |
|---|---|---|---|
| Invalid external command **before** boundary admission | REJECT_REQUEST | no boundary staged; committed B/C/D unchanged | diagnostic only, no revision |
| Unsupported protocol / D rollback capability during assembly | REJECT_ASSEMBLY | no READY/rev0 | fail closed |
| Scheduler / Dynamics malformed proposal or model exception **after** boundary starts | ROLLBACK_BOUNDARY | discard entire B/C/D/queue/RNG/sequence stage; committed revision/time/index unchanged; default Run FAILED | no fake successful empty proposal |
| Event handler with explicit frozen `record_and_skip` on recoverable domain precondition | SKIP_EVENT | discard only this event's local effects; append rejected disposition and dequeue event as part of **one successful** boundary commit; failure to complete remainder rolls everything back | no ghost event effects |
| Event malformed schema, order violation, cycle, fatal policy | ROLLBACK_BOUNDARY (or REJECT_REQUEST before admission) | fully rewind staged cursor and effects | reason and event ID recorded |
| Postcommit MetricProvider / artifact export error | POSTCOMMIT_PARTIAL | committed B/C/D retained; **never re-run physics**; metric/evidence marked PARTIAL/INCOMPLETE | CommittedFrame remains visible |
| Legacy opaque partial write then exception | TAINT_LEGACY | no honest rollback guarantee | TAINTED/FAILED, isolated worker destroy/reset only |

These errors are **logical contract outcomes**; the current repository contains no implementation of the proposed failure envelope. `POSTCOMMIT_PARTIAL` says *world committed*, **not** that durable artifacts were atomically written. Durable audit failures/required evidence stop policy require CONTRACT-04 agreement.

### 8.5 Concurrency, source-lifetime and co-sign gate

Two accepted ChangeSets based on distinct provisional `view_token` stages may share the same `base_revision` inside one boundary but may **not** write inconsistent fields; cross-proposal conflict checked against current stage. Only the last minted, authorized token for that slot is accepted. `producer_seq` for EventEnvelope is **not** `stage_seq`; one is run-scoped deterministic event-admission order, the other private intra-boundary view identity.

**Sign-off requested, not yet obtained**: ARCH-02 owner transaction+failure envelope; ARCH-01 co-sign typed domain reducers/custody/service fact; ARCH-03 / AI-B co-sign normalization and component output aliases; AI-C co-sign RNG rollback and sequence allocation; CONTRACT-04 co-sign commit evidence/CommittedFrame; ARCH-04 legacy exclusion; coordinator ADR-002. No contributor review can retroactively substitute for these explicit signatures, and this doc must remain `PROPOSED` until recorded.


---

## 9. PR #61 cross-team directed normative candidate (P0-01/P0-02; 2026-10-16)

> **Coordinator directive applied for reconciliation, not ACCEPTED ADR.** Source #61 `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc`, [ARCH_06_INTERFACE_REGISTRY_CANDIDATES.md](https://github.com/159357yangjun/SwarmBalance/blob/6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc/docs/platform/architecture/decisions/ARCH_06_INTERFACE_REGISTRY_CANDIDATES.md) and ARCH_06_FREEZE_RULING; AI-B #55 `eca750b9b1c3fb25e6f6fd29732c4316d694e6f5` (TRANSACTION_EVENT_PROPOSAL_CONVERGENCE). This §9 is the authoritative **joint pack `state-event-proposal.v1-candidate-2` candidate within #58**, matching #55 §0, if older §§3 or 8 use different public header/alias names; previous pack `state-event-proposal.v1-candidate-1` is historical and is NOT a second active ABI. Neither #55 nor original ARCH-01–04 is edited by this PR. Version IDs: public header `proposal-header.v1-candidate`, public messages `action-proposal.v1` / `state-delta-proposal.v1`, Harness internal wire tag `normalized-changeset.v1` (registry candidate `normalized-changeset.v1-candidate`), boundary protocol `boundary-commit.v1-candidate`; no second public ChangeSet.

### 9.1 One public ProposalHeaderV1, single internal normalization target

```python
# Logical, non-executable proposal schema (not a released ABI).
class ProposalHeaderV1:
    schema_version: str      # proposal-header.v1-candidate; major 1, frozen by future sign-off
    proposal_id: str         # stable identity, digest-based idempotency within run generation
    run_id: str              # current RunScope
    generation: int          # uint64
    boundary_id: str         # PUBLIC, Harness-issued, run-local; not opaque boundary_ref
    base_revision: int       # uint64, committed revision on entry (not stage_seq)
    read_view_token: str     # opaque stage-scoped capability, Harness-issued
    producer_id: str         # manifest-bound component identity
    capability_ref: str      # versioned authorized capability
    provenance_ref: str      # immutable source/model/assembly manifest digest reference

class ActionProposalV1:
    schema_version: str       # action-proposal.v1 (message schema, distinct from header)
    header: ProposalHeaderV1
    actions: tuple            # typed AssignTaskChain, not direct world operations
    emitted_event_intents: tuple  # default empty, only if capability allows

class StateDeltaProposalV1:
    schema_version: str       # state-delta-proposal.v1
    header: ProposalHeaderV1
    model_interval_ref: str   # opaque *Dynamics* integration capability, NOT event window
    changes: tuple           # typed MotionEnergyChange
    service_facts: tuple     # typed DomainFactCandidate, NOT queued EventEnvelope
    emitted_event_intents: tuple  # future timed work; authorized only

class NormalizedChangeSetV1:
    schema_version: str      # normalized-changeset.v1; Harness internal only
    proposal_id: str         # validated ProposalHeaderV1 projection
    producer_id: str
    run_id: str
    generation: int          # uint64
    boundary_id: str
    base_revision: int       # uint64
    read_view_token: str     # minted stage token
    phase: str               # PhaseV1 assigned by Harness from invocation slot
    operations: tuple        # typed ARCH-01-registered OperationV1 reducers
    capability_ref: str
    source_digest: str       # source proposal bytes + converter version
    model_interval_ref: str | None  # only Dynamics, otherwise None
    emitted_event_intents: tuple

# NormalizedChangeSetV1 is Harness-INTERNAL ONLY.
# No public ChangeSetV1 or change-set.v1 as a competing executable ABI.
```

**Header is one object**, not ten ad hoc duplicate public top-level fields: producer outputs `ActionProposalV1.header` or `StateDeltaProposalV1.header`; the Harness internal `NormalizedChangeSetV1` **projects the validated header into explicit scalar fields**, with source_digest, phase, operations and optional model_interval_ref; it does not expose an alternate public header or a nested competing wire format. Legacy `boundary_ref`, `observed_revision`/`base_committed_revision`, `observed_view_token`/`based_on_view_token`, `source_component_id` may be accepted **only** in a separately versioned ingress adapter with an explicit one-to-one mapping into the common header; strict `proposal-header.v1-candidate` rejects mixed/duplicate or contradictory aliases. `boundary_id` is a Harness-issued *public explicit* identifier, while `read_view_token` remains opaque and stage-specific; they are **different concepts**. A mutable or stale token is rejected even when boundary_id/base_revision match.

| Input | Canonical mapping to internal NormalizedChangeSetV1 | Authority and hard failure |
|---|---|---|
| Scheduler `propose(ObservationV1, ProposalContext)` -> ActionProposalV1 | exact header field-by-field internal projection; `actions` -> typed `task.assign_chain.v1` atomic operations; phase=APPLY_COMMAND | ARCH-03 ABI, ARCH-01 reducer, ARCH-02 converter; DOMAIN_OPERATION_UNMAPPED / STALE_OBSERVATION |
| Dynamics `propose(StateSliceView,Conditions,ModelIntervalRef,ProposalContext)` -> StateDeltaProposalV1 | exact header field-by-field internal projection; `changes` -> typed `dynamics.motion_energy.v1`, `service_facts` -> POST_MODEL DomainFactV1 candidate; phase=ADVANCE_MODEL for motion only | ARCH-03 ABI; model_interval_ref must be current, INTERVAL_MISMATCH; negative/NaN energy rejected |
| Event handler from admitted EventEnvelopeV1 | Harness creates its own scoped validated header and `domain.event_effect.v1` operations for the admitted event; optional future EventIntent separately scheduled | ARCH-01 reducers, ARCH-02 queue and writer; UNAUTHORIZED_EVENT_OPERATION / INVALID_EVENT_ORDER |
| Any proposal containing `change-set.v1` as public ABI, untyped arbitrary field write, or unsupported operation kind | **no conversion**; do not interpret it as another public entrypoint | CONTRACT_VERSION_MISMATCH / DOMAIN_OPERATION_UNMAPPED |
| Any proposal with `boundary_ref` instead of required `header.boundary_id` in strict public profile | **no implicit conversion**; only explicit versioned compatibility converter allowed | BOUNDARY_ID_CONFLICT / CONTRACT_VERSION_MISMATCH |

**Deterministic validation**: header-major/version → RunScope identity/generation → exact Harness-issued boundary_id, committed base_revision, phase-issued view token → producer identity + capability → input/proposal semantic digest and idempotency → typed reducers/refs/units/finite values/state versions → queue time/phase seal → non-conflicting overlay and D checkpoint → one atomic commit. The converter itself is pure (no queue writes/RNG draws/clock advancement), reports its schema/converter version and output digest, and is the **only** route to a normalized stage batch. Proposal ID + identical digest returns prior decision; ID + different digest rejects PROPOSAL_ID_CONFLICT.

### 9.2 Boundary authority, failure and version supersession

- **ADR-002 strict V1 direction supersedes ARCH-01 WORLD_STATE §3's externally visible micro-commits**. This is a new authoritative *candidate direction*, not a retroactive edit to #46: stage_seq/view_token progresses privately, while B(domain), C(clock/queue/event order/RNG) and D(recoverable component state) publish coherently once per successful boundary as `revision=r+1, step_index=s+1`. No partial public phase revision; no `ChangeSet` component directly calling StateCommitter.
- At most one committed revision for an execution boundary; **precommit** fatal validation/exception discards B/C/D, queue/RNG/producer seq and preserves r/time/s; **postcommit** evidence/metrics errors preserve r+1 and emit `ContractFailureV1.disposition=POSTCOMMIT_PARTIAL`; `record_and_skip` is legal only for an explicitly frozen recoverable event, never for a malformed Scheduler/Dynamics proposal.
- Required `ContractFailureV1` has `schema_version,code,source_code?,disposition,severity,retryable,run_id,generation,boundary_id?,committed_revision,attempted_revision?,proposal_id?,event_id?,component_id?,field_path?,policy_ref?,diagnostic_ref?,world_commit_occurred,evidence_status`. Dispositions: REJECT_ASSEMBLY, REJECT_REQUEST, SKIP_EVENT, ROLLBACK_BOUNDARY, POSTCOMMIT_PARTIAL, TAINT_LEGACY. Source codes preserved, no silent aliases. `NO_BOUNDARY` without control transition is not a success commit.
- The PR #61 **COORDINATOR_DIRECTIVE** is binding for this draft's reconciliation choices but not formal `ACCEPTED` / `FROZEN`. This candidate requires real ARCH-01/02/03 and AI-B signatures, independent #59 rereview, and final coordinator gate. All proposed test cases remain NOT_RUN.
