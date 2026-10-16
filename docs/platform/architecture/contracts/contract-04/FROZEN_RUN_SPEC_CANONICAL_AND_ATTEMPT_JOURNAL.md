# CONTRACT-04 × CONTRACT-03 — FrozenRunSpec 全量摘要、ExperimentPlan 单元绑定和持久化尝试账本

> **PROPOSED / P0-03 设计收敛候选，NOT FROZEN，非运行实现**。AI-D 在 CONTRACT-04 #57 独立分支起草；需 CONTRACT-03 AI-C、EXP-01、ARCH-02/03、AI-R 和主控会签后才进入 M2。
>
> 上游证据锁：#56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`（AI-C 原 RNG 草案）；#57 修订前 `027fd78589229db3d2308ced5365b7a780703805`；#59 独立复审 `e76eb483d5760d99673774d48dc699f6a833ad7f`；#60 实施门 `abc93227b9e3160da1023d6c582e7a93ff9094b5`。均为未合并 Draft，当前所有下述规则均为待批准版本，不代替 AI-C 对 LP4/HKDF 的明确 ACCEPT。

## C03 ↔ C04 最新增量会签登记（设计级、非生产冻结）

- AI-C PR #56 最新明确审阅 HEAD：`cb0efcb73638791e027588a1bd12e26e2dd08986`；其 `EXPERIMENT_SEED_CONTRACT.md §9.1–9.6` **ACCEPT** `C03C04-IDENTITY-v1`、LP4/HKDF 字节序、单 Plan 唯一 spec binding、attempt≠replicate，以及 **`SB-FROZEN-RUN-SPEC-v1 / SB-CJSON-1`** 作为共同的**PROPOSED** 全量规格序列化。AI-C 明确撤回竞争的 `SB-FRS-JCS-v1`；两个哈希协议**不得**混用。
- AI-C 在最新 #56 独立用 Python `hashlib/json` 重算 AI-D 完整合成 Spec 测试：SPEC-01=2471 bytes/`d2c07f032498322da6130f153d72199052e249559707574559c8791e2959ddf8`、SPEC-02=`99353448ec6277f9bac835e82f573bf9f8051832d45db0c5307f38ac5f68e5dd`，**2/2 合成数学匹配**；先前 G01–G13 为 **13/13** 数学向量匹配。
- **此处“接受”仅是 AI-C 对合同文本/数学实例的会签**，并非 EXP-01/ARCH-02/03 或 ARCH-06 冻结；对真实配置快照递归覆盖、Unicode 边界互操作、sampler 完整分布、durable journal/fencing/崩溃恢复和实际 CRN/R3/实验运行，仍为 NOT_RUN / UNVERIFIED。
- AI-D 的当前**单一**建议规范是本文件 §2 的 `SB-FROZEN-RUN-SPEC-v1 + SB-CJSON-1`。本次曾出现的 JCS 草案方向已撤回；旧数学 SHA 作为历史取证可见，但不是当前契约数据格式。任何未来更换序列化必须版本升级并由两方共同签字，不接受隐式迁移。

## 1. 唯一身份与 Plan 内的单值约束（C03C04-IDENTITY-v1）

```text
freeze resolved seed allocations and complete FrozenRunSpecs first
-> build canonical ExperimentPlan binding table [(treatment_id, replicate_key, frozen_run_spec_digest)]
-> plan_digest = digest(canonical immutable ExperimentPlan)
-> logical_cell_key = SHA256(LP4("SB-CELL-v1",
                                 plan_digest, treatment_id, replicate_key,
                                 frozen_run_spec_digest))
-> attempt_id = SHA256(LP4("SB-ATTEMPT-v1", cell_key, ordinal_decimal))
-> run_id = SHA256(LP4("SB-RUN-v1", attempt_id))
```

