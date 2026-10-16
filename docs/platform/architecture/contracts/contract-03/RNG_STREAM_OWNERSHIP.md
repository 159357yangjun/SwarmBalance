# CONTRACT-03 — RNG stream ownership and lifecycle

> PROPOSED v1 / B04 / design-only. Read with EXPERIMENT_SEED_CONTRACT.md. This does not redefine the ARCH-02 clock, event phases, or atomic boundary. No executable implementation is asserted.

## 1. Authority and isolation

**EXP-01** resolves and freezes ExperimentSeedPlan, replication keys, exposure group and per-cell effective master_seed. **ARCH-02 Harness** validates the FrozenRunSpec plan binding; creates, isolates and checkpoints named stream handles/counters for each RunScope/generation; enforces rollback. **ARCH-01 Scenario** stores default seed, immutable event recipe and input data. **ARCH-03 providers** declare their stream requests and may only consume scoped handles authorized by Harness; no global Python/NumPy/OS RNG. **ARCH-04 legacy bridge** runs each legacy Run in a separate process; never advertises new scoped-RNG properties on unmodified legacy code.

A stream descriptor MUST include: contract version, namespace, stable owner_id, stream_name, stochastic-process classification, source/implementation manifest digest, pairing/exposure_group scope if applicable, draw-address schema, PRNG/KDF and distribution algorithm/version, numeric environment profile, persistence policy, and checkpoint requirement. Stream registry is frozen at assembly: unknown or duplicate producer names, namespace escape or manifest mismatch fail before the Run begins. Stable owner IDs are manifest identities, not memory addresses or worker scheduling indices.

## 2. Ownership matrix

| Stream | Scope and owner | Addressing/consumption | Shared across algorithm A/B? | Re-key events |
|---|---|---|---|---|
| exogenous.demand.arrival | ExposureGroup; Scenario demand generator / EventProvider capability | Precomputed external candidate calendar or keyed (source, fixed slot, ordinal) | YES if same frozen demand mechanism and tape digest | source dataset, arrival law, horizon interpretation, transformation version change |
| exogenous.demand.attributes | ExposureGroup; demand generator | keyed stable task event_id and attribute name; no scheduler conditional draws | YES if common initial/external workload | payload model / distribution / entity schema change |
| exogenous.weather | ExposureGroup; Weather/EventProvider | fixed field grid/time cell and quantity OR immutable weather tape | YES if same external weather source + semantics | weather manifest, interpolation, units/sign/timing change |
| exogenous.vehicle.failure | ExposureGroup; failure EventProvider | static equipment ID + exogenous hazard calendar/slot | YES if independent exogenous hazard and same assets | fleet identity, hazard input/process change |
| exogenous.initial_state | ExposureGroup; Scenario materializer | stable static entity ID + initial property | YES if initial setup genuinely controlled | World/Scenario/initial distribution change |
| scheduler.search | RunPrivate; Scheduler component | algorithm-owned stable search operator/iteration slots, or checkpointed sequential consumption | NO; different algorithm/manifest yields different stream | Scheduler implementation/config digest change |
| scheduler.tie_break | RunPrivate; Scheduler component | decision identity + canonical candidate IDs or private cursor | NO; do not conflate common disturbances with policy randomness | Scheduler version or policy change |
| dynamics.process_noise | RunPrivate; DynamicsModel | model-specific state/interval address or checkpoint cursor | NO by default | ModelManifest/implementation/parameter/stream schema change |
| dynamics.state_dependent_failure | RunPrivate or explicitly coupled latent process; DynamicsModel | conditional on frozen state/trajectory; record exposure divergence | NOT identical realized failures automatically | causal model/hazard law or component manifest change |
| spatial.stochastic_routing | RunPrivate; SpatialProvider (if declared) | query identity / provider private cursor | NO unless same precomputed external immutable network realization | spatial/model/cache semantics change |
| metric.observe | No randomness by default; MetricProvider | post-commit committed frame only | N/A | unexpected RNG consumption => reject or explicitly version |
| analysis.bootstrap | Analysis-only; Experiment analysis service | analysis_plan digest, method and replicate index | never reuses RunScope | analysis method/data-set digest/definition change |

External source and RunPrivate must be different namespaces, with separate per-Run handles. A common external seed **does not** authorize concurrent sharing of one mutable object. A plugin may not draw directly from ExperimentPlan or mutate the external tape.

