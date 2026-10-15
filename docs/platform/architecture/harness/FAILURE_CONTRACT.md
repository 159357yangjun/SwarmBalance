# ARCH-02 · Failure, Timeout and Invalid-State Contract

> DRAFT design. Failures are first-class run outcomes, not silently swallowed exceptions.

## 1. Typed diagnostics

FailureRecord = {code, severity, run_id, generation, revision, sim_time_ns, phase, component_id, event_id?, command_id?, cause_chain, recoverable, committed_revision, policy, trace_ref}. Sanitize secrets and sensitive payloads. Codes: CONFIG_INVALID, CAPABILITY_MISMATCH, INIT_FAILED, INPUT_INVALID, INVALID_EVENT_ORDER, INVALID_STATE_CHANGE, STATE_CONFLICT, STALE_COMMAND, LIFECYCLE_CONFLICT, COMPONENT_EXCEPTION, COMPONENT_TIMEOUT, BUDGET_EXCEEDED, EVENT_CYCLE, CHECKPOINT_INCOMPATIBLE, REPLAY_MISMATCH, OUTPUT_FAILURE, CLEANUP_FAILURE.

Differentiate (1) preflight validation errors: run cannot leave CREATED/ASSEMBLED, (2) rejected commands/events: no mutation and optionally continue, (3) fatal state / core clock invariants: FAILED, (4) component exception/time budget: policy-controlled at barrier, (5) observer/export failures: committed world unaffected, surface incomplete evidence.

## 2. Default failure policy by source

| Source | Default policy | Observable effect |
|---|---|---|
| Invalid project, schema, units, manifest | FAIL_INIT | Nothing published |
| Invalid user dispatch/injection | REJECT_COMMAND | Return diagnostics; world unchanged |
| Scheduler exception/timeout | FAIL_RUN | Preserve last committed revision; no arbitrary fallback dispatch |
| DynamicsModel exception, NaN, negative battery, invalid reference | FAIL_RUN | Roll back phase; state/time unchanged |
| EventProvider malformed event/past scheduling | REJECT_EVENT or FAIL_RUN for required provider | Diagnostic + policy decision, never silently reorder |
| MetricProvider exception | MARK_METRIC_UNAVAILABLE | Committed world unchanged; output status explicitly partial |
| Logger/export failure | MARK_EVIDENCE_INCOMPLETE | No simulation rewind; escalate to FAIL_RUN when audit evidence is mandatory |
| Voluntary stop | STOPPED | Last coherent checkpoint and STOP_REASON |
| Horizon / domain success | COMPLETED | Completion reason preserved |
| Cleanup failure | REPORT_CLEANUP_FAILURE | Do not rewrite earlier terminal reason |

Overrides (SKIP_EVENT, RETRY, SUBSTITUTE_PROVIDER) require a predeclared, versioned per-component policy in FrozenRunSpec, evidence flag and bounded attempts. Never automatically substitute a scheduler/physics model without contaminating the comparison trace. A retry is legal only for proven side-effect-free deterministic operations, from a restored phase checkpoint (including RNG/queue), never after partial external side effects.

## 3. Timeouts: separate clocks

sim_time_ns: deterministic modeled time; does not elapse while a component computes.
wall_runtime_budget_ms / component_wall_deadline_ms: control operational hang prevention, measured by monotonic wall clock; may introduce variability in whether runs fail but **must not** change simulated physics or RNG ordering. timeout leads to abort at safe barrier or worker termination for uncooperative components. No forced thread kill, no hidden distributed requirement. CPU budget and event count budgets are recorded alongside hardware/runtime profile.

An unresponsive synchronous plugin cannot be safely interrupted inside process. In-process first implementation supports cooperative cancellation and after-return time checks; hard isolation/kill requires opt-in worker process in a later implementation, or mark timeout enforcement as NOT_GUARANTEED. Never claim rollback after an arbitrary in-place side effect.

## 4. Atomicity and recovery

Before execution, snapshot transactional B/C/D. An invalid proposal: discard all boundary-staged writes/events/RNG consumption and record a non-world diagnostic in trace. A postcommit metrics/export failure: do **not** revert the already committed complete boundary state or replay the step. For fatal provider failure: stop further world commits, transition FAILED, release safely, preserve partial result. Catching an exception and continuing on old components while reporting success is forbidden.

LEGACY_OPAQUE_STEP is not atomic: when env.step fails after in-place edits, mark session TAINTED/FAILED, prevent further step or checkpoint as trusted, retain diagnosis. Recovery requires clean rebuild/reset from pinned inputs. Cross-generation restoration remains rejected unless compatibility verified.

## 5. Reproducibility / evidence contract

Every run exports manifest hash, code revision, component versions, clock mode/step, seed/stream algorithm, input checksums, terminal reason, fault policy, event trace digest, committed snapshot digest, partial/complete flag. Treat bounded differences as explicit reproducibility profile rather than universal bit-exact guarantees. Comparisons exclude runs with hidden fallbacks or incomplete evidence unless analysis explicitly permits them.

## 6. Acceptance fault injection matrix

- Scheduler raises after consuming RNG: no world commit, FAILED, RNG continuation not consumed for a future retry.
- Dynamics model returns NaN energy: reject phase and freeze last coherent state.
- Task id missing: reject command, maintain existing assignments.
- Same-time event floods beyond configured limit: EVENT_CYCLE with deterministic trace.
- Timeout during long provider call: no unsafe kill; document cooperative limitation.
- Metric export fails postcommit: retain state revision and flag partial evidence.
- Reset a FAILED run: construct fresh generation with fresh provider instances.
- Compare two reruns with identical manifests/seed: equal event/state digests within declared deterministic profile.