- **唯一约束**：在同一 `ExperimentPlan` 内容中，映射 `(treatment_id,replicate_key) → EXACTLY ONE frozen_run_spec_digest` 必须是单值函数；禁止重复行、重复 ID、同一组绑定两个不同规格。等价实现的索引键为 `(plan_digest,treatment_id,replicate_key)`。对同一个已冻结计划发现另一个 spec digest，返回 `PLAN_CELL_SPEC_CONFLICT`，不允许悄悄生成另一个 cell、补充重复样本或覆盖旧绑定。要改变规格，冻结 **新 ExperimentPlan 内容/新 plan_digest**，引用 `supersedes_plan_digest`，重新审核预注册/样本与比较资格。
- 不同 treatment 在相同 `replicate_key` 可以共享 `pairing_group_id` 与不可变外生 tape，但仍是**不同** logical cells；`replicate_key` 是设计的独立重复单元标识，不是 attempt 序号。旧称 `replication_id` 只在显式迁移入口允许，冲突拒绝。
- `FrozenRunSpec` 冻结**执行语义**，与 `plan_digest` 不能互相引用形成环。运行身份绑定 `run_id/attempt_id/attempt_ordinal/worker/generation/retry_of/status/wall-time` 只在 RunRecord/attempt envelope 中，**不参与 spec_digest**。Plan 可引用 spec，spec 不引用最终 Plan。种子分配属于先于 Plan digest 计算的固定 `seed_allocation_digest`。
- `run_id`：唯一执行尝试/RunRecord 身份；`attempt_id`：不可变计划单元 + 严格正整数序号的幂等键；`replicate_key`：预注册的**独立统计单位**。一次恢复 checkpoint 不造新 replicate；同一 attempt 请求重复送达必须返回原记录、不重新执行；真正的 retry 使用下一 ordinal，并保留旧 attempt 的历史故障。
- 人工单 Run 无 `ExperimentPlan`，`cell_key=null`，用独立请求幂等键分配 RunRecord；不能通过虚构 Plan 来满足字段。

## 2. FrozenRunSpec 的完整可序列化资源（SB-FROZEN-RUN-SPEC-v1）

以下是 **V1 最低完整规格的必填 schema**，不是随意把某些字段放入随缘 JSON 后计算哈希。顶层字段列表固定，全部必须出现；任意缺键/多键拒绝。子对象字段也按此表精确校验。每个 `..._digest` 引用的是**已固定、内容可解析、逐字节验证**的完整资源（不是 URI 或未跟踪 mutable config），该资源的自身规范化格式由其生产者提供并注明版本；不知道来源即不能进入 strict Run。

| 必填字段（精确名称） | 类型与必须锁定的执行事实 |
|---|---|
| `schema_version` | 字符串，精确 `SB-FROZEN-RUN-SPEC-v1` |
| `world_ref, scenario_ref` | 各为 `{id,revision,digest}`：冻结实体/场景配方、时域和静态资源 |
| `resolved_config_ref` | `{digest}`：包含全部已解析默认值、参数、单位、路径内容指纹/任何明确的 fallback |
| `assembly_ref` | `{digest}`：涵盖解析后的组件 DAG、id/contract+implementation version、参数与代码身份 |
| `dataset_manifest_refs, model_manifest_refs` | `[{id,revision,digest}]`：所有地图、任务、天气/风、物理/调度模型、溯源及其输入 snapshot |
| `code_ref` | `{commit_sha,dirty,source_tree_digest,execution_mode}`：40 位小写完整 Git commit；若 dirty=true，tree digest 必须固定所有修改字节且不可声称 clean replay |
| `runtime_profile_ref` | `{digest}`：OS/CPU架构/解释器与依赖锁、算术/数值 profile、确定性能力等 |
| `converter_profile_refs` | `[{id,version,digest}]`：单位、CRS、time 坐标与精度显式转换；无转换为 `[]` |
| `clock_policy` | `{mode,step_ns,horizon_ns,end_boundary_policy}`，`*_ns` 用规范 uint64 十进制**字符串**；规则与 B03 待会签 |
| `seed_allocation` | `{seed_source,effective_master_seed_uint64,seed_allocation_digest}`；实验源来自已锁定 Plan 分配表，禁止运行中更改 |
| `rng_contract` | `{kdf_id,prng_id,sampler_profile_id,numeric_profile_id,stream_contract_digest,external_exposure_digest}`，版本及输入/采样完整指纹 |
| `metric_definition_refs` | `[{id,version,digest}]`，冻结分母/时间窗/聚合/缺失语义，变更必须重摘要 |
| `failure_policy_ref` | `{digest}`：超时/取消/事务失败/允许重试及污染策略 |
| `completeness_policy` | `{audit_required,required_artifacts}`，布尔和已排序唯一的 artifact kind 列表 |
| `execution_profile` | `{resource_budget_digest,termination_policy_digest}`，所有影响停止/观测的策略 |