## 3. Deterministic consumption rules

1. Exogenous input generation must not depend on the Scheduler branch path: materialize before dispatch or use counter/key-addressed opportunities and fixed window support. Freeze a source digest, generated tape digest, field/units, timestamps and stable event IDs. Two treatments are CRN-paired only if these external signatures agree and any differences in *realized* event application are clearly due to changed state/availability rather than RNG drift.
2. Use typed length-prefixed canonical encodings for derivation input; include version tags and stable namespace separators. A variable number of calls by one component MUST NOT shift another component's stream. The private full RunSpec digest is permitted; the shared exogenous key MUST exclude full treatment spec, attempt_id, worker index and Scheduler ID. Freeze bit generator, distribution-transform methods, counters and test vectors before implementing.
3. Stream draw order is deterministic within owner: stable sort by entity/event identity, never dict hash iteration or async completion order. Consumer that cannot guarantee an ordered draw contract MUST either pre-materialize an immutable input tape or mark strict reproducibility unsupported.
4. Each event's random payload is generated once per logical event identity, then reused on replay; never draw again when delivery retries. Distinguish *event sampled*, *event accepted*, *event applied*, *event rejected*; the three latter states are domain/event ownership outside this RNG spec.
5. Unused draws are not "consumed" just to force fake cross-algorithm equality. Frozen latent exogenous outcomes may be identical while observed effects differ because treatments differ in state; record realized exposure and causal mechanism.
6. ModelManifest replacement triggers a new run-private stream whenever it affects implementation/config/PRNG contract. Do NOT perturb unrelated exogenous streams unless their producing model/input distribution/time mapping changes.
7. Component-private state and RNG cursor are within checkpoint/transaction agreement with ARCH-02/03. This proposal requests that guarantee; it does not assign internal phase timing, commit count or clock representation.

## 4. Retry / checkpoint / concurrency ownership

| Transition | Seed and RNG rule | Counting/evidence rule |
|---|---|---|
| New replication key | new exposure allocation by ExperimentSeedPlan; new private RunScope | one additional independent design cell |
| New treatment for same pairing group | identical immutable external tape/stream binding; treatment-private keys | pair by replication key, not execution index |
| Attempt retry of same cell | same FrozenRunSpec + seed + external tape; fresh isolated state or verified compatible checkpoint; no attempt_id in key | keep failed attempt, select at most one eligible outcome per cell |
| Precommit failure or transactional re-execution | discard staged RNG draws and restore B/C/D state/cursors through ARCH-02; if rollback impossible, fail closed | do not claim successful same-boundary retry |
| Postcommit metrics/export failure | committed world/RNG positions remain; re-export artifact idempotently | partial evidence flag, no resimulation to manufacture a second observation |
| Resume checkpoint | require exact run spec/source/code/component/PRNG/numeric profile + queue/RNG/private-state snapshot compatibility | emit resume attempt / lineage, no new independent sample |
| RESET generation | regenerate RunScope from explicit same/new resolved seed and clean components; no stale cursor | reset not a new replicate unless new plan cell |
| Parallel run and retries | separate RNG contexts, independent worker/output artifacts; only immutable data/tapes may be shared | worker order cannot change seeds or denominator |
| Legacy direct/harness | one subprocess per run; config env var before imports, no in-process interleaving | declare LEGACY_OPAQUE_STEP; cannot claim strict transactional replay |

Crash after result persistence before acknowledgment: use durable idempotency key (plan_digest, treatment_id, replicate_key, frozen_run_spec_digest) and attempt_id + artifact digest. Atomic finalize/selection requires an idempotent compare-and-set or equivalent journal; never append second "successful replication" after blind retry. A changed spec is a new plan cell. Failed/cancelled/excluded attempts remain visible with reasons and predeclared inclusion/exclusion policy.

## 5. Trace and audit shape (logical, non-implementation)

