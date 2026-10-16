# CONTRACT-01 — STATE_EVENT_TEST_CASES

> Design-only test fixtures and expected outcomes for ARCH-05-R2 B01/B03. **NOT EXECUTED**: no Python, CI, state machine, replay, integration, numerical-model or real-world validation run was performed. Status PROPOSED; test cases become executable acceptance requirements only after joint sign-off.
>
> Audit baseline: master 2ab60c69a806a22d7ba20353dee0571752a0e8e5; #54 99bd0eb6b910d691d6d7776da0a5fd3f973f2997; #46 b5f05a70a3306f1799fcae2c3f342f3ed9ee0048; #49 d155621aca66e3a80c388718093a452d17d71e10; #47 68382c649393057ffbf5a14508ab1ff72d575b09; #51 f2df96bc609ee1e430ea6eff2456c4577347c300.

## 1. Fixture execution requirements (future, not performed)

Common fixture parameters: strict boundary atomicity; generation=1; initial (revision=0, step_index=0, time_ns=0); frozen World/Scenario/Component digests; deterministic event-source identifiers; finite/typed units; single-threaded run-specific commit. Sample vehicle V1 capacity 100 Wh, current battery 80 Wh; task T1 pending, station S1 one berth; all are **illustrative values**, not real vehicle specifications. Deep-copy committed snapshot and canonical hash before each test. Check state, control state (clock, queue, producer sequence, RNG cursor and component D), public CommittedFrame, diagnostics and mutation rights. Assert full equality of old committed digests on precommit hard failure and exactly one external revision on success. Separate attempted trace from committed state log.

## 2. Positive and negative fixture matrix