凡执行语义值都必须被上述字段自身或被引用的内容寻址资源**完全覆盖**。动态网络数据若没有物化为固定 snapshot、未声明副作用、未明确 RNG 分布变换或组件私有状态复现策略，返回 `SPEC_UNFREEZABLE`。Schema 不得静默加入 `extensions`；扩展需新 `schema_version`、明确迁移及 golden vector。顶层 spec **不得**有 `spec_digest` 字段：摘要作为外层 immutable ref `{schema_version,digest,byte_length}` 保存。

### SB-CJSON-1 规范字节协议

1. 输入为已验证的精确 schema 对象；只允许 object、array、NFC Unicode string、JSON `true/false/null`（仅字段 schema 明确许可 null）。**禁止所有 JSON number**（整数与浮点均不得作为 JSON 数字）；所有整数、时间、种子和精确十进制在已定义字段内表示为字符串，以免 JS 53-bit 精度损失。
2. 数字字符串的类型验证：uint64 属于 `0..18446744073709551615`；格式只允许 `0` 或 `[1-9][0-9]*`；正整数 ordinal 不得为 0；有符号十进制须严格最简形式，禁止科学记数法、前置零、末尾无意义小数 0、`-0`、`+1`。本 schema 仅包含明确列出的 uint64 string。
3. Object keys 精确 schema ASCII 名称，按其 **UTF-8 字节升序**排列；没有空格、缩进或换行；结构标点精确 `{}[]:, `（格式中无空格）。字符用 UTF-8 NFC，无 BOM；双引号/反斜杠转义，控制字符按 JSON 常见短转义 `\\b,\\t,\\n,\\f,\\r`，其余 U+0000–U+001F 用小写 `\\u00xx`；斜线不转义；非控制 Unicode 字符按原 UTF-8 输出（包含 U+2028/2029），禁孤立 surrogate。
4. `dataset_manifest_refs, model_manifest_refs, converter_profile_refs, metric_definition_refs` 是**集合语义数组**：每个元素先单独按 SB-CJSON-1 编码，依其 UTF-8 字节升序排序，重复元素或重复 `id/version` 且不同摘要硬拒绝。`required_artifacts` 按 NFC 字符串的 UTF-8 升序并去重（重复即拒绝）。其他数组若引入必须由新版 schema 指定是顺序还是集合，禁止让进程迭代顺序隐含排序。
5. `canonical_bytes=SB-CJSON-1(spec)`；`frozen_run_spec_digest="sha256:"+lowerhex(SHA256(canonical_bytes))`。内容身份包括字段名和值，**不包括**输出包装 `digest`、RunRecord、ExperimentPlan、`run_id` 或 `attempt_id`。相同规范内容相同 SHA；相同 `id+revision` 不得代表不同内容 digest。
6. Python 的 `json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)` 仅在前述输入校验/规范数组已完成时，是本 schema 的一种候选实现；裸调用 json.dumps **不能替代校验**。JavaScript 禁止将 uint64 string 转为 Number 再编码，且不能直接 `JSON.stringify` 未排序对象做 hash。

### Synthetic SPEC-01 向量（Python/Node 独立计算）

生成所有引用 digest 的原始测试文本规则：`H(label) = "sha256:" + SHA256(UTF8("fixture:" + label + ":v1")).hexdigest()`，label 依次为 `world,scenario,config,assembly,dataset,model,code,runtime,seed-allocation,streams,exposure,metric,failure,budgets,termination`。构造以下**已冻结 schema 形状**的合成输入（字段无省略）。该例仅用于比较 canonical bytes，未宣称对应资源是可运行模型：

