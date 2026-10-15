# ARCH-02 · State Ownership and Commit Contract

> DRAFT design. Not a claim that the legacy Environment is transactional.

## 1. Sole writer, snapshots and scope

Each run generation has exactly one authoritative StateStore. ARCH-01 supplies entity/state schema and invariants. The Harness owns the store transaction coordinator, versioned revisions and clock; it does **not** own domain values or physical formulas. ReadWorldView(revision, generation) is immutable and safe to share with providers. Snapshot consumers cannot call mutable entity methods or hold raw pointers to live Drone/Task/Station instances.

Partition state into: (A) immutable Project and WorldDefinition resources; (B) scenario-initialized domain WorldState (entity attributes, ownership, assignments, task status, weather); (C) runtime control state (clock, event queue, generation, PRNG streams); (D) component-private state (scheduler cache, provider internals) declared and checkpointable; (E) derived read-only metrics, traces and UI projections. B has **one** writer; C is Harness-owned; D is writable only by its owning component and must not contain an alternate authoritative copy of B; E never feeds back by hidden mutation.

## 2. Write permissions

| Actor | Read permission | Write permission |
|---|---|---|
| RunController / StateStore | A-D through scoped interfaces | Commit validated B; manage C |
| DataProvider / SpatialProvider | Frozen A, authorized B read view | Initialization proposals only, no live B writes |
| EventProvider | Clock, subscribed read view | Propose event envelopes, scoped B patches through commands |
| Scheduler | Read-only domain observation | Propose DispatchCommand, not direct task assignment |
| DynamicsModel | Authorized B read view and interval | Propose bounded B Delta / service events; never update shared state directly |
| MetricProvider | Committed B snapshot + trace | Derived E only, no commands or B writes |
| UI / HTTP / batch runner | Snapshot/result/progress | Submit validated external commands into C pending queue |
| LegacyEnvironmentAdapter | Controlled legacy Environment object | Exclusive opaque writer inside legacy step; compatibility mode only |

No component can request a raw StateStore mutable reference, inject arbitrary object attributes, mutate identifiers, bypass resource constraints or modify another component's private cache.

## 3. ChangeSet / transactional boundary

Minimum ChangeSet: run_id, generation, base_revision, producer_id, phase, ordered operations, emitted events, expected entity versions and provenance. Operations specify stable entity ID, typed field/semantic command, before-version, new value, units and reason. Validate in this order: generation and revision; component capability and allowed fields; references exist and type match; units and finite numbers; physical/domain invariants delegated to ARCH-01 schema/model; capacity/exclusivity constraints; cross-command conflict detection; event schedule validity. If any hard validation fails, reject the whole **atomic execution boundary** and preserve previous committed state and queue/RNG cursor. The next state is published only after successful validation; metrics/observers see either old or new revision.

Ordering: propose -> canonical sort -> validate and stage all ordered phases in provisional snapshots -> merge non-conflicting changes -> single atomic boundary commit -> increment revision -> publish events and snapshot -> observability. Multiple writers cannot independently commit. Conflicting writes to the same field are rejected by default (STATE_CONFLICT), not resolved by last-writer-wins; a domain reducer can be explicitly registered and versioned. A failed boundary transaction never increments sim_time/revision; retry requires an explicit deterministic failure rule.

## 4. Dispatch and physical correctness

Dispatch intent is validated for known task, drone, workload/capacity and no contradictory assignments. Assignment is committed before motion. Completion is driven by the DynamicsModel's **service completion event**, not UI coordinate proximity. The concrete meaning of delivery and recharge remains with domain models. Do not duplicate the canonical task lifecycle as UI projections. Snapshot always supplies state revision and time, preventing stale observation reuse.

## 5. Checkpoints, caching and concurrency

Checkpoint barrier captures B, C, declared D state and pinned A digest. Restore rejects incompatible schema, component signatures, run generations and dangling references; resource caches may be reconstructed if semantically pure and keyed by resource hash. A cache must not influence deterministic outcomes through iteration order or stale geometry. Only one boundary executor may commit per run; multiple readers receive immutable snapshots. Multirun parallelism is possible with run-specific scopes and no module-level mutable randomness.

## 6. Legacy reconciliation and acceptance

Today, frontend/environment.py:1033-1286 mutates Drone objects, assignments, task pools and metrics directly; console/sim_session.py:441-547 serializes dynamic __dict__ and module-global RNG. The legacy adapter may hold an **exclusive lock** and snapshot/output after a complete env.step; it cannot advertise atomic rollback, cross-run isolation or per-operation ChangeSet until separately proven. Document compatibility as LEGACY_OPAQUE_STEP.

Acceptance: invalid overweight dispatch leaves revision unchanged; simultaneous conflicting dispatches have deterministic rejection; Metrics cannot modify battery; injection at a barrier creates a new revision and updated observation; checkpoint restore reproduces event ordering; running two worlds cannot share task state.

ARCH-01 must specify mutable schema and reference invariants; ARCH-03 must declare provider read/write capability and checkpoint format; ARCH-04 must design copying/commit adapters for legacy before asserting H-02/H-03 compliance.