| ID | Polarity / interface | Given → when | Expected assertion | Proposed responsibility / needed sign-off |
|---|---|---|---|---|
| ST-01 | POS / StateStore, ReadWorldView, BoundaryCommit | One valid dispatch T1→V1 and model energy -10 Wh in one boundary | revision 0→1, step 0→1; battery 80→70, assignment, motion and clock appear **together**; one public CommittedFrame only; no phase snapshot | ARCH-02 / ARCH-01,03 |
| ST-02 | POS / ProvisionalView | PRE_INPUT station S1 closed; Scheduler reads later provisional view at same t | Scheduler sees closed state while public snapshot concurrently still returns old revision; no granted new S1 lease; internal stage_seq changes but WorldState.revision does not | ARCH-02 / ARCH-01,03 |
| ST-03 | NEG / atomicity and error | PRE_INPUT wind=6 proposed; APPLY_COMMAND assigns T1; ADVANCE_MODEL outputs NaN energy | Whole boundary fails precommit; neither wind nor assignment nor clock/queue/seq/RNG/D cursor published; public snapshot identical pre-fence; fatal failure record with committed_revision=0 | ARCH-02 / ARCH-01,03 |
| ST-04 | POS / time and boundary identity | Dynamics interval ends at t=4s and commits one revision; a **pre-admitted** event due at t=4s then executes in next legal bounded event boundary | two distinct successful boundaries can share sim_time_ns=4e9 and each increments revision and step_index once; NO externally visible in-phase revision and NO late PRE_INPUT admitted after phase seal | ARCH-02 / ARCH-01,03 |
| ST-05 | NEG / stale revision/generation | ActionProposal from revision 2 submitted against revision 3 or a reset generation | STALE_OBSERVATION/STALE_GENERATION; no state change or silent rebase | ARCH-02 / ARCH-03 |
| ST-06 | POS / EventSpec→Envelope | Frozen spec time_s="3.5", priority=10, wind update; registered PRE_INPUT map, source seq 0 | envelope time_ns=3500000000, PRE_INPUT, priority 10, stable source; HYBRID split; updated field visible to scheduler next boundary before model integrates after 3.5s | ARCH-01/02/03 |
| ST-07 | NEG / exact time | external seconds "0.0000000001", NaN or overflow; fixed-step forbids necessary mid-tick split | TIME_PRECISION_LOSS / INVALID_TIME / TIME_OVERFLOW / CLOCK_SEMANTICS_MISMATCH; no silent round or time drift | ARCH-02 / ARCH-01,03 |
| ST-08 | NEG / event dedup | admitted event_id E same digest re-sent; then E with different payload | same digest idempotent/no second effect; different content EVENT_ID_CONFLICT and no queue/world mutation | ARCH-02 / ARCH-01,03 |
| ST-09 | POS / total event ordering | t=4s fault PRE_INPUT priority 20 from producer b seq0; wind PRE_INPUT priority10 from producer z seq0; arrival PRE_DECISION priority0 from a seq0 | order: wind, fault, arrival by phase then priority; Scheduler sees all applied facts; repeated equivalent run produces same canonical order digest under pinned profile | ARCH-02 / ARCH-01,03 |
| ST-10 | NEG / phase cascade | POST_MODEL event at t tries inserting PRE_INPUT(t) after phase seal; repeated same-time chain hits bound 5 | INVALID_EVENT_ORDER, or EVENT_CYCLE; never reopen previously published phase or partially commit before failure | ARCH-02 / ARCH-03 |
| ST-11 | POS / soft event failure | optional missing target and EventSpec record_and_skip frozen; later valid event | skipped event writes rejection/consumed disposition in successful boundary exactly once; later valid operations commit; failed event's domain ops not applied | ARCH-01/02/03 |
| ST-12 | NEG / domain invariants | two vehicles claim same exclusive resource; task custody transferred to two owners; negative battery; duplicate operation_id differing content | STATE_CONFLICT / CUSTODY_CONFLICT / STATE_INVARIANT_FAILED / PROPOSAL_ID_CONFLICT; boundary unchanged including queue/RNG/D | ARCH-01/02 |
| ST-13 | POS / postcommit metrics failure | atomic commit succeeds then MetricProvider raises | snapshot retains newly committed revision and state; metric unavailable, output PARTIAL / EVIDENCE_INCOMPLETE, no re-run of physics | ARCH-02/03 / CONTRACT-04 |
| ST-14 | NEG / private state checkpoint | stateful scheduler has no reliable rewind declaration in strict RunSpec | assembly rejects CHECKPOINT_UNAVAILABLE / CAPABILITY_MISMATCH; not a best-effort rollback | ARCH-02/03 / CONTRACT-02 |
| ST-15 | POS / snapshot isolation | two readers request snapshot while staging at step r→r+1 | each reader sees coherent r or coherent r+1, never half updated battery/leases or provisional stage | ARCH-02 |
| ST-16 | NEG / same-time completion fact | motion interval t=3→u=4 creates delivery completion at u; independent PRE_INPUT fault also effective at u | delivery fact becomes committed at previous interval endpoint; fault processed by next boundary's PRE_INPUT at u; audit distinguishes fact_time/producing boundary; scheduler thereafter sees both; never mis-sort delivery as pending envelope of phase POST_MODEL versus PRE_INPUT | ARCH-01/02/03 |
| ST-17 | NEG / producer sequence collision | two event providers report same producer_id + seq with unequal IDs, or input priority_class has no pinned map | INVALID_PRODUCER_SEQUENCE / INVALID_PRIORITY_CLASS; admission rejected without nondeterministic tie breaking | ARCH-02/03 |
| ST-18 | POS / checkpoint replay specification | checkpoint committed queue+RNG+producer counters and pinned definition digests; restore into new generation | compatible restore runs same canonical event-order/state digests within declared profile; old generation views rejected; **future execution gate, not demonstrated** | ARCH-02/03 / CONTRACT-03 |
| ST-19 | NEG / retry policy | missing precondition, retry_without_max or zero backoff | INVALID_FAILURE_POLICY; no infinite zero-time cascade; legitimate bounded retry requires transactional source checkpoint and exact positive backoff_ns | ARCH-01/02/03 |
| ST-20 | NEG / legacy non-transaction | legacy Environment.step mutates object then throws | mark TAINTED/FAILED; forbid trusted new STRICT_ATOMIC_BOUNDARY snapshot and avoid false rollback claim | ARCH-04 / ARCH-02 |

## 3. Interface test contracts and mutation guards

Each component signature is a **logical draft schema**, not working Python:

