# CONTRACT-03 × CONTRACT-04 — 统一逻辑实验单元、重试身份和 RNG 派生提案

> **PROPOSED / DESIGN-ONLY / NOT FROZEN**，CONTRACT-04 AI-D 负责接口交汇；CONTRACT-03 AI-C/EXP-01/ARCH-02/ARCH-03 需共同会签。本文件不编辑 PR #56，不单方面改变 C03 已提议的职责边界，不覆盖 B01/B02/B03。
>
> 复审输入：#56 CONTRACT-03 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`；#57 CONTRACT-04 原 HEAD `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118`；#60 CONTRACT-05 `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955`；上游 #52 `a966567b1a2a033f477c2847073cc11777a3afd2`、#49 `d155621aca66e3a80c388718093a452d17d71e10`、#54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`。共同原始 base `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`。
>
> 解决 #60 D05/D06：C03 使用四元组 `(plan_digest,treatment_id,replicate_key,frozen_run_spec_digest)`；C04 原先使用三元组且 `replication_id` 命名不同，并在 FrozenRunSpec 示例中放置 `run_id`，导致 retry 改变 digest。本提案固定唯一规范四元组，`replication_id` 仅为迁移别名；`run_id` 退出被哈希的 FrozenRunSpec 语义内容。

## 1. 唯一身份 Schema（schema_id = `C03C04-IDENTITY-v1`）

```yaml
identity_schema_version: "C03C04-IDENTITY-v1"
identity_profile: "SB-ID-LP4-SHA256-v1"
experiment:
  experiment_definition_digest: "sha256:<64hex>"
  plan_digest: "sha256:<64hex>"            # frozen complete plan, references spec digests
logical_cell:
  treatment_id: "A"                        # EXACT spelling; stable and unique within plan
  replicate_key: "r02"                     # one independently allocated unit; NOT attempt/generation
  frozen_run_spec_digest: "sha256:<64hex>" # exact executable input spec, never per-attempt envelope
  cell_key: "sha256:<64hex>"                # SHA256(LP4(tag,plan,treatment,replicate,spec))
attempt:
  attempt_ordinal: 1                       # strictly positive; monotonically allocated per cell
  attempt_id: "sha256:<64hex>"              # SHA256(LP4(tag,cell_key,decimal_ordinal))
  run_id: "sha256:<64hex>"                  # proposed durable deterministic Run ID derived from attempt_id
  retry_of_attempt_id: null                # only ordinal=1 can omit
  record_owner: "ARCH-02-Harness"
  generation: 0                            # lifecycle/reset generation, NOT a new replicate
  run_record_revision: 1                   # append-only writer revision, NOT key material
exposure_binding:
  pairing_group_id: "p02"
  exogenous_exposure_ref: "immutable-external-tape-or-generator-manifest-ref"
  seed_plan_ref: "sha256:<64hex>"
  effective_master_seed_uint64: "5928125456373989572" # JSON decimal STRING; no float coercion
```

**Normative identity projection**: `logical_cell_tuple=(plan_digest,treatment_id,replicate_key,frozen_run_spec_digest)`. Only this exact tuple is idempotency/unique-cell identity. `replication_id` from old C04 is allowed **only on legacy ingestion** as a source alias for `replicate_key`; when both supplied and unequal => `REPLICATE_ALIAS_CONFLICT`. Canonical objects/output and RNG info contain only `replicate_key`. Changing spec digest (including seed/model/code/failure/metric lock) creates a **different cell**, never a retry even if the other 3 fields remain equal. A new plan digest creates a new cell. `pairing_group_id` links two different cells with the *same intended external realization*; it is not a cell or replication identity.

**Additional P0-03 Plan invariant:** inside a *single* immutable ExperimentPlan, the pair `(treatment_id,replicate_key)` MUST bind **one and only one** `frozen_run_spec_digest`; different spec digest at the same `plan_digest+treatment_id+replicate_key` is `PLAN_CELL_SPEC_CONFLICT`, **not** a new cell in that plan. Freeze a new ExperimentPlan with a new digest before changing the spec; preserve old failed/cancelled attempts and compare gates. The earlier phrase "changed spec = new cell" applies ONLY after a new Plan revision. `replicate_key` remains independent replication design identity, `attempt_ordinal/attempt_id/run_id` are only execution-attempt identities.

