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

Required **semantic FrozenRunSpec content**: immutable world/scenario/config/data/model/code and assembly digest refs; resolved seed source and master_seed; sorted stream descriptors (namespace, owner, KDF/PRNG/distribution versions, manifest digests and immutable exposure ref when shared); clock/time policy **digest supplied by ARCH-02**; deterministic numeric/environment profile; metric-definition digest locks; failure/retry policies; evidence-output requirement. **Do not hash** run_id, attempt_id, attempt_ordinal, generation, plan_digest, cell_key, worker/timestamps/status/trace or mutable attempt envelope into FrozenRunSpec: those are separate RunRecord/BatchRecord bindings. The full frozen semantic serialization is specified in §9 (SB-FRS-JCS-v1); store its digest once before planning and never derive it from a mutable post-run object.

For each exogenous stream, retain either immutable realized input/event tape with content digest and stable event IDs or sufficient generator identity + derivation/test-vector/profile proof to regenerate it. **Seed equality is insufficient**, because differing PRNG libraries, draw counts, event sampling order, variable distributions, entity iteration, clock interpretation or model-side consumption produce distinct disturbances.

Manifest changes:
- Scheduler implementation/config/manifest changes -> new treatment RunSpec and private Scheduler stream; frozen exogenous exposure stays identical **if** generation source, temporal semantics and source digest unchanged. Dynamics state/decisions may diverge afterward, which is expected.
- DynamicsModel or other ModelManifest implementation/parameters changes -> new RunSpec and model-private stream root. External demand/weather/failure tapes stay identical only if their source models, units, semantics and independent generation remain unchanged. Any external process supplied by the replaced model, or a changed input domain/interpolation/hazard law, requires new exposure digest/stream. Same sampled weather does NOT mean same aerodynamic effect.
- Exogenous source/dataset, scenario event recipe or time mapping changes -> new external exposure identity; pair validity reevaluated, do not imply CRN equality.
- MetricDefinition change -> reanalysis of already immutable raw Run artifacts needs only a new AnalysisRecord and never regenerates their RNG. However, **new execution under a changed locked MetricDefinition** changes full FrozenRunSpec digest and (under strict C03/C04 v1) can rekey all Run-private streams; see §9. Exogenous CRN remains separately pinned when its source is unaffected.
- Analysis resampling -> its own analysis seed, independent of all Run keys.
- Changing attempt number, parallel worker slot or wall-clock schedule NEVER changes logical Run seed or frozen exogenous exposure.

## 6. Run isolation, retry, checkpoint and failure

ExperimentRunner schedules distinct immutable FrozenRunSpec requests; ARCH-02 owns RunScope, ScopedRNGFactory, RNG positions, state/queue atomicity, generation, checkpoint and failure policy. Neither ExperimentPlan nor a Scheduler writes Run StateStore/clock/event queue. Components receive capabilities for named streams only; attempts to access other namespaces fail authorization. On reset a fresh generation reconstructs scopes from frozen keys and declared reset options; it never inherits the predecessor's mutable RNG cursors.

One **logical run cell** = (plan_digest, treatment_id, replicate_key, frozen_run_spec_digest), under identity schema `C03C04-IDENTITY-v1`; multiple **attempts** are different executions of that one cell. Enforce additional plan-level uniqueness of `(plan_digest,treatment_id,replicate_key)` -> exactly one spec digest: a changed spec under the same frozen plan is `SPEC_CHANGED_NOT_RETRY`, never a second independent cell. Attempt 1 failure is retained with error/terminal phase and partial evidence. Attempt 2 reuses the identical immutable spec, stream keys and external exposure; it begins from a clean generation or a validated transactional checkpoint. Only one explicitly selected successful attempt may contribute once to the intended cell. Never count attempt successes as independent replications; never discard failures from attrition reporting; follow preregistered replacement/exclusion policy. Changed spec or changed seed is a NEW cell/plan revision, not a retry.

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