| Interface | Schema fixture/check | Error assertion | Cases |
|---|---|---|---|
| WorldState / ReadWorldView | run_id:str, generation:uint64, revision:uint64, step_index:uint64, sim_time_ns:uint64, world/scenario immutable refs; entities/tasks/leases/fields typed maps | no mutable live pointers, unknown refs/unit/ref revision rejected | ST-01,02,05,12,15 |
| ProvisionalView / ChangeSet | base_revision:uint64, boundary_id:str, stage_seq:uint64, view_token:str; operations ordered with typed target and provenance | no external stage publication; obsolete token and write conflicts reject | ST-02,03,05,12 |
| BoundaryFence / Commit | B/C/D snapshot tokens, queue/RNG counters, from/to revision and digests | complete restore precommit and no duplicate commit | ST-01,03,13,14 |
| SimClock | authoritative uint64 ns; float seconds projection; uint64 step/revision independent from elapsed time | reject nonrepresentable times, overflow/regression and invalid clock mode | ST-04,06,07 |
| EventSpecV1 | namespaced kind/ID, decimal time, int32 priority, payload, preconditions, on_failure, provenance | reject missing schema, ambiguous phase or target | ST-06,07,11,19 |
| EventIntentV1 | source ID and monotonically tracked seq, ns-convertible at_seconds, PhaseV1, typed priority, payload/preconditions | reject legacy stable_order_key as substitute for seq | ST-08,09,10,17 |
| EventEnvelopeV1 | (run_id,generation,event_id,time_ns,phase,priority,producer_id,producer_seq,payload_digest) + kind, refs, causal parent, policy | reject conflicting duplicate ID, sealed phase, invalid retry | ST-06,08,09,10,17,19 |
| CommittedFrame | immutable domain truth + revision/step/time, accepted/rejected event facts, commit digest | no precommit visibility; observer failure cannot rewind | ST-01,03,13,15,16 |

**Suggested future implementation harness:** portable property-based generators for time conversion and stable sort keys; deterministic fixture golden JSON; fault injection at each phase, queue reservation and commit publication point; concurrency snapshot stress; explicit failure-code assertions. A test labelled PASS must provide actual command, code commit SHA, observed output/artifact SHA and execution environment. This document supplies none of those runtime observations.

## 4. Counterexample narratives

**Counterexample A (B01)**: If PRE_INPUT wind change publishes revision r+1 and model later fails, outsiders have seen the wind without assignment/model effects; ARCH-02's rollback would return to r after observers already consumed r+1. **Required V1 invariant**: no publication until all phases validate; mid-boundary stages are private and disappear on failure.

**Counterexample B (B03)**: Sorting `time_s` float and EventIntent `priority_class="high"` beside EventSpec numeric priority 10 cannot define a portable order. **Required V1 invariant**: exact ns integer, mapped numeric priority, explicit phase/source/sequence and immutable event ID; ambiguous conversion rejects.

**Counterexample C (cross-boundary)**: Interval [3,4] completes delivery at 4; independently fault event at 4 is queue phase PRE_INPUT. Treating both as single homogeneous EventEnvelope with global (time,phase) would imply PRE_INPUT fault preceded physical delivery already integrated to 4. **Required V1 invariant**: completed model fact at interval end versus next boundary's due envelope are different objects with distinct provenance.

**Counterexample D (private state)**: Scheduler advances hidden local RNG/cache and then Dynamics fails. World-only rollback leaves a different next scheduler response despite same revision. **Required V1 invariant**: strict-mode component private state must be rollback-safe or pure; otherwise assembly rejects.

## 5. Acceptance and sign-off gates

- G-SE-01: ARCH-01, ARCH-02, ARCH-03 explicitly accept single externally published boundary revision and stage-only internal views; record ADR-002 and reconcile conflicting wording in their own future authorized work (not this PR).
- G-SE-02: Clock/event type/schema fields, exact ns conversion, phase-kind mapping, numeric priority, canonical key and source-seq provenance agreed with ARCH-01/02/03; CONTRACT-03 co-sign RNG.
- G-SE-03: CONTRACT-02 signs proposal view tokens, component state and rollback capability. CONTRACT-04 signs CommittedFrame, postcommit incomplete-evidence semantics.
- G-SE-04: ARCH-04 documents LEGACY_OPAQUE_STEP differences; no artificial "legacy parity pass".
- G-SE-05: Independent reviewer runs **future** positive/negative fixtures with saved evidence; no design example is reported as actual pass.
- G-SE-06: Coordinator #61 already directed the single strict-boundary public revision and one public ProposalHeaderV1 / EventWindowRefV1 direction; #58 selects a single candidate timing policy in TIME_AND_EVENT §8 (initial t0 once; normal (start,end]; INCLUDE_ONCE horizon; late phase REJECT; explicit kind→phase map). **Actual ARCH-01/02/03 sign-off and final accepted ADR remain outstanding**, so HOLD / NO-FREEZE.

