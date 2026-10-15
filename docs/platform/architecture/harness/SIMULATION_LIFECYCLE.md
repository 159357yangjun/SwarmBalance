# ARCH-02 · Simulation Lifecycle

> Design-only contract. State transitions are synchronized at commit barriers, not arbitrary UI/render frames.

## 1. State machine

CREATED -> ASSEMBLED -> READY -> RUNNING -> COMPLETED
                                 |          |
                                 |          +-> PAUSED -> RUNNING
                                 |                 |
                                 +-- step ---------+ (one boundary, returns PAUSED/READY)
                                 |          |
                                 +----------+-----> STOPPED
                                 |          +-----> FAILED
Any non-DESTROYED state -> DESTROYED after release.
STOPPED/COMPLETED/FAILED -> READY only by reset (new generation), followed by initialize.

Canonical states and legal operations:

| State | Meaning | Allowed controls |
|---|---|---|
| CREATED | RunHandle allocated; spec unresolved | assemble, destroy |
| ASSEMBLED | Config and dependency graph frozen; no published world yet | initialize, destroy |
| READY | Initial state revision 0 committed, no active loop | start, step, reset, destroy, stop |
| RUNNING | A run loop may cross commit barriers | pause, stop, snapshot |
| PAUSED | Quiescent at barrier, no in-flight mutable update | start, step, stop, reset, destroy |
| COMPLETED | Domain termination or horizon reached | snapshot, result, reset, destroy |
| STOPPED | Explicit user/system cancellation at barrier | snapshot, result, reset, destroy |
| FAILED | Contract/critical component failure; world frozen at last committed revision | snapshot, diagnostics, reset, destroy |
| DESTROYED | Resources released, handle invalid | none (destroy may be idempotent acknowledgment) |

STOPPING is an optional internal transient flag, not an externally observable stable state. Invalid transitions return LIFECYCLE_CONFLICT with state, requested operation and legal options; they never silently mutate state.

## 2. Operations

1. **create:** validate request shape and allocate unique run_id. No map parsing, random draws or state mutation.
2. **assemble:** resolve immutable Project/Scenario, pin resource/version hashes, validate ARCH-03 manifests, capability/unit/coordinate compatibility, topologically sort components; report all preflight diagnostics without partial world publication.
3. **initialize:** initialize components in dependency order, create ARCH-01 initial state, init RNG streams, clock and event queue, validate invariants, atomically publish revision 0; rollback and close initialized providers in reverse order on failure.
4. **start/run:** enforce one execution driver per run; repeat a deterministic boundary transition until stop, natural completion, failure, or budget limit. Neither transport polling nor rendering drives simulation implicitly.
5. **pause:** cooperative request; return only after current boundary is committed or discarded. Remain responsive to snapshot while waiting; mark a pause request as pending if a component is in flight.
6. **step:** execute exactly one configured execution boundary from READY/PAUSED, including all due zero-time phases within its bounded event budget. Do not interpret this as one second when clock mode is event-driven. Return READY/PAUSED unless terminated.
7. **stop:** request cancellation; quiesce at next safe barrier and return terminal STOPPED, preserving last committed state and partial result with explicit stop_reason.
8. **reset:** disallowed during an in-flight boundary without first quiescing. Increment generation, clear queues/history/metrics/streams, reset or reconstruct providers, reseed RNG, rebuild initial state at revision 0; never overwrite the previous generation's immutable exported results.
9. **destroy:** close reverse dependency order, flush best-effort trace and release resources. Do not reuse handle or allow scheduled callbacks after destruction.

## 3. Command serialization, concurrency and errors

Commands carry (run_id, generation, expected_revision, command_id). A run-local controller serializes all state-changing commands. Repeated command_id returns the recorded response; stale generation/revision fails with STALE_COMMAND. pause/stop requests may be queued during a boundary but never interleave with one. Single-process many runs are allowed through isolated run scopes, but serial per-run execution is mandatory; parallelism is an optional future executor implementation, not a new semantic contract.

Transport/UI play speed (1x/5x/10x), polling interval and background worker threads are not part of simulation semantics. They may request multiple committed boundaries but cannot change execution order.

## 4. Reset and checkpoint semantics

Reset is not checkpoint restore. A checkpoint is an immutable (manifest digest, state revision, clock, queued events, component-private checkpoint records, RNG streams/counters, event sequence, metric accumulators) recorded at a barrier. Restoring creates a new run generation or new run; reject incompatible component/schema/resource versions with CHECKPOINT_INCOMPATIBLE. Do not copy old mutable providers into new runs. No restoration of arbitrary Python module globals in the portable contract.

## 5. Acceptance transitions

- Create -> assemble -> initialize -> start -> natural stop emits one terminal reason and one final result.
- Pause amid a slow model returns only at a barrier; snapshot revision is coherent.
- Single-step from PAUSED advances one logical boundary, not arbitrary wall time.
- Two simultaneous steps for same expected revision cannot both succeed.
- Reset while another generation has pending events never receives those events.
- destroy twice does not double-close resources; operations after destroy are rejected.

Legacy mapping: SimSession.__init__/reset/step/rebuild are adapter operations; console/server.py maintains a global _session and per-step _op_lock today. Existing UI reset/rebuild must not be used as definitive future lifecycle behavior.
