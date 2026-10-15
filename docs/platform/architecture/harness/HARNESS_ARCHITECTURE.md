# ARCH-02 · Simulation Harness Architecture

> Status: DRAFT / design-only. Baseline: master @ 2ab60c69a806a22d7ba20353dee0571752a0e8e5 (2026-10-15 audit). No runtime implementation is changed by this proposal.

## 1. Purpose and decisions

A Harness is a deterministic, in-process orchestration boundary for one simulation run. It neither represents a particular city, drone, scheduling algorithm nor owns drone physics. It validates a frozen project/scenario specification, resolves component capabilities, assembles an ARCH-01 World, initializes ARCH-03 providers, advances authoritative state, and emits traceable run results. Default execution is synchronous and serial. Do not introduce microservices, distributed orchestration or plugin sandboxes.

**Decisions:** (H-01) one RunHandle per independent run, no process-wide mutable world/session; (H-02) one authoritative StateStore per run; (H-03) all state changes are staged and validated at commit barriers; (H-04) deterministic ordering and scoped RNG; (H-05) clock policy is configuration, not fixed to the legacy episode; (H-06) adapters preserve the old runtime without claiming it already implements H-02/H-03.

## 2. Verified legacy audit (implementation, not normative contract)

| Source (master) | Verified execution fact | Migration risk |
|---|---|---|
| console/server.py:61-76, 291-308 | Module-global single SimSession; op lock serializes individual HTTP steps; warm-up creates the first session | Not independently scoped runs; UI/transport controls life cycle |
| console/sim_session.py:103-165 | Constructor loads fixed default Yangpu OSM, instantiates Environment; reset builds scheduler, calls env.reset and clears presentation history | World/config construction and presentation cohabit |
| console/sim_session.py:167-210 | Greedy calls greedy_action_from_observation; other algorithms call scheduler.step(obs,current_time); env.step(action) follows | Mixed scheduler call signatures |
| frontend/environment.py:1033-1144 | env.step applies assignments, increments current_time by STEP_SECONDS, then generates tasks | Time/event ownership mixed into world object |
| frontend/environment.py:1146-1286 | Advances drones, consumes ordered consumed_waypoints_this_step, updates berth and metrics, determines done | Domain event semantics must remain with adapters/models |
| frontend/environment.py:1379-1453 | Reset seeds module-level RNG, recreates dynamic objects and initial tasks | Episode seed and world state share hidden globals |
| console/sim_session.py:441-547 | Checkpoint deep-copies dynamic environment, scheduler and Python/NumPy global RNG; cross-generation restore guarded | Not a portable, isolated transactional checkpoint |
| console/sim_session.py:48-72, 643-657 | rebuild reloads modules then reconstructs Environment | Hot reload is process-level and can affect concurrent runs |
| console/experiment_service.py:79-110 | Experiment runner launched as a separate process | Research batch workflow distinct from browser SimSession |
| frontend/scheduling_interface.py:12-69 | Observation/Action schema v1.0; abstract Scheduler.act | Available interface baseline; legacy concrete algorithms still use different entry points |

The initial fixed-step default is a **legacy compatibility profile**, not a future Harness invariant. Existing delivery truth is linked to service-waypoint consumption, not proximity: frontend/environment.py:1177-1231. The in-flight Draft PR #41 targets related lifecycle semantics on a different base branch; do not silently assume it is on master.

## 3. Logical dependency structure

ProjectConfig -> ConfigResolver -> FrozenRunSpec -> ComponentResolver (ARCH-03 manifests)
                                                         |
ARCH-01 Scenario + WorldDefinition -> WorldAssembler -> InitialWorldState
                                                         |
Execution request -> RunController -> [Clock, EventQueue, RNGScope, StateStore, Trace]
                                            |
                       read-only WorldView + RunContext
                                            |
            EventProvider -> Scheduler -> DynamicsModel -> MetricProvider
                                            |
                         ChangeSet validation / commit
                                            |
                    Snapshot / RunEventLog / ResultArtifact

All arrows are logical dependencies. Components depend on thin contracts and never on the controller, web server, environment class or concrete algorithms. ARCH-01 owns world/entity/scenario definitions. ARCH-03 owns component manifests/capabilities and provider contracts. ARCH-02 owns run control, execution order, isolation, transaction coordination and fault policy.

## 4. Minimum public contract (logical types, not code to merge)

- create(project_ref, scenario_ref, run_options) -> RunHandle in CREATED; no world side effects.
- assemble(handle) -> AssemblyReport; freeze resolved config, resource hashes and dependency graph; fail before state publication.
- initialize(handle) -> Snapshot(revision=0, time=0); initialize components in topological order and seed scoped RNGs.
- start(handle) / pause(handle) / step(handle, one_boundary=true) / stop(handle) / reset(handle, optional_new_seed) / destroy(handle).
- snapshot(handle) -> immutable StateView with run_id, generation, revision, sim_time_ns and clock mode.
- events(handle,cursor) / result(handle) -> ordered observations; neither advances the world.

RunScope contains RunId, run_generation, immutable FrozenRunSpec, Clock, StateStore, deterministic EventQueue, ScopedRNGFactory, structured Logger/Trace, ResourceRegistry, ordered component registry, cancellation token and budget guard. RunContext exposed to providers contains read-only world view, clock view, component-local RNG, structured event/logger, capability-filtered read-only resource access, plus output proposal factory. No provider receives the StateStore mutator.

## 5. Core constraints and excluded concerns

Invariants: run_id + generation uniquely identify a state store; no wall-clock time used as simulation time; ordered commands at an explicit barrier; serial writes; no state mutation from snapshot/metrics/UI; all IDs and units validated; snapshots only after committed revisions; terminal reasons explicit; reset is a new generation under the same handle, never leaking old pending events.

Out of scope: map parsing/coordinate conversion, energy/flight dynamics formulae, concrete task assignment heuristics, dashboard layout, task-specific reward semantics and arbitrary plugin sandboxing. Providers/adapters implement domain behavior; Harness only orders and verifies it.

## 6. Integration and unresolved contracts

**ARCH-01 dependencies:** WorldDefinition/Scenario/WorldState distinction; stable entity identifiers and referential constraints; coordinate/units contract; WorldState snapshot/patch schema; time-varying event representation. No implicit assumption that drone indexes are stable identifiers.

**ARCH-03 dependencies:** DataProvider, SpatialProvider, DynamicsModel, EventProvider, Scheduler and MetricProvider minimal interfaces; manifest/version and dependency graph; capability checks; initialize/close hooks; declared state access and failure policy. Model/algorithm manifests must be pinned to a run.

**ARCH-04 bridge:** LegacyEnvironmentAdapter may execute the existing Environment as an opaque single-writer step, translating legacy observations/actions and snapshots. Because env.step mutates in place, legacy mode cannot claim full StateStore atomic rollback without an explicit copy-on-write/rollback adapter. LegacySchedulerAdapter translates greedy callable vs PSO/GA/OR-Tools step signatures. Neither adapter may force future world type or clock policy.

**Compatibility caveat:** PR #41 (L1 task completion/delivery state, Draft against ci-validation) and PRs #42-#45 (TaskUI design, Draft against master) are not baseline implementations for this document. Re-audit changed lifecycle and UI endpoints before migration; do not merge or rewrite them in ARCH-02.

Acceptance: trace from config to assembled world to bounded progression to an immutable result; component invocation/ownership/fault handling documented in sibling contracts. Design questions requiring ARCH-01/03 confirmation remain open rather than masquerading as implemented behavior.