The plan may bind spec digests but **the hashed FrozenRunSpec must NOT include plan_digest/cell_key/run_id/attempt_id/ordinal/generation/retry_of/status/worker/timestamps/logs**, otherwise the Plan ↔ Spec digest graph cycles and retry breaks idempotency. A FrozenRunSpec is frozen execution semantics (world, scenario, exact model/component/data/code/config, clock, seed allocation, RNG descriptors, metric definitions and failure policy); its canonical content hash excludes `spec_digest` itself and all **attempt binding/envelope** fields. `plan_digest` lives in the ExperimentPlan and RunRecord binding, not within the spec content. Pre-freeze failures may have no spec digest and must remain failed RunRecord audit entries without pretending the cell key was validly finalized.

**Durable attempt rule:** `(cell_key, attempt_ordinal)` is a unique immutable allocation. Retry after *known* failed/cancelled/tainted attempt gets ordinal+1 and a fresh RunRecord/run_id; may reuse only the **same FrozenRunSpec/external tape/master_seed** and a clean scope or verified valid checkpoint. A command resent after crash/ack loss with the *same* ordinal must return the pre-existing attempt/run_id (idempotent lookup), **not start a second execution**. If prior outcome is UNKNOWN, reconcile append-only durable ledger/artifact hash first; never blind-replay and double-count. `run_id = SHA256(LP4("SB-RUN-v1",attempt_id))` is a candidate stable internal ID, not an authorization secret. A user-supplied/manual Run without ExperimentPlan has `cell_key=null`, a request-scoped idempotency key and unique RunRecord; it must not invent fake treatment/replicate entries.

Under BatchRecord: preserve `{cell_key, planned? , attempts:[{ordinal,attempt_id,run_id,status,artifact_digest,retry_of}], selected_attempt_id?, selection_policy_digest}` for *all* planned cells, including NOT_DISPATCHED. At most one attempt per cell contributes to a particular preregistered estimator; failure attrition remains visible. Generation / checkpoint resume is a lifecycle concept and cannot silently add an independent statistical sample.

## 2. Canonical byte encoding and identity hash

`LP4(s1,...,sn)`: for each ordered field, require Unicode NFC; UTF-8 encode (no BOM), prepend a **4-byte unsigned big-endian** byte length, and concatenate. Strings only; forbid `null`/numeric coercion at this layer; require exact ASCII IDs for fixed tags, lowercase `sha256:` with exactly 64 lowercase hex for digests; `treatment_id/replicate_key/owner/stream` must be NFC, nonblank, stable and unambiguous. Values `uint64` encoded as **8-byte unsigned big-endian** only in KDF root input; all ordinal fields in LP4 use canonical no-leading-zero positive ASCII decimals. Reject overflow and `-0`, `+1`, `01`, whitespace. Reject duplicate canonical keys (also Unicode normalization aliases) and ambiguous producer/stream names. This is a *logical* byte format: manifests may be YAML/JSON but hash derivation uses the specified ordered fields, not their textual serialization.

Identity hashes:

```text
cell_key   = "sha256:" + HEX(SHA256(LP4("SB-CELL-v1", plan_digest, treatment_id, replicate_key, frozen_run_spec_digest)))
attempt_id = "sha256:" + HEX(SHA256(LP4("SB-ATTEMPT-v1", cell_key, decimal(attempt_ordinal))))
run_id     = "sha256:" + HEX(SHA256(LP4("SB-RUN-v1", attempt_id)))
```

`frozen_run_spec_digest` must use the precise full object serialization `SB-FROZEN-RUN-SPEC-v1 + SB-CJSON-1` now proposed in [FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md](FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md) §2, including synthetic **SPEC-01/02** vectors; ExperimentPlan must separately define its complete canonicalization and pass one-plan uniqueness checks before claiming final plan_digest. The **G01–G13** historical identity fixtures deliberately use synthetic SHA-256 label digests (not complete SPEC-01 hash), so the independent test layers must not conflate them. Both contracts remain PROPOSED pending AI-C/EXP-01 co-signature.

