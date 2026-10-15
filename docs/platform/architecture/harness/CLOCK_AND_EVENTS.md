# ARCH-02 · Clock and Events

> Clock values below are normative proposals for the future Harness; existing Environment has a simpler loop.

## 1. Simulation time

SimClock owns integer sim_time_ns (nanoseconds since run epoch), monotonically non-decreasing. Public provider-facing time_s is sim_time_ns / 1e9; wall time is permitted only for performance tracing/timeouts. Configure positive step_ns and optional horizon_ns before initialization. Reject non-finite, negative, zero-duration fixed steps, and non-representable timestamps at assembly. The legacy compatibility profile reads its STEP_SECONDS from frontend/drone.py:22, presently defaulting to 1.0 second, and must not silently hardcode 1 second for all worlds.

The logical boundary index and committed revision are distinct: a discrete event at the same time can create more than one revision without advancing sim_time_ns.

## 2. Clock strategies

| Mode | Contract | Use |
|---|---|---|
| FIXED_STEP | Choose end = min(t + step_ns, horizon_ns); process ordered phases, integrate interval, commit boundary | Existing urban fleet experiments |
| DISCRETE_EVENT | Advance directly to the next due event time (or horizon); no implicit movement between times | Pure queue/service simulations |
| HYBRID | Integrate continuous components only until min(next event time, nominal tick boundary, horizon); then handle event at a barrier | Weather/failure/task generation with flight dynamics |

Mode and scheduler decision cadence are frozen per run and declared in manifests. In DISCRETE_EVENT/HYBRID, an event occurring at 3.5 s must not be postponed to 4 s if its timestamp is semantically exact. Integration is provided by ARCH-03 DynamicsModel and may be absent in purely discrete models.

## 3. Event envelope and total ordering

Event = (event_id, run_id, generation, time_ns, phase, priority, producer_id, producer_seq, type, payload, causal_parent_id). Order is lexicographic:
1. time_ns ASC;
2. phase rank ASC, with phase ranks PRE_INPUT, PRE_DECISION, APPLY_COMMAND, ADVANCE_MODEL, POST_MODEL, OBSERVE;
3. priority ASC (lower number first);
4. stable producer_id ASC;
5. per-producer monotonic producer_seq ASC;
6. event_id ASC as final explicit tie breaker.

Event producer IDs and event IDs must be stable manifest/entity-based IDs rather than Python object hash or unordered iteration order. Equal-time events may not insert new work into an already completed earlier phase; such proposals fail INVALID_EVENT_ORDER (or explicitly schedule next boundary). A configurable maximal same-time cascade count rejects non-advancing zero-time loops. Cross-component event delivery cannot mutate state synchronously from arbitrary callbacks; all handlers return proposals.

## 4. Per-boundary order

At time t, a stable barrier stages all due PRE_INPUT/PRE_DECISION changes in a validated **provisional view**, then gives Scheduler that read-only provisional snapshot at time t. Scheduler returns commands; Harness validates intent against capabilities and state, and stages accepted commands before domain advancement. DynamicsModel integrates from t to the selected end boundary, emitting ordered service/physics events and state proposals. EventProvider and domain handlers process due post-model events. Atomically commit the **single boundary revision** with clock, queue and RNG, evaluate domain termination and invoke read-only MetricProvider/Trace. Event queue and RNG consumption at a phase are included in its transactional checkpoint/rollback scope.

An external fault/task injection at exactly t is visible to the scheduler at t; a newly generated task at t+step becomes visible on the next decision unless the declared mode schedules a new decision at that same timestamp in a later allowed phase. Termination predicates are domain-supplied and evaluated only after a coherent state commit.

Legacy evidence: console/sim_session.py:180-185 invokes scheduler before Environment.step. frontend/environment.py:1033-1144 applies commands, advances current_time by STEP_SECONDS, then generates tasks; :1151-1250 updates drones, consumes service waypoint events, processes arrivals and berth arbitration. Adapter must preserve this legacy ordering for comparability; it is **not** evidence that every future model must mimic that sequencing.

## 5. Determinism, schedules and horizons

RNG: stable master_seed + run specification digest + component_id + stream_name are fed to a defined PRNG/key derivation (versioned); no use of Python hash(), random.seed(), np.random.seed() on a shared process stream. Record PRNG type/version, per-stream draw position and component order. An event carries producer local sequence assigned before enqueue. Providers may not access OS clock/random by default. Versioned deterministic numeric policy must declare rounding/float tolerance, external library versions and CPU-bound differences; byte-identical replay is guaranteed only within the declared environment profile and identical pinned artifacts.

Snapshot/replay stores event queue in canonical sorted form; no unordered dict/set iteration may determine event order. The horizon is an upper bound; no event after horizon is processed. At exactly horizon, apply declared end-boundary event policy, then terminate once; never run a zero-length extra step. Deadlines use absolute simulation timestamp and explicit inclusive/exclusive comparison owned by the domain model, not Harness.

Acceptance scenarios: two simultaneous task arrivals; fault and dispatch at same timestamp; event mid-tick in HYBRID; empty event queue in DISCRETE_EVENT; zero-time event cycle; pause at same-time cascade; replay after checkpoint with identical stream positions. The event policy must yield the same ordered event trace on equivalent reruns.