## 6. Source freshness and boundaries

The five PR HEADs above were inspected via GitHub at the start of this task; #54 locks identical #46/#49/#47. Should any head move after this, reviewers must re-fetch affected source blobs and mark impacted fixtures STALE, not blindly accept old review. This PR adds only the three Markdown docs in contract-01; does not edit any original ARCH-01–04 PR, code, main/master, tests, configuration, existing evidence, or governance files. No merge is authorized.


---

## 7. Cross-contract normalization + failure tests (addendum; FUTURE / NOT RUN)

Source-lock for this addendum: CONTRACT-02 PR #55 HEAD `b00cd337de2797b9819089b234a113e36513e003`, CONTRACT-03 #56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`, CONTRACT-04 #57 `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`, CONTRACT-05 #60 `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`, independent review #59 `28daf1e336a1447b098b4d6fa044095b7caa1f4f`. Crosswalk contract candidate is `state-event-proposal.v1-candidate-1` in STATE_COMMIT_CONTRACT §8 and TIME_AND_EVENT_CONTRACT §7. **No runnable fixture exists in this PR, and every status below is NOT_RUN.** Numbered names ST-21+ extend, rather than relabel, the original ST-01…20.

| ID | Positive/negative and input | Precisely required *future* assertion | Failure disposition and signer | Executed? |
|---|---|---|---|---|
| ST-21 | POS: valid ActionProposalV1 with **common `header:ProposalHeaderV1`** {`boundary_id=boundary:X`,`base_revision=4`,`read_view_token=view:A`, producer/capability/provenance IDs} and AssignTaskChain | Harness normalizes typed ActionProposal to **internal-only** `NormalizedChangeSetV1` sharing validated header, `phase=APPLY_COMMAND`; stage assignment, not cargo pickup; commit once to rev 5 after full validation | AI-B, ARCH-01/02/03 | NOT_RUN |
| ST-22 | POS: Dynamics StateDeltaProposalV1 after scheduler stage view:B, with 10 finite Wh | `based_on_view_token=view:B` maps to same canonical view-token field; single atomic position+mode+10 Wh debit; no model-side battery update; no second receipt in metrics | AI-B, ARCH-01/02 | NOT_RUN |
| ST-23 | NEG: Dynamics proposal with prior view:A although base committed revision still 4 | `STALE_OBSERVATION`, `ROLLBACK_BOUNDARY`, **not accepted because revision matches**; B/C/D/RNG/queue/seq unchanged | AI-B, ARCH-02 | NOT_RUN |
| ST-24 | NEG: caller uses `clock_ref` as public header `boundary_id`, supplies obsolete opaque `boundary_ref` without versioned adapter, or old-generation Dynamics `model_interval_ref` | BOUNDARY_ID_CONFLICT / CONTRACT_VERSION_MISMATCH / INTERVAL_MISMATCH, no stage; explicit public header and typed opaque tokens cannot be interchanged | AI-A/B, ARCH-02 | NOT_RUN |
| ST-25 | NEG: ActionProposal unsupported variant, float NaN weight or `actor_vehicle_id=0` legacy index | `INVALID_ACTION`/`CONTRACT_VERSION_MISMATCH`, `NONFINITE_VALUE` or `ENTITY_REFERENCE_INVALID`; no implicit free-form patch or index fallback | ARCH-01/03 | NOT_RUN |
| ST-26 | POS: Dynamics service-fact candidate with evidence, subject, service ref at interval end_ns=4e9 | `DomainFactV1` deterministic fact_id from run/generation/boundary/proposal/ordinal; validated custody+delivery transition in POST_MODEL of producing boundary; **no queued EventEnvelope** for same fact | ARCH-01/02, AI-B | NOT_RUN |
| ST-27 | NEG: service completion based solely on proximity or absent evidence, and provider tries direct cargo mutation | `SERVICE_FACT_INVALID`; no delivery, custody transfer, MetricSample success, or bypass StateCommitter; precommit boundary rollback | ARCH-01/03, AI-D | NOT_RUN |
| ST-28 | POS: Scenario EventSpec `time_s="3.5"`, no explicit phase, registered kind phase-map | preserved ID, int32 priority, scenario producer/source ordinal; normalized EventEnvelope time_ns=3500000000; one queue admission; predecision view observes due event before Scheduler | ARCH-01/02/03 | NOT_RUN |
| ST-29 | POS: EventIntentBatch with `intents=[]` and valid Context + window | explicit empty batch accepted as no requests, distinct from malformed/exceptional provider return; no fabricated event or sequence increment | AI-B, ARCH-02 | NOT_RUN |
| ST-30 | NEG: EventProvider submits `priority_class="urgent"` without digest-pinned map; `stable_order_key` but no producer_seq reservation | `INVALID_PRIORITY_CLASS` / `INVALID_PRODUCER_SEQUENCE`, `REJECT_REQUEST` preadmission, all batch intents rejected, unchanged queue/sequence | AI-A/B, ARCH-02/03 | NOT_RUN |
| ST-31 | NEG: same event_id with distinct payload hash, or two distinct events collide on (producer_id, producer_seq) | `EVENT_ID_CONFLICT` / `INVALID_PRODUCER_SEQUENCE` including `source_code`, no second domain effect; stage-time hard error rolls back whole open boundary | ARCH-02, AI-C | NOT_RUN |
| ST-32 | POS: event precondition fails with frozen `record_and_skip`; Scheduler valid proposal also staged | only failed event's local operations discarded; single completed boundary consumes event and commits rejection ledger, Scheduler change; `SKIP_EVENT` diagnostic states `world_commit_occurred=true` **only after** commit | ARCH-01/02 | NOT_RUN |
| ST-33 | NEG: invalid Scheduler proposal treated as `record_and_skip` or converted to empty success | invalid non-event proposal cannot opt into EventSpec failure policy; `ROLLBACK_BOUNDARY`, no revision increase, typed `ContractFailureV1` | ARCH-02/03 | NOT_RUN |
| ST-34 | POS+NEG: postcommit MetricProvider exception or output failure with existing CommittedFrame | `POSTCOMMIT_PARTIAL`, `world_commit_occurred=true`, new committed revision retained; evidence PARTIAL/INCOMPLETE, **no** replay of physics and no fabricated MetricSample=0 | ARCH-02/03, AI-D | NOT_RUN |
| ST-35 | NEG: TRANSACTIONAL scheduler lacks reliable `prepare_commit`/no-throw `publish_prepared` or RNG restore; declares strict | `COMPONENT_RECOVERY_UNSUPPORTED`, `REJECT_ASSEMBLY`; no partial READY WorldState; PURE explicitly stateless may use empty D checkpoint | AI-B/C, ARCH-02/03 | NOT_RUN |
| ST-36 | POS+NEG: event at horizon under frozen `INCLUDE_ONCE` vs `EXCLUDE` policy, plus t=0 event and late PRE_INPUT after seal | exact declared horizon/t0 decision, never an implicit extra tick; late earlier-phase work → `INVALID_EVENT_ORDER`; no hidden fallback | ARCH-01/02/03, coordinator | NOT_RUN |