## 3. RNG 派生版本（`C03-HKDF-HMAC-SHA256-v1` 候选）

One explicit **candidate** byte-level concretization of C03's proposed KDF. Must be signed by AI-C/EXP-01/ARCH-02 before product use; no claims of PRNG/distribution portability from key material alone.

```text
HKDF-Extract:
  ikm  = BE64(root_seed_uint64)     # 8 bytes, non-negative <=2^64-1
  salt = UTF8("SwarmBalance/C03-HKDF-HMAC-SHA256-v1")
  prk  = HMAC-SHA256(salt, ikm)
HKDF-Expand, L=32:
  info = LP4("SB-RNG-v1", domain, field_1, ..., field_n)
  key  = HMAC-SHA256(prk, info || 0x01)   # RFC 5869 single block
```

Exactly one namespace per role; all fields ordered and strings with explicit version suffix:
- **plan master assignment**: `KDF(seed_plan_root,"run-master",experiment_definition_digest,treatment_id,replicate_key,"v1")`; `effective_master_seed = BE64(first_8_bytes(key))`. This allocation is frozen in the Plan **before** plan_digest is computed, avoiding a digest cycle. Scenario.seed remains recorded as overridden default for Experiment Runs. Any Run-provided master seed unequal to allocation is `SEED_PLAN_CONFLICT`. Standalone priority: explicit master seed > Scenario.seed > `SEED_UNRESOLVED`.
- **shared exogenous**: `KDF(seed_plan_root,"exo",pairing_group_id,replicate_key,scenario_input_digest,exogenous_source_digest,stream_name,stream_schema_version)`. **No treatment_id, full spec digest, algorithm manifest, run_id, attempt_id, worker ID, wall-clock**. A/B with same group+replicate+source/tape share identical stream *key*, yet must not share a mutable RNG object. Different replicate keys produce distinct exposure keys.
- **run-private**: `KDF(effective_master_seed,"private",frozen_run_spec_digest,component_id,component_manifest_digest,stream_name,stream_schema_version)`. Different algorithms/config/models produce different keys. Identical cell retries reuse exactly the same key but fresh private cursor/state (or validated checkpoint); attempts and generation never enter KDF.
- **standalone exogenous**: `KDF(effective_master_seed,"standalone-exo",scenario_digest,source_digest,stream_name,stream_schema_version)`. No cross-Run CRN claim unless an immutable identical tape/source contract is separately established.
- **analysis-only**: separate `AnalysisPlan` seed and domain, never reuse Run scopes. The byte-level analysis domain/inputs require EXP-01 approval before analysis randomness is claimed portable.

**MetricDefinition change tension:** C04 freezes metric digest within full FrozenRunSpec; C03 §6 says mere metrics change should not regenerate RNG. Under **this v1 strict full-spec KDF**, metric change yields a *new* cell and may rekey private streams. To reanalyse old immutable raw Run artifacts under a new metric, create a new AnalysisRecord (no rerun, no new RNG). If teams instead require unchanged physical RNG across re-instrumented Runs, jointly introduce a separate, content-addressed `rng_execution_projection_digest` with an audited whitelist, update both C03/C04 in a future version, and regenerate golden vectors; **do not silently substitute it for full spec digest here**. This decision remains a cross-signature item.

**Indexed external draws**: for a frozen opportunity address `A = LP4("SB-DRAW-v1",source_id,slot_id,ordinal_id)`, `draw_block = HMAC-SHA256(exogenous_stream_key,A)` and `draw_u64 = BE64(first_8_bytes(draw_block))`; optional uniform53 `u53 = draw_u64 >> 11; U = u53 / 2^53`. This is a *candidate stable indexed uniform primitive*, not a distribution-sampling rule. Draw addresses must be unique for the same stream (collision => hard reject), state-independent, and versioned. Sampling of Poisson processes, correlated weather, GA/PSO internal random distributions and numeric profile still require explicit PRNG/distribution versioned vectors and review. Freeze realized external event tapes with content digests as alternative/stronger exposure evidence.