~~~yaml
run_rng_ledger:
  contract_version: "proposed-1"
  logical_cell_key: "<digest>"
  run_id: "<stable run identity>"
  generation: 1
  attempt_id: "<execution attempt>"
  seed_source: experiment_plan
  effective_master_seed: "<uint64>"
  seed_plan_digest: "sha256:<real digest>"
  exogenous_exposure_ref: "exposure:<group>@<version>"
  source_tape_digest: "sha256:<real digest>"
  stream_states:
    - stream_id: "exogenous.weather"
      owner_id: "weather-provider:<manifest-id>"
      namespace: "exo"
      generator_version: "<pinned>"
      draw_address_schema: "cell/time/variable@v1"
      draw_count: 0
      cursor_or_counter_digest: "<pinned hash>"
    - stream_id: "scheduler.search"
      owner_id: "scheduler:<manifest-id>"
      namespace: "private"
      generator_version: "<pinned>"
      draw_count: 37
      cursor_or_counter_digest: "<pinned hash>"
  committed_world_digest: "sha256:<real digest>"
  event_trace_digest: "sha256:<real digest>"
  lifecycle_state: "<SUCCEEDED/FAILED/CANCELLED/...>"
  evidence_completeness: "<complete/partial>"
~~~

Illustrative values above are not results. Logs must distinguish RNG **key identity** from mutable **draw cursor**, and record at least stream start/end positions, first divergence address, distribution and external tape digests. Avoid storing raw secrets (seeds here are reproducibility material, not cryptographic authorization tokens). R3 full replay requires enough immutable bytes or generator vectors to recreate all draws, otherwise claim R2/R1 only if their own conditions hold.

## 6. Change impact matrix

| Change | Shared exogenous | Scheduler private | Dynamics private | Pairing/comparison action |
|---|---|---|---|---|
| Scheduler only | preserve if same source/tape | **new** | new key possible under full RunSpec digest even if model unchanged; disclose this | paired exposure valid, not necessarily identical outcomes |
| DynamicsModel only | preserve **only if not its generating source and time/units law unchanged** | new possible due to full RunSpec digest | **new** | describe model confounding; revalidate intended comparison |
| Weather generator manifest | **new weather exposure** | new via RunSpec | new via RunSpec | old/new weather not CRN-paired |
| Scenario scheduled external event recipe | new affected exposure tape | new via RunSpec | new via RunSpec | pair policy recomputed |
| Worker count/order/attempt ID | preserve | preserve logical keys | preserve logical keys | no extra replicate |
| Metric implementation only | preserve | preserve logical keys for replay of same frozen RunSpec, unless metric is modeled input (prohibited in normal mode) | preserve | analyze with new MetricDefinition/provenance; raw Run immutable |
| Frozen dependency/runtime profile | input tape may be preserved, byte replay needs requalification | may change effective output without intended seed change | same | replay level downgraded pending evidence |

With private keys that include full RunSpec digest, any changed model or algorithm spec can cause *all* private stream keys to re-key; this is conservative and intentional. If preserving independent private component draws across unrelated changes is desired, introduce an **explicit versioned alternate policy** after cross-team approval, rather than silently relaxing the digest.

## 7. Mandatory downstream sign-off

ARCH-02 validates RNGScope create/fence/restore and worker isolation; ARCH-03 approves component/private checkpoint and stream requests; EXP-01 approves cell identity and attempt selection; ARCH-01 approves Scenario seed and external event materialization; ARCH-04 confirms legacy boundary. All changes require an independent reviewer and master ADR. No new time or event API is defined in this document. Refer to REPRODUCIBILITY_TEST_CASES.md for positive and adversarial checks.


## 8. C03/C04 owner-approved *candidate* byte profiles and review outcome

AI-C read AI-D PR #57 @ `027fd78589229db3d2308ced5365b7a780703805` (especially `LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md`) and **accepts LP4 / HKDF-HMAC-SHA256 as a mathematically consistent proposed byte rule**. Independently recomputed PR #57 G01–G13 using Python stdlib `hashlib/hmac/struct`: **13/13 exact equality**. This is math-fixture verification, not Run/RNG/CI verification. Cross-team approval of production API is still pending. The exact derivation, full-spec serialization and normative interpretation are in `EXPERIMENT_SEED_CONTRACT.md §9`.

Owner/namespace rules with explicit byte input fields:

| Namespace / role | Seed root | LP4 info (following `SB-RNG-v1`) | Invalid dependency |
|---|---|---|---|
| `run-master` | `seed_plan_root` | `run-master,experiment_definition_digest,treatment_id,replicate_key,v1` | plan digest (avoids Plan/Spec cycle), attempt, worker |
| `exo` | `seed_plan_root` | `exo,pairing_group_id,replicate_key,scenario_input_digest,exogenous_source_digest,stream_name,stream_schema_version` | treatment, whole spec, run_id, attempt_id, worker |
| `private` | resolved `master_seed` | `private,frozen_run_spec_digest,component_id,component_manifest_digest,stream_name,stream_schema_version` | attempt_id, generation, worker |
| `standalone-exo` | resolved standalone master | `standalone-exo,scenario_digest,source_digest,stream_name,stream_schema_version` | worker/attempt |

Each stream binding must lock `stream_contract_version`, `bit_generator`, `bit_generator_impl_digest`, `distribution_id`, `sampler_algorithm_version`, `transform_version`, `draw_address_schema`, `numeric_profile_digest`, `source_manifest_digest`, `checkpoint_policy`; reject `RNG_VERSION_UNPINNED` if any required field absent. No silent generic `random() / numpy.random` fallback.

Versioned **base uniform primitive** `C03-INDEXED-HMAC-U53-v1`: the external keyed `HMAC-SHA256(stream_key,LP4("SB-DRAW-v1",source_id,slot_id,ordinal_id))` yields an unsigned BE64 from the first 8 digest bytes, then `uniform53 = (draw_u64 >> 11) / 2**53`. Index tuple is stable, unique and independent of Scheduler control flow; duplicate draw addresses with different intended opportunities => `RNG_DRAW_ADDRESS_COLLISION`. Uniform53 is the **only** sampler primitive specified by this profile. For demand Poisson arrival counts, inter-arrival exponentials, correlated weather, Gaussian/Weibull failure hazards, GA/PSO perturbations and model noise, freeze a distinct named distribution *and* exact bit-level sampling transformation with reference code/vector; otherwise **R3 disallowed** and research comparison must acknowledge limited evidence. Never infer stable sampling merely from identical PRNG names.

Numerical profile must explicitly pin integer endian and width, binary64 `roundTiesToEven` contract for U53 (and any additional sampler), float/decimal conversion and exceptional/denormal handling, Python runtime/NumPy/BLAS or alternative implementation digest, platform/CPU architecture, parallel reduction and event sort policy. Matching configuration labels without an observed full Run trace is not proof of R2/R3.

### 8.1 Run, attempt and replication are different

- `replicate_key`: planned **independent logical experimental unit**, fixed before execution. `pairing_group_id`: common external exposure source, not another statistical unit.
- `cell_key`: SHA256(LP4("SB-CELL-v1", plan_digest, treatment_id, replicate_key, frozen_run_spec_digest)). The plan triple maps to exactly one spec digest; changed spec => `SPEC_CHANGED_NOT_RETRY` and requires a revised plan.
- `attempt_id`: SHA256(LP4("SB-ATTEMPT-v1", cell_key, positive_decimal(attempt_ordinal))). `run_id`: SHA256(LP4("SB-RUN-v1", attempt_id)); thus **one attempt = one new RunRecord and run_id**, while two retries of the same cell keep shared seed/external input.
- `generation`: a lifecycle/reset/checkpoint generation within one attempt, not a new replicate. Manual Runs are not assigned artificial experiment cells.
- Crash recovery must query durable `(cell_key,ordinal)` and its artifact hash/terminal status **before** launching; a replayed message for the *same* ordinal returns the original attempt. Only verified failure/cancellation with no active unfenced worker and preregistered retry rule can allocate a new ordinal. UNKNOWN outcomes block with `ATTEMPT_OUTCOME_UNRESOLVED`. Durable unique constraints/fencing and versioned Batch snapshot selection permit at most one included attempt per cell, with all attempts visible.

### 8.2 Metric-only change: no hidden private-stream promise

Under the v1 strict private key that incorporates **whole semantic FrozenRunSpec digest**, newly rerunning a model with a changed locked metric definition can rekey *all private* streams. This supersedes any reading of §6 or §4 that an arbitrary metric-only RunSpec change necessarily preserves private stream state. Recomputing analysis from an **existing immutable** RunArtifact is different: no new Run RNG is drawn. An alternate `rng_execution_projection_digest` is a proposed V2 only, requiring joint ADR and updated vectors. Exogenous CRN bindings continue unchanged only when their independently frozen generator/tape contents and semantics match.