```python
import hashlib, json
H = lambda name: "sha256:" + hashlib.sha256(("fixture:"+name+":v1").encode()).hexdigest()
s = {
  "schema_version":"SB-FROZEN-RUN-SPEC-v1",
  "world_ref":{"id":"world:fixture","revision":"1","digest":H("world")},
  "scenario_ref":{"id":"scenario:fixture","revision":"1","digest":H("scenario")},
  "resolved_config_ref":{"digest":H("config")},
  "assembly_ref":{"digest":H("assembly")},
  "dataset_manifest_refs":[{"id":"dataset:fixture","revision":"1","digest":H("dataset")}],
  "model_manifest_refs":[{"id":"model:fixture","revision":"1","digest":H("model")}],
  "code_ref":{"commit_sha":"0123456789abcdef0123456789abcdef01234567","dirty":False,
              "source_tree_digest":H("code"),"execution_mode":"NATIVE_HARNESS"},
  "runtime_profile_ref":{"digest":H("runtime")},
  "converter_profile_refs":[],
  "clock_policy":{"mode":"FIXED_STEP","step_ns":"1000000000","horizon_ns":"3600000000000",
                  "end_boundary_policy":"INCLUSIVE_LAST"},
  "seed_allocation":{"seed_source":"EXPERIMENT_PLAN","effective_master_seed_uint64":"5928125456373989572",
                     "seed_allocation_digest":H("seed-allocation")},
  "rng_contract":{"kdf_id":"C03-HKDF-HMAC-SHA256-v1","prng_id":"HMAC-INDEXED-U64-v1",
                  "sampler_profile_id":"C03C04-SAMPLER-MIN-v1",
                  "numeric_profile_id":"SB-NUMERIC-IEEE754-BINARY64-v1",
                  "stream_contract_digest":H("streams"),"external_exposure_digest":H("exposure")},
  "metric_definition_refs":[{"id":"metric:timeout_rate","version":"1.0.0","digest":H("metric")}],
  "failure_policy_ref":{"digest":H("failure")},
  "completeness_policy":{"audit_required":True,"required_artifacts":["diagnostics","metrics","run_manifest"]},
  "execution_profile":{"resource_budget_digest":H("budgets"),"termination_policy_digest":H("termination")}
}
b = json.dumps(s,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
assert len(b) == 2471
assert hashlib.sha256(b).hexdigest() == "d2c07f032498322da6130f153d72199052e249559707574559c8791e2959ddf8"
```

- SPEC-01 原始内容字节长度：**2471**；`frozen_run_spec_digest=sha256:d2c07f032498322da6130f153d72199052e249559707574559c8791e2959ddf8`。
- SPEC-02 仅把 `metric_definition_refs[0].version` 从 `1.0.0` 改为 `1.0.1`，其余保持原样：预期 `sha256:99353448ec6277f9bac835e82f573bf9f8051832d45db0c5307f38ac5f68e5dd`。这是**负例**：不允许沿用原 spec digest。
- 以上 SPEC-01/02 各经 Python `hashlib/json` 与 Node.js `crypto/自写键排序 JSON` 分别复算，SHA 一致。**数学/序列化验证 ≠ Harness 已实现 ≠ PRNG/分布可重放 ≠ 现实模型 Validation**。
- LP4/HKDF 原 **G01–G13** golden vectors 继续由 [LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md](LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md) 定义；其合成 Plan/Spec label 摘要是 **身份层的固定测试输入**，并非 SPEC-01 完整 spec digest，不能暗中混用两个 fixture 集。

## 3. RNG/采样器/数值环境：最低有效合同

- KDF 字节规则仍为候选 `C03-HKDF-HMAC-SHA256-v1`：`LP4` 的 uint32 大端长度前缀、NFC/UTF-8，HKDF-Extract 的 IKM=BE64(seed)，盐=`SwarmBalance/C03-HKDF-HMAC-SHA256-v1`，HKDF-Expand info=`LP4("SB-RNG-v1",domain,ordered_fields...)`，L=32，首次 HMAC 末尾 `0x01`。**AI-C 在 #56 @ `cb0efcb73638791e027588a1bd12e26e2dd08986` 已对 LP4/HKDF、SPEC-01/02 给出设计级 ACCEPT，数学为 G01–G13 13/13、SPEC 2/2；但对异常输入、通用非 ASCII serializer/采样器/运行态持久化及多方冻结仍须独立验收**。
- 最低随机引擎 `HMAC-INDEXED-U64-v1`：每个 draw 由 `HMAC-SHA256(stream_key,LP4("SB-DRAW-v1",source_id,slot_id,ordinal_id))` 输出，首 8 字节 BE64；不共享 mutable PRNG；地址重复映射不同机会必须拒绝。`UNIFORM53-v1`：`u53=draw_u64>>11`，`U=u53/2^53`（IEEE-754 binary64, ties-to-even）。原 G13 检查一个地址和输出。**仅 U64/UNIFORM53 基元**在此版本具有可核对的字节向量。
- `C03C04-SAMPLER-MIN-v1` 允许严格版本化的 `U64`、`UNIFORM53`；进一步随机律如 `BERNOULLI-RATIONAL-v1` 可以定义为规范 `a/b`、`0<=a<=b` 的整数阈值抽样（拒绝采样剔除取模偏差），`CATEGORICAL-INTEGER-v1` 可按稳定实体排序及整数权重定义。但 **在两路径产生各自完整 golden vectors 和误差/边界规范之前，这两者仍不可被标为已支持的 portable sampler**。Poisson demand、Gaussian wind、指数间隔/其他真实物理采样器一律 `SAMPLER_VERSION_UNPINNED`，除非冻结明确分布/变换/抽样消费规则、数值版本与独立 golden vectors；或者先物化带 digest 的 immutable external event tape，不依赖运行时重新抽样。
- `SB-NUMERIC-IEEE754-BINARY64-v1` 是候选数值 profile：binary64、roundTiesToEven、禁非有限值/隐式 FMA 收缩/不稳定并行归约；固定计算次序和比较容差、浮点库/编译器/CPU/操作系统/依赖包版本到 `runtime_profile_ref`。不满足这些约束时不能声称跨平台 R3 bit-identical。仅固定 KDF vector 不等于固定统计分布或运行环境。
- Exogenous CRN key **不包括** treatment、full FrozenRunSpec digest、attempt/run ID 或 worker；private key **包括** frozen spec/component manifest 但排除 attempt/worker；**相同 plan cell 重试复用相同根+key/固定外生 tape，且 RNG cursor 从干净状态或合法 checkpoint 恢复**。同 seed 但 tape 不同须拒配对；指标锁变更导致 spec digest 改变并可能重键 private stream，若只想更新旧数据分析应创建新的 AnalysisRecord，不重跑；“不改 RNG 的 metric-only instrumentation”需要新版本的执行子摘要和跨组裁决。