## 4. Golden vectors — actual computed mathematical fixtures, not Run outcomes

Inputs are **synthetic unit fixtures**. Every `sha256:` input is SHA-256 of exact UTF-8 text; none is a hash of real SwarmBalance model/plan. Prefixes/lengths use §2 rules; keys are lowercase 32-byte hex. Independent Python `hashlib/hmac` and Node.js `crypto` calculations matched for representative identity/KDF/draw outputs in this proposal; **no repository implementation, CI, end-to-end simulation, PRNG distribution sampler, or real-world Validation was executed**.

| Symbol | `SHA256(UTF8(fixture string))` |
|---|---|
| `P` | `fixture:plan:v1` → `sha256:b43d54268f2adf20e250a338ada2feb31a99b287bb6ba805e3d35765a10574f0` |
| `D` | `fixture:experiment-definition:v1` → `sha256:e2b66e309d69a089fab8a0189f340e983b5cc1c0278e5893d482b3214284579f` |
| `SA` | `fixture:spec:greedy:v1` → `sha256:a540e853038fbacd834222d56e4805abc7c89d877f16430e256243addd87e0a9` |
| `SB` | `fixture:spec:pso:v1` → `sha256:84a2e7931c14eac17363bc3da228072744a47ec8ff6b7f275f5fb74c710336ef` |
| `SC` | `fixture:scenario:v1` → `sha256:74fe29e07feb5210a3d52b4c5a4476696c4185b1adc6190e740f33eb7da06484` |
| `EX` | `fixture:exogenous:demand:v1` → `sha256:9fb209e4879f6b69408983549954bae3df12d7370025ae00a1d0275e61a5ef93` |
| `CA` | `fixture:scheduler:greedy:v1` → `sha256:f9d4190026f4c960b6a340d1720fd6aa3945d963733df63d59b4ed24e73c3558` |
| `CB` | `fixture:scheduler:pso:v1` → `sha256:c964182ff5e387df382a2b5a8a55106e430f2d5307e7835c3369cbaebed2fe86` |

| Vector / exact ordered inputs | Expected |
|---|---|
| G01 `cell(A,r02,SA)`: LP4 tag, P, "A", "r02", SA | `sha256:41957ee33f111aa9fc24d694fa09c2261e0621ff8be41be653e5be32665164fb` |
| G02 `cell(B,r02,SB)`: LP4 tag, P, "B", "r02", SB | `sha256:b261ffc0c42e37128e68ac01c9d331cbc9cce5ab7cc8bad73b60198779fde94d` |
| G03 `attempt(A,1)`: LP4 tag, G01, "1" | `sha256:5751eff7a342d3bfbb1fcc9fc2c0d28785d0a9b2dbfd48edc890827fa132addb` |
| G04 `attempt(A,2)`: LP4 tag, G01, "2" | `sha256:1adfe2979472e854404c3857759381fbab428a8239a7c42cc7fccb0bf6fba62a` |
| G05 `run(A,1)`: LP4 tag, G03 | `sha256:0f1a0169cbd46f44ee4b2174f4f431fe50fca8a61b3ecc86e255a51c28b97d13` |
| G06 `run(A,2)`: LP4 tag, G04 | `sha256:f38690540e827d2768e28525d6729eb03f38aa411a0ac2aa5f1af2e56449a04a` |
| G07 master A: `KDF(9001,"run-master",D,"A","r02","v1")[:8]` | `5244eeb1ab1f40c4` = uint64 `5928125456373989572` |
| G08 master B: `KDF(9001,"run-master",D,"B","r02","v1")[:8]` | `6392354692bf1865` = uint64 `7174855733580601445` |
| G09 shared exo: `KDF(9001,"exo","p02","r02",SC,EX,"exogenous.demand.arrival","v1")` for both A/B | `71431f83f3cd9855fc1351335a3197d78cba1bce8adedb2fdcaf1f2e5a779f99` |
| G10 new replicate: `KDF(9001,"exo","p03","r03",SC,EX,"exogenous.demand.arrival","v1")` | `c6409fab9be559fac3c034bbec2e5ca7a26d054903976f40779590d41a865d11` |
| G11 private A: `KDF(G07,"private",SA,"scheduler",CA,"scheduler.search","v1")` | `a914a88477f24edb367427e591562680c62fb05a40483e0a29e67e021868648e` |
| G12 private B: `KDF(G08,"private",SB,"scheduler",CB,"scheduler.search","v1")` | `5b27c63dd4abceac6893f1a766f180efc742f5591cad633a965d67190ec06f65` |
| G13 `HMAC(G09,LP4("SB-DRAW-v1","source:demand","slot:7","ordinal:0"))[:8]` | `2276e70cab9bca45` / `draw_u64=2483426286146144837`, `draw_u53=1212610491282297` |