### 7.1 Machine-readable acceptance evidence required later

A future implementation test result for each ST-xx must record: `case_id`, `contract_pack_version`, `frozen_PR_HEADs`, `implementation_HEAD`, `command`, `environment_digest`, `input_fixture_digest`, `expected_state_digest`, `observed_state_digest`, `expected_committed_revision`, `observed_committed_revision`, `expected_error/disposition`, `observed_error/disposition`, `queue_rng_private_checkpoint_before_after`, `trace_uri`, `actual_status(PASS|FAIL|NOT_RUN)`. A predicted outcome without observed test log remains `NOT_RUN`. Unit tests here would prove **software Verification only**, not Legacy parity, measured flight physics, Validation or experiment integrity.

### 7.2 Formal review and co-sign packet

| Reviewer role (not an assumed GitHub identity) | Review scope / acceptance fields | Required evidence | Status |
|---|---|---|---|
| ARCH-02 / Harness state owner | `NormalizedChangeSetV1`, BoundaryRef/ClockRef/ViewToken/ModelIntervalRef, commit/abort, ContractFailureV1 | GitHub comment/review citing **exact latest PR #58 HEAD and pack version**, ACCEPT/CHANGES_REQUESTED with objections | PENDING |
| ARCH-01 / World domain owner | typed operations, invariant/reducer, ServiceFactCandidate→DomainFact, EventSpec kind mapping | same, plus reference to changed domain rule | PENDING |
| ARCH-03 + AI-B / CONTRACT-02 | `ObservationV1` / `ActionProposalV1` / `StateDeltaProposalV1` ↔ ChangeSet, EventIntentBatch compatibility | same, explicit component-side schema acceptance | PENDING |
| AI-C / CONTRACT-03 | RNG cursor and transaction producer_seq, retry/checkpoint | same, stream/version notes | PENDING |
| AI-D / CONTRACT-04 | CommittedFrame and partial evidence state | same, no duplicate RunRecord or metric on failure | PENDING |
| ARCH-04 | LEGACY_OPAQUE_STEP not strict transactional | same, adapter difference declaration | PENDING |
| Independent AI-R / ARCH-05-R3 | review all five **latest** contract HEADs, B01/B02/B03/B06 delta gate | independent file-level verdict (not self-approval) | PENDING |
| Coordinator / ARCH-06 | ADR-002/003, phase/horizon/late-event decisions, final gate | explicit ACCEPTED decision + signers + date + frozen HEAD | PENDING |