## 4. 崩溃一致性与 exactly-once 统计选择（不是 exactly-once 物理执行）

**逻辑存储模型，不要求数据库/云服务**：实验编排器拥有固定 PlanCellIndex（不可变计划绑定）；Harness 唯一创建 RunRecord 与写入 attempt 生命周期；Experiment BatchRecord 引用所有尝试。底层可用单进程持久 journal/原子文件操作或小型本地事务 store，必须真实证明 crash-safety 与唯一性，**仅说 append JSONL 不等于已保证原子性**。

1. `PLAN_FROZEN`：生成 spec 和分配表；对 `(plan_digest,treatment_id,replicate_key)` CAS/唯一索引绑定唯一 spec digest；冲突 `PLAN_CELL_SPEC_CONFLICT`，冻结新 Plan 前不得追加独立样本。
2. `ATTEMPT_ALLOCATED`：在耐久事务下 `CAS(cell_key,attempt_ordinal)`，落 `attempt_id/run_id/spec_digest/retry_of/status=PREPARED`，**先 durable commit，再派送到 worker**；索引的内存状态不是事实源。重复申请已存在的 ordinal => **查询并返回原记录**；不得启动第二个 worker。
3. `CLAIMED/RUNNING`：worker 使用带 fencing epoch 的独占 lease；失效 owner 不得在新 owner 已接管后提交旧结果。运行物理副作用若无法有效 fence/重建，必须保留 UNKNOWN，不许凭超时假定“未执行”。
4. `RESULT_STAGED`：将 artifacts 写到新内容地址，验证 sha256/字节数，flush/fsync 后写 durable staging journal；对同一 `attempt_id` 不同 result digest 冲突拒绝（`RUN_RESULT_CONFLICT`）。
5. `FINALIZED`：RunRecord append `execution_status,terminal_reason,artifact_refs,result_digest,metric/evidence_completeness`，以 `attempt_id + result_digest` CAS 幂等提交；提交一旦持久完成但 ACK 丢失，调用方按 `attempt_id` **只读查找**并返回原 finalized result，绝不重跑。staging 存在但 finalize 未完成时核验工件并执行幂等 finalize，而非生成新的 Run。
6. `CRASH_RECOVERY`：任何异常窗口，查询顺序：PlanCellIndex → AttemptIndex → RunRecord journal → staged/result content hashes → lease epoch/worker liveness；有 finalized 返回；仅有 staging 则核验恢复；RUNNING 且可能留副作用则 `OUTCOME_UNKNOWN`、冻结 lease 与统计选择直至独立核清，绝不盲目再执行 ordinal。只有记录失败/取消/不可信并满足预注册 retry_policy 才以 **新 ordinal + 新 RunRecord** 重试相同 spec/seed/tape。
7. `ANALYSIS_SELECTION`：BatchRecord append 所有 `NOT_DISPATCHED/PREPARED/RUNNING/FAILED/CANCELLED/OUTCOME_UNKNOWN/SUCCEEDED` attempts 及理由。对固定 `(analysis_plan_digest,cell_key)` 的已选 `attempt_id` 做 CAS 和 immutable snapshot；每 cell 至多一个可纳入统计。缺 attempt、悬挂引用、未决 UNKNOWN 或选择策略漂移：`INSUFFICIENT_EVIDENCE` / `NOT_COMPARABLE` 且 `ranking=null`。已完成旧分析不可被后台重试修改，变更只能生成新 AnalysisRecord。