**Must assert:** A/B G09 identical; G09 ≠ G10; G11 ≠ G12; retry 1/2 share G09 and G11 but have distinct G03/G04/G05/G06; worker/concurrency/ack timing must not enter values. This table is a **candidate conformance vector**, not evidence that the existing code has implemented it.

Minimal Python verifier for these exact vector primitives (not an application runtime harness):

```python
import hashlib, hmac, struct
def lp4(*values):
    out = b""
    for value in values:
        raw = value.encode("utf-8")
        out += struct.pack(">I", len(raw)) + raw
    return out
def sha256_label(label):
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()
def digest_bytes(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()
def kdf(root, *fields):
    ikm = root.to_bytes(8, "big")
    salt = b"SwarmBalance/C03-HKDF-HMAC-SHA256-v1"
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    info = lp4("SB-RNG-v1", *fields)
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()
P = sha256_label("fixture:plan:v1")
SA = sha256_label("fixture:spec:greedy:v1")
cell_a = digest_bytes(lp4("SB-CELL-v1", P, "A", "r02", SA))
assert cell_a == "sha256:41957ee33f111aa9fc24d694fa09c2261e0621ff8be41be653e5be32665164fb"
```

This reference assumes inputs already validated as NFC and canonical strings. An implementation must enforce validation before calling these primitives and must independently check the full table, including reject fixtures; output-equality on these short strings is **not** full reproducibility certification.

## 5. 强制负例 / fail-closed oracle

