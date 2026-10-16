# CONTRACT-03 — ExperimentSeedPlan / Run RNG 契约

> Task: CONTRACT-03 / ARCH-05-R2 B04 / AI-C. Status: PROPOSED FOR JOINT REVIEW, not ACCEPTED, not implemented. Date: 2026-10-16.
> Scope: seed authority, pairing, frozen references, derivation, retries, comparability. This document does NOT freeze Harness clock, phase, boundary, or event-envelope API. No experiment/CI execution is claimed.

## 0. Pinned upstream evidence and change policy

| Source | Current reviewed PR HEAD (full SHA) | Referenced facts |
|---|---|---|
| #54 ARCH-05-R2 | 99bd0eb6b910d691d6d7776da0a5fd3f973f2997 | B04 P0; M18 DELTA, S03/S07 blocked; HOLD/NO-FREEZE |
| #52 EXP-01 | a966567b1a2a033f477c2847073cc11777a3afd2 | ExperimentPlan owns factors, seed plan and independent Run requests |
| #49 ARCH-02 | d155621aca66e3a80c388718093a452d17d71e10 | scoped RNG; original master_seed + full RunSpec digest + component_id + stream_name; rollback and Run isolation |
| #46 ARCH-01 | b5f05a70a3306f1799fcae2c3f342f3ed9ee0048 | immutable Scenario revision with seed; reproducible external events |
| #47 ARCH-03 | 68382c649393057ffbf5a14508ab1ff72d575b09 | run seed + component ID + stream; model/assembly manifest provenance |
| #50 ARCH-04 | c4c0c67111ead435062650c1ed776547c477e3e3 | legacy Python/NumPy process-global RNG, subprocess-per-run isolation |
| #51 Governance | f2df96bc609ee1e430ea6eff2456c4577347c300 | proposed registry/ADR, independent review and SHA handoff |

All seven PRs were Open/Draft when inspected. Base of these PRs: master @ 2ab60c69a806a22d7ba20353dee0571752a0e8e5. Upstream drafts are not approved ADRs. Recheck HEAD and relevant diffs before cross-sign or implementation; changed SHA invalidates affected assertions. Stable source entry points: PR #54 review/M18, #52 EXPERIMENT_SYSTEM.md and EXPERIMENT_CONTRACTS.md, #49 CLOCK_AND_EVENTS.md / FAILURE_CONTRACT.md / STATE_OWNERSHIP.md, #46 SCENARIO_MODEL.md, #47 COMPONENT_CONTRACTS.md / DATA_AND_MODEL_MANIFESTS.md, #50 COUPLING_ANALYSIS.md / BACKWARD_COMPATIBILITY.md, #51 HANDOFF_PROTOCOL.md.

## 1. Ownership and precedence (PROPOSED decision C03-01)

Three fields are NOT three interchangeable global random seeds.

1. **Scenario.seed** is an immutable recipe-level default and provenance input. It may seed a standalone Run only if neither a frozen experiment allocation nor an explicit standalone master seed exists. An event already fixed as explicit immutable data is not resampled just because a seed exists.
2. **ExperimentPlan.seed** (recommended field name: seed_plan_root) is the authority for an Experiment batch and its replication/pairing allocations. ExperimentDefinition revision and plan digest freeze this allocation before the first Run. An experiment Run MUST obtain its effective seed and exogenous stream bindings from the plan; Scenario.seed is recorded as overridden_default, not silently mixed into plan-derived streams.
3. **FrozenRunSpec.master_seed** is the final resolved effective seed consumed by an individual RunScope, not an independently editable competing experiment override. For a standalone run an explicit caller-supplied master_seed takes precedence over Scenario.seed. For an experiment, supplied Run master_seed MUST equal the seed the immutable plan assigned, or fail SEED_PLAN_CONFLICT. Never silently prefer a Run override over a plan.

Effective resolution: experiment-bound Run -> plan allocation (and verify Run field matches); otherwise explicit standalone Run seed -> Scenario.seed -> FAIL SEED_UNRESOLVED. No OS entropy/time default in a reproducibility-eligible Run. To choose a new seed, create a new immutable ExperimentPlan revision or a new standalone FrozenRunSpec, never mutate an in-flight one. Scenario.seed may still influence explicit Scenario-authored event data only when Scenario's own generation recipe declares it; such generated artifacts are materialized, digested and frozen before experimental pairing.

Example: Scenario.seed=101, experiment seed_plan_root=9001, replicate_key=r02, treatment=A/B. Both A and B record Scenario.seed=101 as the unused default. Each gets a plan-verified effective master_seed (possibly different), but BOTH bind the same demand/weather/fault exogenous stream identities for r02. An ad-hoc Run master_seed=101 is rejected for the experiment unless that is exactly the plan allocation. A standalone Run with no explicit seed resolves to 101.