No sign-off obtained by writing these tables or creating a PR. GitHub reviews from the **PR author alone** are not independent sign-offs; do not fake user identities or infer AI agent approvals from shared repository account. For every change in #58 HEAD after a review, reviewers must reaffirm the new HEAD or explicitly scope an incremental re-review. #59's prior fixed-HEAD judgment does **not** automatically endorse this amendment.

### 7.3 Scope and current verdict

- Artifact status: three **design** Markdown documents amended in existing CONTRACT-01 branch only; no ARCH-01–04 files, old PR branches, Python, config, legacy results or master changed.
- Actual GitHub metadata/blob checks are valid evidence of authored design and path scope only. **Implementation/run test PASS = 0; no executable test run, no CI, no physical validation.**
- **B01/B02/B03/B06: schema convergence proposed; independent design/owner signatures pending. HOLD / NO-FREEZE.** B04/B05/B07 remain under their respective independent owners, not accepted by this amendment.


---

## 8. Directed P0-01/P0-02 closure fixtures for PR #61 (all NOT_RUN)

> Source: ARCH-06 coordinator directive #61 at `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc`, AI-B #55 at `fd7ae6a5668f2cd97174628120435281e31e1a30`, CONTRACT-01 STATE_COMMIT §9 and TIME_AND_EVENT §8 (joint `state-event-proposal.v1-candidate-2`, matching #55 at `eca750b9b1c3fb25e6f6fd29732c4316d694e6f5`). These cases supersede earlier ambiguous public `boundary_ref` or `EventIntentBatch.window_ref:ModelIntervalRef` fixtures, which must not be implemented as alternate valid ABI. No test actually ran; **every row NOT_RUN**.