| ID | Mutation / attempted behavior | Expected and retained evidence |
|---|---|---|
| ID-N01 | A logical cell request has same plan+treatment+replicate but a **different** spec digest; caller calls it a retry | **REJECT `PLAN_CELL_SPEC_CONFLICT`**; never allocate a second cell under this Plan; a **new** approved Plan revision is required; preserve original RunRecord |
| ID-N02 | Repost same `(cell_key,ordinal=1)` after result persisted and ack lost; worker tries to launch again | **`RUN_ATTEMPT_DUPLICATE` / idempotent return existing** without executing; no second sample |
| ID-N03 | Retry ordinal=2 but changed master_seed or external tape; claims same cell | **`RETRY_INPUT_DRIFT`**; no silent reseed, preserve failed attempt |
| ID-N04 | `replication_id=r01` and `replicate_key=r02` on ingestion | **`REPLICATE_ALIAS_CONFLICT`**; no ambiguous cell |
| ID-N05 | `attempt_id`, worker ID, run_id or full treatment spec added to exo KDF to "ensure uniqueness" | **`CRN_NAMESPACE_CONTAMINATION`**; A/B G09 mismatch, reject paired-design claim |
| ID-N06 | Two distinct replication keys produce identical exposure tape key/manifest without an explicit shared-tape design | **`REPLICATION_EXPOSURE_COLLISION`**; do not claim independent replicates |
| ID-N07 | Scheduler algorithm changes; system forcefully shares mutable private RNG handle between A/B | **`PRIVATE_STREAM_OWNER_CONFLICT`**; reject, private keys must differ |
| ID-N08 | Duplicate draw address `source:demand/slot:7/ordinal:0` reused for different opportunities | **`RNG_DRAW_ADDRESS_COLLISION`**; do not silently draw new sequential value |
| ID-N09 | Unspecified PRNG, Gaussian distribution, floating numeric profile or environment while claiming cross-runtime R3 | **`RNG_VERSION_UNPINNED` / `REPLAY_CLAIM_UNSUPPORTED`**; golden KDF alone is insufficient |
| ID-N10 | `attempt_ordinal="01"`, leading whitespace, non-NFC IDs, a JS float-corrupted uint64, non-lowercase digest or overflow | **`IDENTITY_ENCODING_INVALID`**; prevent silently different hashes |
| ID-N11 | FrozenRunSpec embeds plan_digest which itself includes spec digest, or retry includes run_id in spec hash | **`CYCLIC_SPEC_PLAN_DIGEST` / `ATTEMPT_FIELDS_IN_SPEC`**; abort freeze, emit diagnostic |
| ID-N12 | Crash leaves attempt-1 UNKNOWN; a new successful attempt is counted without reconciling it | **`ATTEMPT_OUTCOME_UNRESOLVED`**; Block ranking, both attempts preserved |
| ID-N13 | Two independent treatments use same "seed=101" but have different generated external event tapes | **`CRN_EXPOSURE_MISMATCH`**; same seed does not license paired comparison |
| ID-N14 | MetricDefinition digest changes; implementation silently reuses old `frozen_run_spec_digest` despite lock change | **`FROZEN_SPEC_CONTENT_MISMATCH`**; create new spec/cell or reanalyse immutable raw artifacts only |
| ID-N15 | Manual Run lacks experiment_ref and caller invents plan/cell to satisfy required field | **`INVALID_EXPERIMENT_BINDING`**; manual RunRecord must be accepted with `cell_key=null` |
| ID-N16 | Retry after postcommit metric export failure re-executes simulation boundary | **`POSTCOMMIT_RESIMULATION_FORBIDDEN`**; re-export from immutable committed frame; retain evidence gap |

Every rejection records `case_id, plan/cell/attempt/ref, expected/observed values, rejection code, state/metrics/evidence effect, artifact digest, evaluator`. Comparison on unresolved/unknown identity or CRN -> `INSUFFICIENT_EVIDENCE` or `NOT_COMPARABLE`, `ranking_allowed=false, ranking=null`; never silently drop failed RunRecords. For a gold-vector mismatch, report the first mismatching field/root/info bytes and **never** publish a false PASS.

### 5.1 Crash-safe attempt ledger (P0-03)

The full `PlanCellIndex → AttemptIndex → RunRecord → staged artifact → finalized result → AnalysisRecord selection` query order and durable CAS/fencing recovery semantics are defined in [FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md](FROZEN_RUN_SPEC_CANONICAL_AND_ATTEMPT_JOURNAL.md) §4. Never blindly allocate a second ordinal after a lost ACK; query existing attempt and result digest first. All three crash windows (allocation-before-dispatch, artifact-staged-before-finalize, finalized-before-ACK) need actual fault-injection evidence before M2 approval. **This PR adds design and synthetic hash calculations only.**

## 6. Required implementation tests and cross-sign

- **Design check performed:** this proposed byte-level fixture was calculated with Python hashlib/hmac and independently recomputed for representative vectors with Node.js crypto; the checked values matched. This verifies the math/encoding for those vectors only.
- **Not executed:** repository contract runner, CI, actual Run retries/idempotent durable journal, checkpoint restoration, stochastic distribution sampling, concurrent Harness, Legacy comparison, real-world Validation.
- Before freeze: AI-C confirms KDF salt/info/version, PRNG/distribution/numeric vectors and CRN opportunity semantics; EXP-01 confirms `logical_cell_tuple`, ExperimentPlan allocation without circular digests and sample selection; ARCH-02 confirms RunRecord writer/idempotent ledger/checkpoints; ARCH-03 confirms private stream identity; AI-R independently reruns vector tests and rejects all negatives; coordinator freezes ADR. Follow-ups require **both** #56 and #57 contracts to explicitly adopt the same schema and refreshed precise HEADs; text in this PR alone cannot amend the other author's PR.