## 2. ExperimentSeedPlan V1 proposed logical schema

~~~yaml
contract: ExperimentSeedPlan
version: proposed-1
experiment_ref: "experiment:<id>@<immutable_revision>"
experiment_plan_digest: "sha256:<real content digest>"
scenario_ref: "scenario:<id>@<revision>"
scenario_content_digest: "sha256:<real digest>"
scenario_seed_default: 101
seed_source: experiment_plan
seed_plan_root: 9001                       # uint64, illustrative ONLY
derivation_spec: "C03-HKDF-HMAC-SHA256-v1" # test vectors required before freeze
rng_engine_spec: "<algorithm/version/distribution adapters/numeric profile>"
pairing_policy: "CRN_EXOGENOUS_V1"
replications:
  - replicate_key: "r02"
    pairing_group_id: "p02"
    exogenous_exposure_ref: "exposure:p02@1"
    treatment_bindings: ["scheduler:A", "scheduler:B"]
streams:
  - name: "exogenous.demand.arrival"
    exposure_group: "p02"
    source_manifest_digest: "sha256:<real digest>"
    draw_address_policy: "indexed-by-stable-opportunity"
    distribution_spec_digest: "sha256:<real digest>"
  - name: "exogenous.weather"
    exposure_group: "p02"
    source_manifest_digest: "sha256:<real digest>"
    draw_address_policy: "indexed-by-fixed-time-cell"
  - name: "exogenous.vehicle.failure"
    exposure_group: "p02"
    source_manifest_digest: "sha256:<real digest>"
    draw_address_policy: "indexed-by-static-entity-and-slot"
run_bindings:
  - treatment_id: A
    replicate_key: r02
    master_seed: "<resolved uint64>"
    scheduler_manifest_digest: "sha256:<real digest>"
    exogenous_exposure_ref: "exposure:p02@1"
  - treatment_id: B
    replicate_key: r02
    master_seed: "<resolved uint64>"
    scheduler_manifest_digest: "sha256:<real digest>"
    exogenous_exposure_ref: "exposure:p02@1"
pre_registered_exclusions: "<explicit policy reference>"
~~~

The example is a **schema fixture**, not a real manifest with validated hashes or computed seeds. Production records MUST replace placeholders, lock canonical serialized bytes, include all relevant data/model versions, event-source semantics, external-file checksums, clock-policy reference (owned by ARCH-02), and a complete run assignment table. A replication key is stable experimental design identity; attempt_id and worker/process identity are NOT replication keys.

A pairing_group_id means the plan intends a controlled exogenous exposure. It is not evidence that realized exogenous events actually match. Separate an **exposure identity** from a **Run identity** and a **treatment identity**.

## 3. Derivation and no accidental resampling (PROPOSED decision C03-02)

Use a formally versioned domain-separated KDF, canonical typed UTF-8 field encoding with length prefixes (never Python hash(), repr(), filesystem iteration order or language-dependent object hashes). Proposed KDF name: C03-HKDF-HMAC-SHA256-v1; exact byte serialization, PRNG seeding width, sampling algorithms, and golden vectors are REQUIRED before an implementation can claim interoperable bitwise replay. Treat PRNG algorithm/version as mandatory FrozenRunSpec fields; no undocumented default. Derive independent root namespaces:

- **External shared exposure root:** KDF(plan_root, "exo", pairing_group_id, replicate_key, scenario_input_digest, exogenous_source_digest, stream_name, stream_schema_version). MUST NOT contain scheduler ID, scheduler parameters, treatment-specific full RunSpec digest, worker number, run_id, or attempt_id. Include a model/data identity here only when it genuinely defines that exogenous process; changing it creates a new exposure version.
- **Run-private root:** KDF(effective_master_seed, "private", frozen_run_spec_digest, component_id, component_manifest_or_implementation_digest, stream_name, stream_contract_version). In this namespace ARCH-02's full-spec-digest protection remains appropriate. Scheduler/Model changes intentionally alter these keys.
- **Standalone exogenous root:** KDF(effective_master_seed, "standalone-exo", frozen_scenario_digest, source_digest, stream_name, version); no cross-Run shared-exposure claim by default.

For state-independent external opportunity generation, use stable draw addresses rather than sequential draws conditioned on branch execution. E.g. demand arrival keyed by (source_id, replicate_key, fixed arrival slot or event ordinal), weather by (field_id, fixed spatial cell, time bin, quantity name), exogenous failure by (static equipment ID, fixed hazard slot). Each draw address is unique within stream, with documented collision rejection; distribution-transform version and numeric profile are pinned. For a point process, freeze the candidate arrival calendar/hazard realization *before* algorithms run, rather than letting a conditional consumption count determine arrivals. Common random numbers may be implemented by identical frozen event-trace artifact references rather than shared live RNG objects.