## 9. C03 × C04 formal technical reconciliation (AI-C review of PR #57, 2026-10-16)

**Reviewed exact inputs:** CONTRACT-03 PR #56 @ \`0b038f29e7f1957bf93e4afd1e3a171d54e5b620\`; CONTRACT-04 PR #57 @ \`027fd78589229db3d2308ced5365b7a780703805\`, especially \`LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md\`, \`RUN_AND_METRIC_CONTRACT.md\` and \`RESULT_COMPARABILITY_TEST_CASES.md\`. This appendix supersedes ambiguous details in §2/§5–§6; earlier exploratory YAML is illustrative, **not** a conflicting production schema. Cross-group G0 remains HOLD until owners sign and implementation tests run.

### 9.1 Identity reconciliation — ACCEPT as C03 proposal, NOT cross-team freeze

\`\`\`text
identity_schema_version = "C03C04-IDENTITY-v1"
logical_cell_key = "sha256:" + lowercase_hex(
  SHA256(LP4("SB-CELL-v1", plan_digest, treatment_id,
              replicate_key, frozen_run_spec_digest)))
\`\`\`

A \`plan_digest\` is a full immutable ExperimentPlan digest. Exactly **one** \`frozen_run_spec_digest\` may bind each \`(plan_digest,treatment_id,replicate_key)\` inside that plan. Before acceptance, validate the plan's existing binding with an atomic unique index/transaction. A changed spec with the same triple MUST return \`SPEC_CHANGED_NOT_RETRY\` (retain both request and canonical existing binding as audit evidence); if legitimate, prepare a **new** immutable plan revision/digest. It is forbidden to quietly add a fifth independent replication or overwrite the old binding. There is no circular digest: derive the effective master seed from the ExperimentDefinition identity and seed root, freeze the full RunSpec first, then freeze the ExperimentPlan referencing all spec digests. The hashed FrozenRunSpec MUST NOT reference \`plan_digest\`.

Canonical terms: \`replicate_key\` is independent planned experimental unit, \`pairing_group_id\` represents common intended external exposure, \`run_id\` identifies one actual execution attempt, and \`attempt_id\` is the immutable retry/attempt identity (different from \`replicate_key\`). \`replication_id\` is a **legacy ingestion-only alias**, and must match \`replicate_key\` if both are provided, or fail \`REPLICATE_ALIAS_CONFLICT\`. \`attempt_ordinal\` is a canonical positive decimal string at identity-hash boundary (no leading zero); stored \`run_id\`/attempt attributes do not participate in the cell key or frozen RunSpec.

\`\`\`text
attempt_id = "sha256:" + hex(SHA256(LP4("SB-ATTEMPT-v1", cell_key, decimal_ordinal)))
run_id     = "sha256:" + hex(SHA256(LP4("SB-RUN-v1", attempt_id)))
\`\`\`

These IDs are content-addressed bookkeeping IDs, not authentication credentials. An independent standalone manual Run has \`cell_key=null\` and a separate request idempotency key rather than fictional experiment treatment/replicate identities.

### 9.2 Formal byte rule audit — ACCEPT LP4 and HKDF primitives

**LP4(s1..sn):** each string MUST already be valid Unicode NFC; encode UTF-8 with no BOM, prepend its byte length as unsigned 4-byte **big-endian**, concatenate in specified order. Exact tag, digest and stable ID text is case-sensitive; digests are \`sha256:\` + exactly 64 lowercase ASCII hex. Input to LP4 is strings only: null, unnormalized/non-NFC, implicit number/string conversion, leading/trailing whitespace for canonical identifiers, oversized length, or duplicate normalized identities => hard reject. \`uint64\` root seeds are encoded directly as **8-byte big-endian binary**, never as JSON IEEE-754 doubles; external JSON carries decimal strings. Ordinals use positive ASCII base-10 without leading zero.

**HKDF-HMAC-SHA256 v1 (verified candidate):**
\`\`\`text
IKM  = BE64(root_seed_uint64)
salt = UTF8("SwarmBalance/C03-HKDF-HMAC-SHA256-v1")
PRK  = HMAC-SHA256(salt, IKM)
info = LP4("SB-RNG-v1", domain, field_1, ..., field_n)
OKM  = HMAC-SHA256(PRK, info || 0x01)    // L=32, HKDF-Expand one block
\`\`\`

Four role-specific ordered sequences are **accepted exactly as proposed in PR #57**: \`run-master\` takes (experiment_definition_digest, treatment_id, replicate_key, "v1") under seed_plan_root and uses BE64(first 8 bytes); \`exo\` takes (pairing_group_id, replicate_key, scenario_input_digest, exogenous_source_digest, stream_name, stream_schema_version) under seed_plan_root; \`private\` takes (frozen_run_spec_digest, component_id, component_manifest_digest, stream_name, stream_schema_version) under effective_master_seed; \`standalone-exo\` takes (scenario_digest, source_digest, stream_name, stream_schema_version) under effective_master_seed. Prefixes/tags, order, digest encoding and domains are normative candidates, not reinterpretable labels. The CRN exo sequence MUST exclude treatment/spec/attempt/run/worker IDs. Each Run uses its own mutable RNG handle even when exogenous key bytes are equal.

Indexed primitive only: \`A=LP4("SB-DRAW-v1",source_id,slot_id,ordinal_id)\`; \`block=HMAC-SHA256(exogenous_key,A)\`; \`draw_u64=BE64(block[0:8])\`; \`uniform53=(draw_u64>>11)/2**53\`. The arithmetic is exact for the 53-bit integer conversion under the stated binary64 profile. This freezes **only** this indexed uniform draw primitive. It does **not** freeze Poisson/Gaussian/Weibull, correlated weather, GA/PSO operators, or an entire PRNG implementation. Unknown sampler/version => \`RNG_VERSION_UNPINNED\` and R3 unsupported.

**Independent math verification actually performed:** AI-C re-derived all synthetic PR #57 G01–G13 (13 of 13 exact matches) using Python stdlib \`hashlib\`, \`hmac\`, \`struct\` and independent LP4/KDF formulas, including G07/G08 BE64, G09=G09 for A/B, G10 unequal independent replicate, G11/G12 distinct private keys and G13 \`draw_u64=2483426286146144837\`, \`draw_u53=1212610491282297\`. PR #57's prior third-party report also records 13/13, but AI-C's review is a **new independent mathematical recalculation**, not an execution of SwarmBalance simulator, distribution samplers, parallel workers, CI, or R1/R2/R3 replay.

### 9.3 Complete FrozenRunSpec canonical serialization: \`SB-FRS-JCS-v1\` (AI-C added proposal)

PR #57's LP4 rules hash **identity fields**, but do not canonicalize the arbitrary full FrozenRunSpec JSON/YAML. C03 therefore proposes a separate, explicit profile that must be agreed with EXP-01/ARCH-02 before implementation:

1. Resolve references and seed allocations **before** serialization. The exact root JSON object has REQUIRED top-level keys \`schema_version\`, \`world\`, \`scenario\`, \`code\`, \`inputs\`, \`assembly\`, \`config\`, \`execution\`, \`seed\`, \`metrics\`, \`failure_policy\`, \`evidence_policy\`. Set \`schema_version="SB-FRS-JCS-v1"\`. Content-addressed sources include both stable semantic ref (if applicable) and cryptographic digest; resolve any config overrides into one immutable config digest. Each nested object is strictly schema-validated with no unknown fields or environment-dependent defaults.
2. Mandatory meanings: \`world={ref,digest}\`; \`scenario={ref,digest,seed_default_uint64}\`; \`code={digest}\` (engine/runtime code lock); \`inputs=[{id,digest}]\`; \`assembly={digest}\` (complete component/model/parameters and dependency graph); \`config={digest}\`; \`execution={clock_policy_digest,horizon_seconds,numeric_profile_digest}\` (ARCH-02 owns exact clock semantics); \`seed={source,master_seed_uint64,streams:[{name,exposure_ref?,source_digest,rng_profile,...versioned required sampler refs}]}\`; \`metrics={definition_digests:[...]}\`; \`failure_policy={digest}\`; \`evidence_policy={digest}\`. A real implementation MUST validate that these digests transitively cover **all** execution-affecting data, distributions, event recipes, model/capability parameters, input order, retry policy and runtime flags; a generic \`digest\` must not hide unresolved mutable content. Schema extensions require a **new** version and regression vectors.
3. All semantic integers including uint64 and durations/quantities are **canonical decimal strings**; numeric values carry explicit schema-prescribed units and a finite representable domain. Reject any raw JSON binary floating-point number, NaN/Inf, \`-0\`, \`+1\`, \`01\`, trailing decimal zeros or exponent aliases at ingestion to avoid byte ambiguity. Decimal canonical rule for signed finite nonnegative/negative quantities: \`0\` or \`-?[1-9][0-9]*(\\.[0-9]*[1-9])?\` (for fractional values below one allow \`0.[0-9]*[1-9]\`; \`-0\` rejected). Versioned typed schema determines units, nullability and normalization; booleans are real JSON booleans, not \`"true"\`. For missing semantic fields, reject; schema-optional fields have declared explicit null/omission rules, never arbitrary defaults.
4. All strings, keys and IDs MUST be Unicode NFC, valid scalar strings with no ill-formed surrogate code points; forbid non-canonical aliases and duplicate keys **before parsing**. Use RFC 8785 JSON Canonicalization Scheme (JCS) for UTF-8 no-BOM serialization, object key sort per JCS UTF-16 code units, no whitespace, no arbitrary escaping; array order is semantic and MUST be canonically arranged at schema assembly (inputs sorted by stable \`id\`, streams by \`name\`, component refs by fixed registry order, metric digests lexicographically). Reject duplicate sort IDs, unordered/set-derived lists, mutable paths, wall-clock data. Do not sort arbitrary arrays during the JSON serializer as that can change meaning.
5. \`frozen_run_spec_digest="sha256:" + hex_lower(SHA256(UTF8(JCS(validated semantic object))))\`. \`plan_digest\`, \`cell_key\`, \`frozen_run_spec_digest\` itself, \`run_id\`, \`attempt_id\`, ordinal, generation, worker host/PID, logs, cursor positions, status and wall timestamps are **not** part of the hashed semantic object. They live in binding/attempt/RunRecord envelope. If a metric lock changes, full spec digest changes for a **new** Run and its private RNG can rekey; for mere analysis of immutable existing artifacts, create a new AnalysisRecord without a Run. No spec/plan digest cycle permitted.
6. **Serializer-only synthetic fixture** (NOT a complete implementation or actual experiment): the exact ASCII JCS bytes for the object \`{"execution":{"horizon_seconds":"600"},"schema_version":"SB-FRS-JCS-v1","seed":{"master_seed_uint64":"9001"}}\` have SHA256 \`TBD\` until separately verified by a conforming JCS implementation. An actual complete-spec end-to-end Golden Vector, including digest validation and invalid cases, is a **required open acceptance gate**. No ad hoc \`json.dumps(sort_keys=True)\` alone can certify JCS for all Unicode/numeric edge cases.

**Identity math G01–G13 is valid independently of this not-yet-accepted spec serialization profile;** their \`SA/SB\` digests are synthetic fixture-label hashes, not digests from an actual valid FrozenRunSpec. Do not report E2E freeze/replay PASS.

### 9.4 Strict RNG/sampler and numeric environment locks

Every execution-ready RunSpec must additionally lock \`rng_profile_version\`, KDF/bit-generator name+implementation version/digest, each stream's distribution family plus algorithm/version and transform order, opportunity addressing schema, sampler parameters and type/unit, required numerical policy (IEEE-754 binary64 tie-to-even and explicitly tested exceptional/denormal policy), CPU architecture/endian, language runtime/version, dependency lock digest (e.g. Python/NumPy/BLAS), OS and deterministic parallel/ordering policy. A fixed seed plus vague \`numpy.default_rng\` or \`random.random\` is **insufficient**. The only concretely specified candidate base sampler here is \`C03-INDEXED-HMAC-U53-v1\`; all other distributions/algorithms require explicit individually versioned specifications and golden vectors **before** R3 claims, or are rejected for that reproducibility profile. Pinning environment is a necessary condition, never a blanket guarantee of cross-platform bit identity.

### 9.5 Crash/unknown attempt reconciliation and single-count contract

Before dispatch persist \`(plan_digest,treatment_id,replicate_key)->spec_digest\` UNIQUE, cell_key and reserved \`(cell_key, attempt_ordinal)\` UNIQUE with \`attempt_id\`, \`run_id\`, \`state=RESERVED\`, worker fencing token and immutable spec/seed/source refs. On re-delivery of the same ordinal/request idempotency key, **read the durable journal first**; if a run or verified terminal artifact already exists, return its IDs/records and NEVER re-execute as a new attempt. Journal states: RESERVED / RUNNING / SUCCEEDED / FAILED / CANCELLED / UNKNOWN, with immutable transitions and separate artifact hash/commit evidence.

On crash or acknowledgment loss: (a) query attempt by durable key, verify complete artifact digest, terminal/commit marker and run_id; (b) if terminal, return stored result; (c) if RUNNING/UNKNOWN, fence/resolve any still-live worker before new execution; verify last durable commit and any partial artifact, preserve UNKNOWN until adjudicated; (d) retry only after **confirmed** terminal failed/cancelled/tainted state and preregistered policy, allocate a **new ordinal** and linked RunRecord using same FrozenRunSpec and seed/tape; (e) if backend cannot establish exclusive ownership or durability, BLOCK and emit \`ATTEMPT_OUTCOME_UNRESOLVED\`, not optimistic rerun. Archive unsuccessful and unlaunched cells. Analysis references a pinned Batch snapshot/revision; selects at most one eligible attempt per cell according to preregistered policy; concurrent CAS/unique constraints prevent selecting two. Generation/checkpoint resume is not a new statistical replicate.

No implementation of durable store, fencing, C03/C04 RunRecord schema or ARCH-02 clock is claimed by this docs-only proposal. Proposed error codes: \`SPEC_CHANGED_NOT_RETRY\`, \`RUN_ATTEMPT_DUPLICATE\`, \`ATTEMPT_OUTCOME_UNRESOLVED\`, \`RETRY_INPUT_DRIFT\`, \`CYCLIC_SPEC_PLAN_DIGEST\`, \`ATTEMPT_FIELDS_IN_SPEC\`, \`IDENTITY_ENCODING_INVALID\`, \`RNG_VERSION_UNPINNED\`, \`FROZEN_SPEC_CONTENT_MISMATCH\`.

### 9.6 Technical disposition

- **PASS (limited)**: PR #57's G01–G13 **synthetic mathematical vector** recomputation, 13/13 exact values; LP4, HKDF, identity and indexed uniform primitive coherent as a byte-level proposal.
- **CONDITIONAL/PROPOSED**: \`C03C04-IDENTITY-v1\` and \`SB-FRS-JCS-v1\` are technically consistent candidates, but must be jointly signed by EXP-01/ARCH-02/ARCH-03 and coordinator. Exact complete FrozenRunSpec serializer/vector and rejection oracle need independent implementation verification.
- **NOT VERIFIED**: Gaussian/Poisson/failure hazard sampling, runtime bit generators, private component cursor restore, parallel Run isolation, crash-safe journal implementation, full experiment replay, CI, statistical inference or physical validation.
- **Remaining design decision**: metric-only full-spec digest changes rekey private streams for fresh Runs; reanalysis uses original artifacts. An alternative execution-only subdigest requires a new contract version and separate co-sign; no silent substitution.