| ID | Input (positive / negative) | Single expected result and exact failure mapping | Owner / signature | Actual |
|---|---|---|---|---|
| ST-37 | POS: Scheduler returns `ActionProposalV1{header:ProposalHeaderV1(run_id,generation,boundary_id,base_revision,read_view_token,proposal_id,producer_id,capability_ref,provenance_ref),actions}` | All nine public header fields required; Header is echoed without incompatible duplicate aliases; Harness emits internal `NormalizedChangeSetV1` with typed `task.assign_chain.v1`, no public change-set.v1 endpoint | ARCH-02/03 + AI-A/B | NOT_RUN |
| ST-38 | NEG: public `ChangeSetV1/change-set.v1` sent by component, or unknown untyped `kind="set arbitrary_field"` | `CONTRACT_VERSION_MISMATCH` or `DOMAIN_OPERATION_UNMAPPED`, `REJECT_REQUEST` preadmission; no queue/state/clock mutation | ARCH-01/02/03 | NOT_RUN |
| ST-39 | NEG: same committed revision but wrong provisional read_view_token, or `boundary_ref` alias sent as strict public header boundary_id without converter | `STALE_OBSERVATION` or `BOUNDARY_ID_CONFLICT/CONTRACT_VERSION_MISMATCH`; no stage; previous generation token never reused | ARCH-02/03 | NOT_RUN |
| ST-40 | POS: EventProvider `EventIntentBatchV1.window_ref:EventWindowRefV1`, fixed [0,0] initial poll and subsequent (start,end] windows | Exactly one t0 poll before first Scheduler observation; subsequent event at right endpoint admitted once; `window_seq`/run-generation capability verified; same event not admitted twice | ARCH-02/03 + AI-A/B | NOT_RUN |
| ST-41 | NEG: EventProvider hands `ModelIntervalRefV1` as `EventIntentBatchV1.window_ref`, even when both have start=0/end=4e9 | `WINDOW_REF_TYPE_MISMATCH` with `disposition=REJECT_REQUEST`, no partial batch accept, no producer_seq reservation/queue change | ARCH-02/03 + AI-A/B | NOT_RUN |
| ST-42 | POS: `environment.wind.update` and `facility.set_availability` at t=0; `demand.inject` also at t=0; pinned phase-kind-map | wind/facility PRE_INPUT(0), demand PRE_DECISION(1), then Scheduler sees both; no external micro-commit revision in between, only once at full boundary | ARCH-01/02/03 | NOT_RUN |
| ST-43 | NEG: unknown `event.kind`, same registered kind with mismatched requested phase, or EventSpec with absent versioned mapping | `UNKNOWN_PHASE_MAPPING` / `PHASE_CAPABILITY_MISMATCH` and `REJECT_ASSEMBLY` or `REJECT_REQUEST` per admission phase; no guessed phase or fallback | ARCH-01/02/03 | NOT_RUN |
| ST-44 | POS: one event at exactly horizon_ns, one event beyond horizon; `horizon_policy=INCLUDE_ONCE` | valid horizon event executes exactly once in bounded terminal event-only boundary (if needed), no physics > horizon and no empty phantom boundary; event beyond horizon rejects `HORIZON_EXCEEDED` | ARCH-02/03, coordinator | NOT_RUN |
| ST-45 | NEG: EventIntent submitted for already sealed PRE_INPUT at same t, even after preceding committed boundary | `INVALID_EVENT_ORDER`/`REJECT_REQUEST` with no implicit deferral, no second micro revision; explicit strictly later valid timestamp required | ARCH-02/03 | NOT_RUN |
| ST-46 | NEG: Scheduler proposal throws after staging wind, assignment and RNG/private D; postcommit metrics separate test | Precommit → `ROLLBACK_BOUNDARY` with exact B/C/D/queue/RNG/producer_seq old digests; metric error only postcommit → `POSTCOMMIT_PARTIAL`, committed revision retained and no replay | ARCH-02/03, AI-D | NOT_RUN |
| ST-47 | NEG: duplicate `proposal_id` different semantic digest; `service_facts` forcibly emitted as queue Envelope | `PROPOSAL_ID_CONFLICT` or `INVALID_EVENT_ORDER`; domain completion is POST_MODEL DomainFactV1, not a due envelope at same time; no double delivery/battery debit | ARCH-01/02/03 | NOT_RUN |

### 8.1 Exact sign-off and future evidence requirement

AI-A signs only authorship of #58 draft and records a **request**, never AI-B's or ARCH-01/02/03's consent. To close P0-01/P0-02: #55 and #58 must both contain matching public `ProposalHeaderV1` (nine fields), internal-only `NormalizedChangeSetV1`, `EventIntentBatchV1.window_ref:EventWindowRefV1`, distinct Dynamics `ModelIntervalRefV1`, `EventEnvelopeV1` and one boundary revision, plus matching `ContractFailureV1` dispositions. Each named owner must post explicit review on **both latest immutable HEAD SHAs** or a scoping note of the exact one(s) reviewed. An independent AI-R review must re-open #59 for those latest HEADs, and coordinator must approve ADR-002/003. Planned test outcomes above do not demonstrate a runtime gate; `actual=NOT_RUN`, CI/flight validation = NOT_ASSESSED.

**Final local candidate disposition:** P0-01/P0-02 = **DOCUMENTS RECONCILED IN #58 / CROSS-PR CO-SIGN PENDING / NO-FREEZE**. No merger/implementation/verification claim.