**Never use the overall treatment RunSpec digest inside a CRN exogenous key.** A/B RunSpec digests necessarily differ when Scheduler differs. Both Runs MUST have distinct private stream state even when their exogenous exposure refs are the same.

## 4. Common random numbers: allowed and forbidden

| Variable/process | CRN permitted? | Precondition |
|---|---|---|
| Externally generated task arrival times and initial task payloads | YES | same frozen demand recipe/input, horizon/semantic mapping and identical external candidate/event trace |
| Pre-sampled independent weather/wind field or time series | YES | model/source/interpolation, space/time coordinates and sign conventions identical; no scheduler feedback |
| Independent external equipment failure clocks/hazards | YES, conditional | static equipment identity and hazard process identical; pre-sampled exogenous failure calendar, not draws performed only after usage |
| Initial inventory/fleet state stochastic draw | YES, conditional | same World/Scenario and pre-materialized initial entity state |
| Scheduler tie-breaks, GA/PSO search/mutation, planner exploration | NO | treatment-private algorithm randomness; separate component-private namespaces |
| State-dependent battery/failure/repair risk or weather generated from action trajectories | NOT as identical realized outcomes | different state/action histories change exposure; may couple fixed underlying latent hazards by stable opportunity ID, disclose conditional divergence |
| Stochastic DynamicsModel internal noise | NOT automatically | only externally defined shared measurement/forcing may stay common; model-private noise changes with manifest/version |
| Metric bootstrap/resampling for analysis | NOT a Run stream | belongs to versioned AnalysisPlan and separate analysis-only RNG |

CRN design reduces some comparison variance only when meaningful paired exposure is demonstrably equivalent; it is not required for all studies, nor proof of fairness by seed equality. Manifest replacement that changes the stochastic law requires a new exposure identity and an explicit comparability decision, not a misleading identical label.

## 5. FrozenRunSpec linkage and manifests

Required per-run immutable fields: run_id; generation; experiment_ref optional; plan digest/ref optional; treatment_id; replicate_key and pairing_group_id optional; scenario revision/digest and seed default; seed_source; resolved master_seed; sorted stream descriptors (stream namespace, owner, KDF/PRNG/distribution versions, manifest digests, exogenous_exposure_ref if shared); exact component registry/assembly/model manifest digests; code revision; input content checksums; time/clock configuration **reference as provided by ARCH-02**; reproducibility numeric/environment profile; failure/retry policies; output evidence requirement. Store frozen spec digest after resolution and do not recalculate it from a post-run mutated object.

For each exogenous stream, retain either immutable realized input/event tape with content digest and stable event IDs or sufficient generator identity + derivation/test-vector/profile proof to regenerate it. **Seed equality is insufficient**, because differing PRNG libraries, draw counts, event sampling order, variable distributions, entity iteration, clock interpretation or model-side consumption produce distinct disturbances.

Manifest changes:
- Scheduler implementation/config/manifest changes -> new treatment RunSpec and private Scheduler stream; frozen exogenous exposure stays identical **if** generation source, temporal semantics and source digest unchanged. Dynamics state/decisions may diverge afterward, which is expected.
- DynamicsModel or other ModelManifest implementation/parameters changes -> new RunSpec and model-private stream root. External demand/weather/failure tapes stay identical only if their source models, units, semantics and independent generation remain unchanged. Any external process supplied by the replaced model, or a changed input domain/interpolation/hazard law, requires new exposure digest/stream. Same sampled weather does NOT mean same aerodynamic effect.
- Exogenous source/dataset, scenario event recipe or time mapping changes -> new external exposure identity; pair validity reevaluated, do not imply CRN equality.
- MetricDefinition change -> new analysis/comparison revision; does not consume or retroactively regenerate Run RNG.
- Analysis resampling -> its own analysis seed, independent of all Run keys.
- Changing attempt number, parallel worker slot or wall-clock schedule NEVER changes logical Run seed or frozen exogenous exposure.

## 6. Run isolation, retry, checkpoint and failure

ExperimentRunner schedules distinct immutable FrozenRunSpec requests; ARCH-02 owns RunScope, ScopedRNGFactory, RNG positions, state/queue atomicity, generation, checkpoint and failure policy. Neither ExperimentPlan nor a Scheduler writes Run StateStore/clock/event queue. Components receive capabilities for named streams only; attempts to access other namespaces fail authorization. On reset a fresh generation reconstructs scopes from frozen keys and declared reset options; it never inherits the predecessor's mutable RNG cursors.