**三个崩溃窗口必须独立验证**：A）ALLOCATED 已刷盘但未分发；B）result bytes 已刷盘但 FINALIZED 未完成；C）FINALIZED 已提交、ACK 未送达。负例：fenced 旧 worker late commit，双并发 allocate 相同 ordinal，不同 result digest，跨 spec 伪重试，另造 replicate 冒充 retry。所有事件需固定 `request_id,cell_key,attempt_ordinal,attempt_id,run_id,status_from/to,lease_epoch,artifact_digest,commit_sequence,decision_reason` 的审计格式；日志时间是诊断不是 RNG 种子。

## 5. 正反验收、已执行检查、残余门禁

| Case | Expected future outcome | This PR status |
|---|---|---|
| SPEC-01/02 | full-spec 规范字节/摘要跨 Python+Node 一致；指标变更生成不同摘要 | **仅合成数学计算完成，已取得两语言匹配结果** |
| ID G01–G13 | LP4/HKDF 身份与 RNG 根向量一致 | 已存在 13 个合成 golden vectors；独立复审记载 13/13 数学一致；**未运行系统 RNG** |
| P03-01 | 同 Plan 相同 treatment+replicate 绑定不同 digest | REJECT `PLAN_CELL_SPEC_CONFLICT`；NOT RUN |
| P03-02 | 相同 cell+ordinal 并发发起两次 | 返回同一 attempt/RunRecord；NOT RUN |
| P03-03 | 崩溃窗口 A/B/C 重启后查询账本 | 单元身份稳定、不双计；NOT RUN |
| P03-04 | 旧 worker 过期 fencing epoch 提交 | REJECT `STALE_ATTEMPT_LEASE`；NOT RUN |
| P03-05 | 换 spec/seed/tape 后使用“retry” | REJECT `RETRY_INPUT_DRIFT`；NOT RUN |
| P03-06 | 失败 attempt-1 与成功 attempt-2 | 两个 RunRecord、只有一个所选样本；NOT RUN |
| P03-07 | Poisson/Gaussian 未版本化采样器声明 R3 | REJECT `SAMPLER_VERSION_UNPINNED`；NOT RUN |
| P03-08 | Python/JS uint64 JSON number，非规范数字/Unicode/排序 | REJECT `SPEC_CANONICALIZATION_INVALID`；NOT RUN |
| P03-09 | 동일 seed A/B 但外生 tape hash 不同 | REJECT `CRN_EXPOSURE_MISMATCH`；NOT RUN |
| P03-10 | CI 软件门绿但缺 Validation 现实参照 | Reality Validation=NOT_ASSESSED；NOT RUN |

实测范围：只做了 GitHub HEAD/文档/白名单静态核验及合成 JSON canonical SHA-256 的 Python、Node.js 两个独立计算路径；无 GitHub Actions、完整 RunSpec freeze 实现、持久 journal crash 注入、Harness/Experiment 运行、PRNG 分布采样器全向量、物理 Validation/UQ 的成功证据。**不允许将 SPEC-01/02 或 G01–G13 数学通过写成 M2/R3/研究 PASS**。

签字工作：AI-C 已对 `LP4/HKDF` 与 SPEC-01/02 **设计数学**给出 ACCEPT；仍须对 PRNG/distribution 全 profile、非 ASCII 规范解码、异常输入及应用实现给出单独的可复核决定；EXP-01 确定 ExperimentPlan 分配表与 retry policy；ARCH-02 审核 RunRecord durable writer/fencing；ARCH-03 审核 stream manifest 与 MetricDefinition 锁；AI-R 完整负例/崩溃独立评审；主控冻结 ADR。未会签前保持 **HOLD / NO-FREEZE**。
