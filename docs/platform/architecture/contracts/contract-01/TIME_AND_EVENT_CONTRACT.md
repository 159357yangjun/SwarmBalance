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

**Boundary dimensions:** end time may equal start for bounded same-time work; neither revision nor step_index can be used to infer seconds elapsed. A long FIXED_STEP t→t+dt cannot silently skip an exact at=3.5 event; if a boundary cannot split its interval, **reject assembly** with CLOCK_SEMANTICS_MISMATCH or configure documented discrete/hybrid cut. Strict V1 recommends HYBRID splitting at exact event barriers. At horizon no event > horizon may execute. At exactly horizon, a pre-frozen inclusivity policy applies; no extra zero-duration tick just to run metrics.

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
\`(time_ns ASC, phase_rank ASC, priority ASC, producer_id UTF-8 bytewise ASC, producer_seq ASC, event_id UTF-8 bytewise ASC)\`.

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

\`Scenario EventSpec --validate frozen source/decimal time/phase mapping--> EventIntent-equivalent normalized record --Harness admission--> EventEnvelope\`.
\`EventProvider EventIntent --validate capability/source order/time/phase/schema--> EventEnvelope\`.
Only Harness creates the run_id/generation and canonical queue entry. Scenario events with no phase use a **versioned event-kind→phase mapping**, not arbitrary default; unknown mapping must fail assembly. Existing EventSpec priority is copied exactly as int32 after range validation. Existing EventIntent priority_class needs a manifest-pinned conversion table to numeric priority; missing/ambiguous mapping fails; do not lexicographically sort strings. Existing stable_order_key may be retained for provenance but not as ordering input. Converters must record source schema/version, input digest, mapping version and output digest.

1. Validate identity, units, time representation, phase/kind/priority mapping and source contract.
2. Check event_id duplication versus admitted-event ledger and producer_seq monotonic uniqueness, time >= current admission seal; reject past, expired, or already sealed earlier-phase events.
3. Reserve deterministic producer_seq/event identity and staged queue/RNG cursors as transaction B/C. Same boundary hard failure restores all reservations.
4. On execution validate preconditions on the latest provisional view, not an obsolete committed frame. The event handler proposes declarative operations; it never mutates B directly.
5. abort_run: invalidate whole uncommitted boundary, preserve last committed revision, mark Run FAILED. record_and_skip: stage *rejected disposition* and consume the event only at a successful boundary commit, no partial domain operations. retry_with_limit: only for predeclared deterministic and rollback-safe cases, schedule an exact later valid time and record attempt; max and backoff must be frozen. Zero-backoff retries disallowed in V1.
6. Events created after commit or by an observer do not retroactively enter a closed boundary. Observer failures keep committed state, mark incomplete evidence.

**Illustrative fixtures (design only):**
- Spec \`{event_id:"wind:1",time_s:"3.5",priority:10,kind:"environment.wind.update",target_ref:"field:wind",payload:{u_ms:6,v_ms:0},on_failure:"abort_run"}\` with kind map PRE_INPUT and source \`scenario:s1\` ordinal 0 -> envelope \`time_ns=3500000000,phase=PRE_INPUT,priority=10,producer_id="scenario:s1",producer_seq=0\`. At 3.5 s HYBRID barrier, next scheduler sees wind=6 m/s.
- Two independent fault and demand events at 4.0 s: PRE_INPUT fault applied before PRE_DECISION arrival; if same phase, priority and source sequence determine order; no scheduler dispatch to a closed facility.
- Input \`time_s="3.0000000001"\` rejects TIME_PRECISION_LOSS; \`priority_class="urgent"\` with no mapping rejects INVALID_PRIORITY_CLASS.
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
| choice between late same-time reject vs deferred explicit next boundary; horizon inclusivity; initial t=0 pre-input, event-kind phase-map; non-exact timestamp tolerance | Coordinator via ADR-002 with ARCH-01/02/03 signatures | **NEEDS DECISION** |

**Required future review:** Re-open B01/B03 if any of the exact PR HEADs above change; read changed blobs and revise the matrix. Do not report these fixtures as executed runtime tests. No physical/model validation performed.
