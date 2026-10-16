# CONTRACT-01 — TIME_AND_EVENT_CONTRACT

> **PROPOSED / NOT FROZEN**, task CONTRACT-01, resolves ARCH-05-R2 B03 jointly with STATE_COMMIT_CONTRACT.md. Owners ARCH-02 (clock/queue/order), ARCH-01 (Scenario EventSpec/domain effects), ARCH-03 (EventIntent), ARCH-04 (legacy disclosure); CONTRACT-03 co-sign on RNG-driven producers. Baseline SHA: master 2ab60c69a806a22d7ba20353dee0571752a0e8e5; #54 99bd0eb6b910d691d6d7776da0a5fd3f973f2997; #46 b5f05a70a3306f1799fcae2c3f342f3ed9ee0048; #49 d155621aca66e3a80c388718093a452d17d71e10; #47 68382c649393057ffbf5a14508ab1ff72d575b09; #51 f2df96bc609ee1e430ea6eff2456c4577347c300. All Draft and unchanged relative to #54's recorded #46/#49/#47 heads at inspection.

## 1. Conflict references

- [ARCH-01 SCENARIO_MODEL §2/§5](https://github.com/159357yangjun/SwarmBalance/blob/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world/SCENARIO_MODEL.md): EventSpec time_s float, priority int, kind, target_ref, on_failure, immutable scenario and event ID.
- [ARCH-02 CLOCK_AND_EVENTS §1–§5](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/CLOCK_AND_EVENTS.md): integer nanosecond clock, six phases and deterministic producer order, mid-tick hybrid boundaries.
- [ARCH-03 COMPONENT_CONTRACTS §1/§3](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md): EventIntent at_seconds float, priority_class string, stable_order_key string; no phase or sequence.
- [ARCH-05-R2](https://github.com/159357yangjun/SwarmBalance/blob/99bd0eb6b910d691d6d7776da0a5fd3f973f2997/docs/platform/architecture/review/ARCH_05_R2_INTERFACE_AND_SCENARIO_MATRIX.md): M03–M05 are P0 differences.

**Resolution:** EventSpec is immutable scenario input, EventIntent is untrusted provider proposal, EventEnvelopeV1 is the sole admitted, normalized Run-local queue identity. Neither EventSpec nor EventIntent is directly executed. A domain completion fact is not a queued intent. All conversions are total-or-reject, logged and versioned.

## 2. Clock schema and conversion

| Field | Type / invariant | Owner | Failure |
|---|---|---|---|
| Clock.sim_time_ns | uint64 nanoseconds since Run simulation epoch; authoritative, monotone within generation | Harness | TIME_REGRESSION / TIME_OVERFLOW |
| Clock.sim_time_s | float64 **read-only** projection = sim_time_ns / 1_000_000_000; never used as equality/order key | Harness adapter | no reverse float equality comparisons |
| Clock.step_index | uint64 number of successfully committed strict-mode boundaries since initialization; not a time or a model sample counter | Harness | STEP_CONFLICT |
| WorldState.revision | uint64 committed version, rev=0 at init and +1 per accepted boundary (including zero-duration bounded event work) | Harness | REVISION_CONFLICT |
| Clock.generation | uint64 reset epoch, different identity even if revision and clock reset to zero | Harness | STALE_GENERATION |
| Clock.mode | enum FIXED_STEP / DISCRETE_EVENT / HYBRID, frozen RunSpec | ARCH-02 | CLOCK_SEMANTICS_MISMATCH |
| Clock.step_ns, horizon_ns | uint64 positive fixed tick (when used), uint64 nonnegative horizon; exact durations, frozen | ARCH-02 | INVALID_DURATION / TIME_OVERFLOW |
| Clock.boundary_id | run-unique deterministic string derived from generation and next step ordinal; not a revision | Harness | BOUNDARY_ID_CONFLICT |

**Exact input converter:** external seconds MUST be a finite decimal string or finite numeric input with an explicitly documented round-trip decimal representation. Use decimal arithmetic to multiply by 10^9 and accept **only exact integral nanoseconds** in the uint64 range; no implicit floor, ceiling, binary float multiplication, or bankers rounding. IEEE float source normalized with its shortest round-trip decimal representation; record original type/text, normalized decimal, time_ns and converter version. Thus 3.5 s -> 3_500_000_000 ns; 0.0000000001 s (0.1 ns) -> TIME_PRECISION_LOSS, rather than silently becoming zero. Every provider-facing float projection is informational; scheduling back into queue requires explicit converter and validation. Scenario.time_origin maps calendar times into this Run-relative axis with declared timezone/DST policy; OS time is prohibited.

**Boundary dimensions:** end time may equal start for bounded same-time event work; neither revision nor step_index can be used to infer seconds elapsed. A FIXED_STEP interval cannot skip an exact at=3.5 event; split deterministically or reject assembly (CLOCK_SEMANTICS_MISMATCH). No event after horizon executes. Candidate horizon policy is INCLUDE_ONCE: process pending events exactly at horizon in one legitimate bounded terminal event boundary if needed, **without any redundant empty physics tick**. See §8 for the type, boundary and t=0 policy; not an accepted ADR.

## 3. Event interfaces (all fields, source, errors)

**EventSpecV1 (ARCH-01 frozen scenario input)**

| Field | Type and meaning | Failure |
|---|---|---|
| schema_version | string event-spec.v1 | SCHEMA_MISMATCH |
| event_id | stable globally unique namespaced string within Scenario and Run mapping | EVENT_ID_CONFLICT |
| time_s | finite input decimal/numeric seconds converted exactly to time_ns | TIME_PRECISION_LOSS |
| priority | signed int32, smaller executes first | INVALID_PRIORITY |
| kind | registered namespaced string, e.g. environment.wind.update | UNKNOWN_EVENT_TYPE |
| target_ref | typed Entity/Field ref or null only when kind allows | TARGET_NOT_FOUND |
| payload | schema-validated immutable JSON-compatible value with explicit units | INPUT_SCHEMA_INVALID |
| preconditions | typed expected world revision/entity versions/field rules | EVENT_PRECONDITION_FAILED |
| on_failure | enum abort_run / record_and_skip / retry_with_limit | INVALID_FAILURE_POLICY |
| provenance | immutable scenario/dataset digest, source locator, converter version | PROVENANCE_MISSING |

**EventIntentV1 (ARCH-03 EventProvider output)**

| Field | Type and meaning | Failure |
|---|---|---|
| schema_version, event_id | string event-intent.v1, deterministic stable string | SCHEMA_MISMATCH / EVENT_ID_CONFLICT |
| at_seconds | finite seconds, exactly representable at ns precision | TIME_PRECISION_LOSS |
| phase | PhaseV1 enum; required new field replacing implicit phase | INVALID_PHASE |
| priority | signed int32; replaces ambiguous priority_class string | INVALID_PRIORITY_CLASS |
| producer_id, producer_seq | stable component ID, uint64 per-producer monotonic sequence assigned before enqueue, persisted in queue/control | INVALID_PRODUCER_SEQUENCE |
| kind, target_ref, payload, preconditions | namespaced kind, typed ref, schema-checked immutable value, typed predicates | INPUT_SCHEMA_INVALID |
| failure_policy | scenario-frozen failure enum and (for retry) max_attempts:uint32 positive, backoff_ns:uint64 positive | INVALID_FAILURE_POLICY |
| causal_parent_id | optional string parent event/fact/command identity | CAUSAL_REFERENCE_INVALID |
| provenance | component/version/input digest/converter lineage | PROVENANCE_MISSING |
| stable_order_key | **deprecated compatibility input**, string for origin audit only, NEVER substitutes for producer_seq or canonical order | AMBIGUOUS_ORDER if no valid producer_seq |

**EventEnvelopeV1 (ARCH-02 sole executable queue object)**

| Field | Type and meaning | Failure |
|---|---|---|
| schema_version | string event-envelope.v1 | SCHEMA_MISMATCH |
| event_id, run_id, generation | stable string, string, uint64 | EVENT_ID_CONFLICT / STALE_GENERATION |
| time_ns, phase | uint64 exact timestamp, PhaseV1 enum | TIME_REGRESSION / INVALID_PHASE |
| priority, producer_id, producer_seq | int32, stable string, uint64; total-order inputs; seq reserved transactionally at admission | INVALID_PRIORITY / INVALID_PRODUCER_SEQUENCE |
| kind, target_ref, payload | namespaced kind, optional typed ref, schema-validated immutable payload | UNKNOWN_EVENT_TYPE / INPUT_SCHEMA_INVALID |
| preconditions, failure_policy | typed predicates, frozen policy including bounded retry | EVENT_PRECONDITION_FAILED |
| causal_parent_id, provenance | optional stable ref, mandatory immutable lineage | CAUSAL_REFERENCE_INVALID / PROVENANCE_MISSING |
| payload_digest | sha256 canonical entire semantic spec excluding non-semantic trace metadata | EVENT_ID_CONFLICT |
| attempt | uint32 starting zero; bounded policy continuation may assign new attempt without changing original event identity | EVENT_RETRY_EXHAUSTED |

The EventEnvelope includes all fields needed to reproduce an outcome; per-producer sequence must be assigned by a deterministically ordered Harness admission pipeline or issued through its transactional allocator. Provider-supplied sequence is a *claim* to validate, not an authority allowing collision. Scenario EventSpec conversion uses producer_id = deterministic scenario-source manifest identity, producer_seq = declared immutable ordinal in the scenario's canonical scheduled_events ordering; never unordered dictionary iteration. External UI injection receives a stable command_id and a sequence assigned during serialized admission before the phase seal; identical retried command_id and digest receives the same identity. Different content under same ID hard rejects.

## 4. Deterministic event total order and phase semantics

**Canonical queue key:**
`(time_ns ASC, phase_rank ASC, priority ASC, producer_id UTF-8 bytewise ASC, producer_seq ASC, event_id UTF-8 bytewise ASC)`.

| PhaseV1 rank | Meaning and permissible work | Reader |
|---|---|---|
| 0 PRE_INPUT | weather/fault/airspace/exogenous changes effective at boundary start | Event handler staging |
| 1 PRE_DECISION | arrivals/validations; preregistered work due before scheduler | Scheduler afterward |
| 2 APPLY_COMMAND | proposal validation and assignment/resource operations | Dynamics afterward |
| 3 ADVANCE_MODEL | integrate only explicit [start_ns,end_ns] interval, stage position/energy and physical facts | Post-model handlers |
| 4 POST_MODEL | consume service-completion facts, custody/lease lifecycle updates; queue events *only if future effective barrier* | Metric after commit |
| 5 OBSERVE | postcommit observation/trace ONLY; not a queue-delivered world-mutating event phase | Metrics/clients |

**Important separation**: ranks 0–5 are logical phase order **within one boundary**. A boundary that integrates t→u has PRE_INPUT/PRE_DECISION at t and advances to u; a completion at u is staged as an end-boundary POST_MODEL **fact** (not a due EventEnvelope at u whose rank should precede PRE_INPUT). At the next boundary starting u, admitted PRE_INPUT(u) is processed first, then scheduler reads the state including committed completion at u. This deliberately splits end-of-interval facts from queued events, preventing a global key claiming an impossible chronological ordering. Audit trace records fact_time_ns=u and producing boundary_id. A separately scheduled external PRE_INPUT(u) is processed in the next boundary at u (possibly zero duration), never retroactively changes the preceding dynamics integral. If a model needs a wind/failure at u **before** integrating beyond u, HYBRID must split there.

**Within the same timestamp and phase**, priority wins, then canonical producer_id, then per-producer seq, then event_id. IDs are not identity of phase or position. Duplicate event_id + matching digest is idempotently reused, not executed twice; differing digest rejects EVENT_ID_CONFLICT. New same-time work targeting an already sealed/lower phase rejects INVALID_EVENT_ORDER (or must be explicitly scheduled for a future valid boundary); NO silent reordering. A configurable positive max_same_time_events/max_cascade_depth in FrozenRunSpec aborts a cycle with EVENT_CYCLE and rolls back all uncommitted stages. EventProvider polling window boundary inclusivity (recommended (start,end] for generated external events, separate initial t=0 queue) must be frozen by ARCH-02/03; no double-window ingestion.

## 5. Conversion pipeline, policy and failure

`Scenario EventSpec --validate frozen source/decimal time/phase mapping--> EventIntent-equivalent normalized record --Harness admission--> EventEnvelope`.
`EventProvider EventIntent --validate capability/source order/time/phase/schema--> EventEnvelope`.
Only Harness creates the run_id/generation and canonical queue entry. Scenario events with no phase use a **versioned event-kind→phase mapping**, not arbitrary default; unknown mapping must fail assembly. Existing EventSpec priority is copied exactly as int32 after range validation. Existing EventIntent priority_class needs a manifest-pinned conversion table to numeric priority; missing/ambiguous mapping fails; do not lexicographically sort strings. Existing stable_order_key may be retained for provenance but not as ordering input. Converters must record source schema/version, input digest, mapping version and output digest.

1. Validate identity, units, time representation, phase/kind/priority mapping and source contract.
2. Check event_id duplication versus admitted-event ledger and producer_seq monotonic uniqueness, time >= current admission seal; reject past, expired, or already sealed earlier-phase events.
3. Reserve deterministic producer_seq/event identity and staged queue/RNG cursors as transaction B/C. Same boundary hard failure restores all reservations.
4. On execution validate preconditions on the latest provisional view, not an obsolete committed frame. The event handler proposes declarative operations; it never mutates B directly.
5. abort_run: invalidate whole uncommitted boundary, preserve last committed revision, mark Run FAILED. record_and_skip: stage *rejected disposition* and consume the event only at a successful boundary commit, no partial domain operations. retry_with_limit: only for predeclared deterministic and rollback-safe cases, schedule an exact later valid time and record attempt; max and backoff must be frozen. Zero-backoff retries disallowed in V1.
6. Events created after commit or by an observer do not retroactively enter a closed boundary. Observer failures keep committed state, mark incomplete evidence.

**Illustrative fixtures (design only):**
- Spec `{event_id:"wind:1",time_s:"3.5",priority:10,kind:"environment.wind.update",target_ref:"field:wind",payload:{u_ms:6,v_ms:0},on_failure:"abort_run"}` with kind map PRE_INPUT and source `scenario:s1` ordinal 0 -> envelope `time_ns=3500000000,phase=PRE_INPUT,priority=10,producer_id="scenario:s1",producer_seq=0`. At 3.5 s HYBRID barrier, next scheduler sees wind=6 m/s.
- Two independent fault and demand events at 4.0 s: PRE_INPUT fault applied before PRE_DECISION arrival; if same phase, priority and source sequence determine order; no scheduler dispatch to a closed facility.
- Input `time_s="3.0000000001"` rejects TIME_PRECISION_LOSS; `priority_class="urgent"` with no mapping rejects INVALID_PRIORITY_CLASS.
- Same ID, different payload rejects EVENT_ID_CONFLICT; event emitted in POST_MODEL trying PRE_INPUT for already sealed same timestamp rejects INVALID_EVENT_ORDER.
- Same timestamp cyclic self-scheduling exceeds bounded budget -> EVENT_CYCLE, no half-applied wind or task.

## 6. Responsibilities, signatures and unresolved matters

| Issue | Owner and mandatory co-sign | Status |
|---|---|---|
| nanosecond converter/range/clock strategy, event total ordering, phase admission and end-boundary fact split | ARCH-02; ARCH-01/03 | PROPOSED |
| scenario EventSpec version, kind→phase registry, time-origin policy, immutable event identity | ARCH-01; ARCH-02/03 | PROPOSED |
| EventIntent field additions and manifest priority_class mapping; component sequence/checkpoint support | ARCH-03; ARCH-02; CONTRACT-02 | PROPOSED |
| RNG stream and stochastic event stable producer sequence | CONTRACT-03 owner; ARCH-02/03 | NOT RESOLVED here |
| legacy old Environment.step ordering and manual injection equivalence | ARCH-04; ARCH-02 | LEGACY_OPAQUE_STEP, non-equivalent |
| postcommit CommittedFrame/event-fact provenance and durable trace failure handling | CONTRACT-04; ARCH-02/03 | OPEN |
| Proposed fixed candidate for late same-time REJECT, horizon INCLUDE_ONCE, t=0 predecision admission and versioned kind→phase map | Coordinator ADR-002/003 with ARCH-01/02/03 signatures | **DIRECTION CHOSEN for #58; FORMAL SIGNATURES PENDING** |

**Required future review:** Re-open B01/B03 if any of the exact PR HEADs above change; read changed blobs and revise the matrix. Do not report these fixtures as executed runtime tests. No physical/model validation performed.


---

## 7. Unified event/Proposal schema join (AI-A → AI-B handshake, 2026-10-16)

> Companion to STATE_COMMIT_CONTRACT.md §8; candidate pack `state-event-proposal.v1-candidate-1` (**PROPOSED, not registered as ACCEPTED ABI**). Cross-checked against #55 `PROPOSAL_AND_OBSERVATION_SCHEMA.md` at `b00cd337de2797b9819089b234a113e36513e003`, #56 `RNG_STREAM_OWNERSHIP.md` at `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`, #57 `RUN_AND_METRIC_CONTRACT.md` at `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`, #60 `IMPLEMENTATION_DEPENDENCY_PLAN.md` at `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`. This is a joint **proposal for review**, not evidence that peers signed.

### 7.1 Envelope, typed EventIntentBatch and responsibility

`EventIntentBatchV1` (ARCH-03 component public return): `schema_version:"event-intent-batch.v1"`, `run_id:string`, `generation:uint64`, `boundary_id:string`, `read_view_token:OpaqueRef`, `producer_id:string`, `window_ref:EventWindowRefV1`, `intents:EventIntentV1[]`, `source_manifest_digest:string`. An **empty `intents:[]` is a valid, explicitly empty batch**, distinct from provider failure (typed ContractFailureV1). Harness validates authorization, source ordering, window endpoints and replay source digest before admitting *any* intents. A hard-invalid batch is fully rejected, never prefix-enqueued.

| Normalized field | Scenario EventSpec source | EventProvider EventIntent source | Harness EventEnvelope destination, ownership / rejection |
|---|---|---|---|
| `schema_version` | `event-spec.v1` (legacy v0.1 explicit converter) | `event-intent.v1` | `event-envelope.v1`; unsupported major CONTRACT_VERSION_MISMATCH |
| `event_id:string` | immutable EventSpec ID | intent ID | carry verbatim run-mapped identity, no re-numbering; EVENT_ID_CONFLICT on equal ID different canonical payload |
| `run_id:string,generation:uint64` | absent (Scenario is run-independent) | from minted ProposalContext/Batch, never arbitrary payload | **Harness injects/validates** current RunScope; STALE_GENERATION |
| `time_ns:uint64` | `time_s` exact decimal ns conversion | `at_seconds` exact decimal ns conversion | **Harness authoritative** uint64; TIME_PRECISION_LOSS, TIME_REGRESSION or TIME_OVERFLOW |
| `phase:PhaseV1` | versioned kind→phase map from frozen ScenarioManifest | `phase` declared by provider, cross-checked with capability and kind map | admission ranks immutable; UNKNOWN_PHASE_MAPPING / PHASE_CAPABILITY_MISMATCH |
| `priority:int32` | `priority:int`, range checked | numeric `priority:int32`, or legacy `priority_class` with frozen map | copied integer; no implicit class lexicography; INVALID_PRIORITY_CLASS |
| `producer_id:string` | pinned Scenario event-source ID + version | component descriptor ID must match batch/ctx identity | manifest-stable UTF-8 identity, cannot be OS/thread/Python-hash derived; INVALID_PRODUCER_ID |
| `producer_seq:uint64` | event's zero-based position in **frozen canonical Scenario event list** per producer | transactional per-producer sequence issued by Harness (or checked reservation token in ctx) | Harness verifies strict monotonicity/collision and commits cursor **only with boundary**; INVALID_PRODUCER_SEQUENCE |
| `kind:string,target_ref:Ref?` | kind and target_ref | kind and target_ref | versioned domain event registry/ref validator; UNKNOWN_EVENT_TYPE / ENTITY_REFERENCE_INVALID |
| `payload:TypedJSON,preconditions:Predicate[]` | typed payload/constraints | typed payload/constraints | immutable canonical bytes, validation on latest provisional view; INPUT_SCHEMA_INVALID / EVENT_PRECONDITION_FAILED |
| `failure_policy:FailurePolicyV1` | `on_failure` mapped exactly with frozen retry budget | requested policy must be authorized by FrozenRunSpec for this source/kind | Harness resolves abort/skip/bounded retry; INVALID_FAILURE_POLICY |
| `causal_parent_id:string?` | explicit only if source supports | optional causal parent | pin stable parent, no dangling references; CAUSAL_REFERENCE_INVALID |
| `provenance:ProvenanceRef` | scenario/source digest & ordinal | component/manifest/input digest and window ref | required converter/version/input digest; PROVENANCE_MISSING |
| `payload_digest:Digest,attempt:uint32` | derived, no EventSpec authority | derived, no EventProvider authority | computed by Harness canonical serialization; attempt starts 0; EVENT_ID_CONFLICT / EVENT_RETRY_EXHAUSTED |

**Input precedence:** the EventSpec `time_s` and EventIntent `at_seconds` are *input adapters*, never alternative clock owners. `stable_order_key:string` (ARCH-03 old proposal) remains audit-only; absent producer_seq reservation is a hard refusal. The event envelope's `priority` and `phase` never accept unregistered alias strings. Where a v0 EventSpec lacks `phase`, a versioned `event_kind_phase_map` digest frozen in RunSpec provides it; unknown kind has no default. No provider is allowed to create `CommittedFrame`, `DomainFactV1`, or WorldState writes through its event payload.

**Canonical serialization**: explicitly named `canonicalization_version`, UTF-8 normalized string policy, type tags and stable dict key/array order must be fixed before a replay digest may be assessed. This is **not** currently a byte-level ABI or golden vector; ARCH-02/03 and CONTRACT-03 must sign and test canonicalization. An event ID is semantic identity, whereas event payload digest is the integrity check.

### 7.2 Time fields and opaque refs as one joined type family

| Interface | Fields/types | Allowed use | Invalid behavior |
|---|---|---|---|
| `ClockRefV1` | Harness-issued opaque `clock_ref:string` tied to run/generation/boundary | read-only projection `sim_time_ns:uint64`, `sim_time_s:float64`, `step_index:uint64`, `committed_revision:uint64` | cannot parse token to set time; STALE_CLOCK_REF |
| `BoundaryIdV1` | Harness-issued public `boundary_id:string`, run/generation scoped | explicit ProposalHeaderV1 boundary identity; no second public opaque boundary_ref | BOUNDARY_ID_CONFLICT across boundaries/generation |
| `ViewTokenV1` | Harness-issued opaque `view_token:string` scoped to component+phase+stage_seq and committed_revision | matches `ObservationV1.view_token` and normalized `ChangeSet.read_view_token` | STALE_OBSERVATION even when committed revision same |
| `ModelIntervalRefV1` | Harness-issued opaque `model_interval_ref:string` mapping internally to `start_ns:uint64,end_ns:uint64,dt_ns:uint64` | verified `duration_seconds:float64` projection; Dynamics never picks interval | INTERVAL_MISMATCH / INVALID_DURATION |
| `EventWindowRefV1` | Harness-issued immutable typed object `{run_id:string,generation:uint64,boundary_id:string,window_token:opaque string,start_ns:uint64,end_ns:uint64,include_start:bool,include_end:bool}` and internal window_seq | **only** EventProvider `EventIntentBatchV1.window_ref`; never Dynamics interval | WINDOW_REF_TYPE_MISMATCH / OUT_OF_EVENT_WINDOW; no silent delayed ingestion |

**Disallow semantic aliasing**: `boundary_id` (public string) ≠ `read_view_token` (opaque stage capability) ≠ `clock_ref` (opaque clock read) ≠ `model_interval_ref` (Dynamics-only) ≠ `window_ref` (EventWindowRefV1) conceptually. Only token-valued fields are opaque; public boundary_id and EventWindowRefV1 typed metadata are explicit immutable values. Type roles are not interchangeable even if string fields or time endpoints happen to match. A reset generates new tokens. To prevent a stale predecision token reaching Dynamics, Harness must mint a new stage-specific token after action staging without incrementing committed revision. Error codes and scope fence from STATE_COMMIT_CONTRACT.md §8 apply.

### 7.3 Admission order, phase seal, and model-end facts

1. Freeze per-run `EventAdmissionPolicyV1`: `kind_phase_map_digest:Digest`, `priority_class_map_digest?:Digest`, `window_inclusion:enum`, `same_time_late_policy:REJECT` (V1 candidate), `horizon_policy:enum`, `initial_t0_policy:enum`, `max_same_time_events:uint32>0`, `max_cascade_depth:uint32>0`, `retry_backoff_policy:explicit version`. Missing required policy means **REJECT_ASSEMBLY**, not defaults invented by producers.
2. Scenario EventSpec is canonicalized in frozen Scenario ordinal order. EventProvider EventIntentBatch is admitted serially by Harness **before** phase seal, using versioned producer order from component dependency DAG. Each accepted event claims unique (run,generation,event_id) and (producer_id,producer_seq); seq reservation advances transactionally and is restored on precommit rollback.
3. For queued envelopes at the same `time_ns`, use **only** `(time_ns, phase_rank, priority, producer_id, producer_seq, event_id)`, all ascending; event_id and producer_id compare as canonical UTF-8 bytes. The ordering cannot depend on worker completion, hash-map iteration or UI polls.
4. A provider may schedule into permitted PRE_INPUT/PRE_DECISION at an **unsealed** boundary. Neither `OBSERVE` nor raw `ADVANCE_MODEL` is a provider-executable domain mutation phase; attempts without declared capability fail PHASE_CAPABILITY_MISMATCH.
5. A validated Dynamics `ServiceFactCandidate` is converted by Harness to `DomainFactV1` with `fact_time_ns=model_interval.end_ns`; its domain lifecycle changes are resolved during the preceding boundary's POST_MODEL stage, **not queued** as `EventEnvelopeV1`. An exogenous PRE_INPUT at the same endpoint is processed at the next boundary beginning there; no impossible global ordering of finished physical facts and not-yet-admitted envelopes is claimed.
6. A genuine follow-up *future* event from a fact handler must be an explicitly authorized EventIntent with `at_seconds` > current sealed time or the next allowed boundary policy. Silent re-entry into a lower already sealed phase → INVALID_EVENT_ORDER. Same-time cascades are bounded and recorded.
7. **Candidate freeze choice (needs coordinator approval):** initial t=0 Scenario PRE_INPUT enters the first admitted boundary before Scheduler; event exactly at horizon may be disposed according to an explicit `horizon_policy=INCLUDE_ONCE|EXCLUDE`; there is never an infinite extra zero-duration step. EventProvider default window suggestion `(start_ns,end_ns]` with a separately defined initial t=0 admission avoids boundary duplicates; otherwise assembly must carry a different named inclusion policy. All such choices are **open ADR-002 parameters**, not silently frozen by this amendment.

### 7.4 Unified event failure and conversion failure semantics

| Failure | Normalized code | Disposition and atomic effect |
|---|---|---|
| Invalid EventSpec at assembly (kind map absent, time unrepresentable, no provenance) | UNKNOWN_PHASE_MAPPING / TIME_PRECISION_LOSS / INPUT_SCHEMA_INVALID | REJECT_ASSEMBLY; no revision 0 published |
| Invalid external EventIntentBatch before admission (wrong ctx, wrong window, missing priority map) | STALE_OBSERVATION / OUT_OF_EVENT_WINDOW / INVALID_PRIORITY_CLASS | REJECT_REQUEST; queue/counters unchanged |
| Same event ID same digest admitted again | idempotent recorded disposition, **not a new action** | No second domain effect; return original record |
| Same ID different semantic digest, or sequence collision | EVENT_ID_CONFLICT / INVALID_PRODUCER_SEQUENCE | REJECT_REQUEST if no boundary stage; else ROLLBACK_BOUNDARY by hard error |
| Event precondition fails and policy=`record_and_skip` | EVENT_PRECONDITION_FAILED with disposition SKIP_EVENT | all **this** event's tentative effects discarded; record skipped disposition and dequeue atomically on successful full boundary, not externally early |
| Event failure and policy=`abort_run` | original cause + ROLLBACK_BOUNDARY | restore all uncommitted B/C/D/queue/RNG/seq; Run FAILED by default |
| Event `retry_with_limit` but missing budget/positive backoff or non-rewindable D | INVALID_FAILURE_POLICY / COMPONENT_RECOVERY_UNSUPPORTED | REJECT_ASSEMBLY or hard rollback; never spin at zero time |
| Late lower phase or same-time cascade over budget | INVALID_EVENT_ORDER / EVENT_CYCLE | hard rollback of all uncommitted work, no phantom event |
| MetricProvider postcommit failure | OUTPUT_FAILURE + POSTCOMMIT_PARTIAL | keep published WorldState/CommittedFrame, mark evidence status; do not re-emit events |

Every failure uses `ContractFailureV1` with original `source_code`, `disposition`, `world_commit_occurred`, `committed_revision`, causal IDs and sanitized trace. **EventIntent is an input object; accepted EventEnvelope is a queue/control record; DomainFact is a committed domain outcome.** None may substitute for another merely because they share `event_id` or `time_ns`.

### 7.5 Joint sign-off checklist (all initially PENDING)

| Group | Must explicitly accept or request changes | Current |
|---|---|---|
| AI-B / ARCH-03 (#55) | EventIntentBatch and ProposalContext aliases, Action/StateDelta→ChangeSet/fact mapping | PENDING |
| ARCH-02 Harness (#49) | EventEnvelope, queue/producer sequence ownership, admission policy, atomic fence and failure mapping | PENDING |
| ARCH-01 World (#46) | EventSpec phase-kind map, typed event effects, DomainFact lifecycle invariants | PENDING |
| AI-C CONTRACT-03 (#56) | RNG cursor/producer_seq on rollback; deterministic external source tape IDs | PENDING |
| AI-D CONTRACT-04 (#57) | CommittedFrame/evidence partial and fact log digest, no postcommit rewind | PENDING |
| ARCH-04 (#50) | explicit LEGACY_OPAQUE_STEP segregation | PENDING |
| Coordinator ADR-002/003 | horizon, t=0, late same-time, phase registry, public schema major/version approval | PENDING |

Acceptance requires an explicit GitHub **review/comment naming the precise #58 HEAD SHA, accepted schema pack/version and any exceptions**, then independent AI-R rereview, then coordinator ADR. Silence, task authorship, PR creation and the existence of a checklist are **not** signatures. Fixtures in STATE_EVENT_TEST_CASES.md are **NOT RUN**.


---

## 8. PR #61 binding correction — EventWindowRef and complete edge-of-time profile

> **Directed candidate, NOT formal Accepted ADR.** Sources: #61 `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc`, #55 `eca750b9b1c3fb25e6f6fd29732c4316d694e6f5`, #58 earlier `bd5e47266d79d1e087ca8cfc6fe68ea28a03496b`. This §8 is the event half of joint pack `state-event-proposal.v1-candidate-2` matching #55 §0 and fixes field names and ambiguities in preceding draft sections; those sections are historical design rationale. Candidate schema versions: `event-window-ref.v1-candidate`, `event-intent-batch.v1` (public message schema), `event-envelope.v1` (Harness record schema; registry candidate event-envelope.v1-candidate), `sim-clock.v1`. ARCH-02/03/01 must sign the actual mapping before FROZEN.

### 8.1 Definitive typed window vs interval: no aliasing

```python
# Non-executable logical types; each is a distinct typed, scoped Harness capability.
class EventWindowRefV1:
    run_id: str              # minted by Harness, validated against context
    generation: int          # uint64
    boundary_id: str         # Harness-minted run-local identity
    window_token: str        # OPAQUE, type-tagged and non-forgeable
    start_ns: int            # uint64, immutable
    end_ns: int              # uint64, immutable
    include_start: bool
    include_end: bool
    # Additional internal registry window_seq exists; no provider writes.

class ModelIntervalRefV1:
    opaque_id: str          # DIFFERENT type tag and scope, Dynamics only
    # Harness validates run_id/generation/boundary_id/start_ns/end_ns/dt_ns.

class EventIntentBatchV1:
    schema_version: str     # event-intent-batch.v1
    run_id: str
    generation: int         # uint64
    boundary_id: str        # public ProposalHeaderV1/Harness boundary_id
    read_view_token: str    # minted provisional stage scope
    producer_id: str        # authenticated EventProvider
    window_ref: EventWindowRefV1  # FIXED; never ModelIntervalRef
    intents: tuple          # EventIntentV1 only
    source_manifest_digest: str

# EventProvider.events_in_window(window:EventWindowRefV1,
#     state:ReadonlyView, ctx:ProposalContext) -> EventIntentBatchV1
# DynamicsModel.propose(..., interval:ModelIntervalRefV1, ctx:ProposalContext)
# NEVER receives EventWindowRefV1.
```

Harness validates **nominal type tag and lookup registry** (not Python structural fields or string similarity), minted run/generation and authorized component/phase, window_seq and exact nanosecond limits, then enforces every intent time inside the declared window. Wrong type → **WINDOW_REF_TYPE_MISMATCH / REJECT_REQUEST** before any stage/queue writes, even if the two records have the same numerical start/end. Prior §7.1's `ModelIntervalRef` reference is hereby **withdrawn**, as are `boundary_ref` / `observed_view_token` as public V1 batch fields. A legacy ingress adapter must be explicitly versioned, validated and logged, never a silent cast. An empty but structurally valid batch `intents=()` is an empty success, not a provider failure. EventProvider must not infer polling window from Dynamics duration.

### 8.2 Frozen-in-RunSpec candidate timing policy, exact boundary cases

| Case | Candidate V1 rule, deterministic order / state | Reject or termination behavior |
|---|---|---|
| **Initial `t=0`** | WorldState rev0 (time_ns=0, step_index=0) is published at init; Scenario EventSpec at 0 and EventProvider **initial event window [0,0] once** are queued before the first PRE_INPUT. First execution boundary stages PRE_INPUT(0) then PRE_DECISION(0) before first Scheduler observation, then advances only to next allowed barrier. | No implicit `t=0` world micro-commit; any t0 data submitted *after* first PRE_INPUT seal → INVALID_EVENT_ORDER; initial window cannot be queried twice to duplicate events. |
| **Normal provider polling** | After initial poll, `EventWindowRefV1` window inclusion = `(start_ns,end_ns]`. Scheduled event exactly at end included once and splits HYBRID interval before subsequent Dynamics continues. Never re-poll boundary start as new work. | Out-of-window intent → OUT_OF_EVENT_WINDOW, reject whole EventIntentBatch before admission. |
| **End `horizon_ns`** | Candidate `horizon_policy=INCLUDE_ONCE`. If an admitted event occurs at exact horizon, stage it at a **bounded terminal event-only boundary** at horizon, applying permitted PRE_INPUT/PRE_DECISION operations with no dynamics beyond horizon. This **may be zero sim-time**, but is a real boundary with one revision when control/domain facts change; it is *not* an arbitrary extra physics tick. Run terminates once after coherent final state. | `time_ns > horizon_ns` rejects HORIZON_EXCEEDED; no extra empty boundary merely for metrics; same-time cascade limit still enforced. |
| **Late same-time** | Candidate `same_time_late_policy=REJECT`: phase seal is monotonic; once PRE_INPUT(t) sealed, later admission of PRE_INPUT(t) or any lower phase is forbidden, **including a command arriving after prior boundary published at same time**. | INVALID_EVENT_ORDER / REJECT_REQUEST before admission; no silent deferral to a new t boundary. Caller must explicitly schedule a later valid timestamp when allowed by kind and horizon. |
| **Mid-tick precise event** | `time_s="3.5"` is exactly `3500000000` ns; HYBRID splits integration at this event barrier. Dynamics fact generated at interval end is committed to preceding boundary as `DomainFactV1`; queued PRE_INPUT at same end runs at next boundary before integrating beyond. | `3.0000000001` s is not integral ns and fails TIME_PRECISION_LOSS; no rounding to step tick. |
| **Unbounded zero-time cascade** | positive frozen `max_same_time_events` and `max_cascade_depth` cap all new same-time permitted-phase events; no retroactive phase insertion. | EVENT_CYCLE / ROLLBACK_BOUNDARY, B/C/D/queue/RNG/sequence revert. |

**Important:** these are now **one selected candidate profile** for #58 (not a choice among incompatible runtime defaults). At code assembly, the FrozenRunSpec must explicitly lock `initial_t0_policy=PROCESS_ONCE_BEFORE_FIRST_DECISION`, `event_window_inclusion=INITIAL_CLOSED_THEN_OPEN_CLOSED`, `horizon_policy=INCLUDE_ONCE`, `same_time_late_policy=REJECT`, `kind_phase_map_digest`, `priority_class_map_digest` if used, event-cascade and retry budgets; no missing default/fallback accepted. Their formal status remains COORDINATOR_DIRECTIVE pending ARCH-01/02/03 signature.

### 8.3 Versioned event-kind→phase map (typed, no accidental dynamic phase)

| Event kind (schema-qualified / example V1 registry entry) | PhaseV1 and rank | Effect owner / constraint |
|---|---|---|
| `environment.wind.update`, `weather.update` | PRE_INPUT (0) | ARCH-01 dynamic field state; before scheduling |
| `vehicle.fail`, `vehicle.recover` | PRE_INPUT (0) | ARCH-01 entity health/cargo policy |
| `facility.set_availability`, `facility.close`, `facility.open` | PRE_INPUT (0) | ARCH-01 ResourceLedger and facility policy |
| `airspace.activate`, `airspace.expire` | PRE_INPUT (0) | ARCH-01 restriction state; route revalidation |
| `demand.inject`, `demand.withdraw` | PRE_DECISION (1) | ARCH-01 tasks/queue; visible to Scheduler |
| `task.validation` / registered predecision constraint event | PRE_DECISION (1) | schema-versioned domain validation |
| `service.completion`, `delivery.committed` | **NOT QUEUEABLE** as an external event in V1 | become DomainFactV1 (POST_MODEL stage 4), no replay as future PRE_INPUT |
| Other kind (unregistered) | **no fallback** | UNKNOWN_PHASE_MAPPING / REJECT_ASSEMBLY or REJECT_REQUEST |

The **registry itself** is `EventKindPhaseMapV1`: `schema_version:string="event-kind-phase-map.v1-candidate"`, `mapping_id:string`, `entries:sorted tuple{kind:string, kind_schema_version:string, phase:PhaseV1, source_capability_ref:string, effect_reducer_ref:string, constraints_digest:Digest}`, `content_digest:Digest`. Owner: ARCH-02 implements registry admission, ARCH-01 declares world effect reducers, ARCH-03 declares source capabilities. Stable canonical registry order by normalized namespaced UTF-8 kind, no automatic substring/fallback matching. For a kind name overloaded across incompatible effect schemas, schema_version is part of lookup; conflict → EVENT_KIND_SCHEMA_CONFLICT. `APPLY_COMMAND` and `ADVANCE_MODEL` are **Harness invocation phases**, not arbitrary external event kinds; `POST_MODEL` contains validated service facts; `OBSERVE` is read-only after commit. A provider whose EventIntent.phase disagrees with the pinned kind map is rejected PHASE_CAPABILITY_MISMATCH.

### 8.4 Envelope, normalization and failure closure against PR #61

**One EventEnvelopeV1** admitted to run queue, with `schema_version, event_id, run_id, generation, time_ns:uint64, phase:PhaseV1, priority:int32, producer_id:string, producer_seq:uint64, kind, target_ref, payload, preconditions, failure_policy, causal_parent_id?, provenance, payload_digest, attempt:uint32`. Scenario EventSpec and EventProvider EventIntentBatch share exactly this normalized shape after Harness conversion; components cannot publish/enqueue Envelope directly. Sort key `(time_ns,phase_rank,priority,producer_id,producer_seq,event_id)` ASC. No runtime reliance on dict/set order or priority_class string sorting; duplicate ID same digest idempotent, different digest EVENT_ID_CONFLICT.

`ContractFailureV1` from STATE_COMMIT_CONTRACT §9 is the one diagnostic envelope: **REJECT_ASSEMBLY** on unbound map/ref/strict rollback capability at init; **REJECT_REQUEST** on wrong window/input time/late sealed phase before stage; **SKIP_EVENT** only on authorized frozen recoverable event, queue disposition at successful boundary commit; **ROLLBACK_BOUNDARY** on in-flight fatal event/operation, fully restore B/C/D, queue, RNG and producer seq; **POSTCOMMIT_PARTIAL** on postcommit Metric/evidence failure while keeping published state; **TAINT_LEGACY** for opaque partial legacy failures. All log `source_code`, `committed_revision` and `world_commit_occurred`. Requested lenience cannot turn a malformed Scheduler or Dynamics proposal into successful no-op.

**Required sign-off:** ARCH-02 owns event window/clock and boundary lifecycle, ARCH-03 + AI-B accepts public EventIntentBatch and ProposalHeaderV1, ARCH-01 accepts kind→domain reducer, AI-C accepts source sequence/RNG rollback, AI-D postcommit evidence, AI-R independently rechecks exact new #58 HEAD, and coordinator moves ADR-002/003 from directive to ACCEPTED only with named evidence. ALL NOT YET SIGNED; fixtures NOT_RUN.