One **logical run cell** = (experiment_plan_digest, treatment_id, replicate_key, frozen_run_spec_digest); multiple **attempts** are different executions of that one cell. Attempt 1 failure is retained with error/terminal phase and partial evidence. Attempt 2 reuses the identical immutable spec, stream keys and external exposure; it begins from a clean generation or a validated transactional checkpoint. Only one explicitly selected successful attempt may contribute once to the intended cell. Never count attempt successes as independent replications; never discard failures from attrition reporting; follow preregistered replacement/exclusion policy. Changed spec or changed seed is a NEW cell/plan revision, not a retry.

Precommit error: ARCH-02 must restore or discard staged clock/queue/RNG **and** component-private state as specified by ARCH-02/03 capability contract. If private state cannot be rolled back or call has untracked side effects, reject strict retry / mark failed or tainted; don't claim deterministic same-boundary retry. Postcommit metric/export failure: preserve committed world and RNG cursors; retry export only from immutable committed data, never redo simulation step. Checkpoint must pin source/spec digests, generation identity, B/C/D RNG states/counters, algorithm & sampling versions and evidence trace; incompatible restore => CHECKPOINT_INCOMPATIBLE. Do not assume ARCH-02's internal clock schema or settle B01/B03 here.

Parallel Runs: each must have independent memory, stream handles, cursors and output directories; shared immutable exogenous **bytes** allowed, shared mutable RNG instance forbidden. Worker scheduling/interleaving cannot enter seed derivation or event ordering. Legacy mode remains one subprocess per Run with config set before import, separate Python/NumPy globals and no concurrent in-process legacy sessions. Legacy Python/NumPy global-state checkpoints are NOT portable new-Harness snapshots (see #50).

## 7. Three distinct reproducibility claims (PROPOSED decision C03-03)

| Level | Name / what may be claimed | Necessary evidence; NOT implied |
|---|---|---|
| R3 | **Complete replay (full replay)**: reconstruct the same committed event/state/decision trace and scoped RNG positions bit-for-bit within an explicitly pinned execution environment/profile. | exact frozen artifacts, implementation/PRNG/sampling/numeric and environment versions, checkpoints/tapes, canonical event ordering, trace/state digest equality; diagnostic timestamps/path names excluded from semantic digest. Does NOT guarantee cross-machine bit equivalence without proven portable numeric profile. |
| R2 | **Same-input determinism**: under the same frozen specification and declared numeric tolerance/profile, matching domain outcomes or first explainable divergence; bitwise trace is not required. | input/implementation digests, repeat attempts, deterministic scheduling/metrics, fieldwise tolerances fixed in advance and first divergence; a merely matching seed is not sufficient. |
| R1 | **Statistical comparability**: separate stochastic Runs/treatments can be compared under preregistered design, controls, missing/failure policy, sample/metric definitions and uncertainty analysis. | defined populations, replication keys, comparable manifests/metrics/windows/denominators, exposure equivalence for claimed CRN pairs, attempts/attrition accounted, analysis methodology. R1 can hold when R2/R3 between different treatments does NOT. |

R3 does not establish a realistic physical model. R2 does not establish unbiased treatment comparison. R1 does not establish algorithm superiority or external validation. VVE-01 owns reality Validation/UQ claim review, not this RNG contract.

## 8. Arbitration / acceptance gate

Proposed error identifiers: SEED_UNRESOLVED, SEED_PLAN_CONFLICT, STREAM_OWNER_CONFLICT, STREAM_SCHEMA_MISMATCH, CRN_EXPOSURE_MISMATCH, RNG_VERSION_UNPINNED, RNG_GLOBAL_STATE_FORBIDDEN, RNG_DRAW_ADDRESS_COLLISION, RNG_RESTORE_INCOMPATIBLE, RUN_ATTEMPT_DUPLICATE, NOT_COMPARABLE. Report run/cell/component/stream IDs, expected/observed digests and first divergence; never silently regenerate or substitute seed/model.

**Must be co-signed before acceptance:** EXP-01 (ExperimentSeedPlan schema and seed priority), ARCH-02 (RunScope RNG injection/checkpoint/rollback, preserving its separate clock/event API ownership), ARCH-01 (Scenario.seed and event recipe semantics), ARCH-03 (component-specific stream ownership and manifests), ARCH-04 (legacy worker isolation), plus independent ARCH-05 delta review and master coordinator ADR decision. B04 remains OPEN until signatures, canonical derivation vectors, CRN equivalence tests and immutable manifest refs are supplied.

Linked cases: RNG_STREAM_OWNERSHIP.md and REPRODUCIBILITY_TEST_CASES.md. Existing study outputs and legacy comparison gates are untouched.