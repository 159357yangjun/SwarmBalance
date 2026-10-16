# CONTRACT-04 × CONTRACT-03 — FrozenRunSpec 全量摘要、ExperimentPlan 单元绑定和持久化尝试账本

> **PROPOSED / P0-03 设计收敛候选，NOT FROZEN，非运行实现**。AI-D 在 CONTRACT-04 #57 独立分支起草；需 CONTRACT-03 AI-C、EXP-01、ARCH-02/03、AI-R 和主控会签后才进入 M2。
>
> 上游证据锁：#56 `0b038f29e7f1957bf93e4afd1e3a171d54e5b620`（AI-C 原 RNG 草案）；#57 修订前 `027fd78589229db3d2308ced5365b7a780703805`；#59 独立复审 `e76eb483d5760d99673774d48dc699f6a833ad7f`；#60 实施门 `abc93227b9e3160da1023d6c582e7a93ff9094b5`。均为未合并 Draft，当前所有下述规则均为待批准版本，不代替 AI-C 对 LP4/HKDF 的明确 ACCEPT。

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

## 2. FrozenRunSpec 的统一规范序列化：`SB-FRS-JCS-v1`

> **Cross-reconciliation with AI-C #56 @ `4b0af61718af8f25f9a44c33cef63f0cba1f1c57`:** AI-C §9.3 提议 `SB-FRS-JCS-v1` (RFC 8785) 作为全量 RunSpec 序列化。AI-D **ACCEPTS the same profile ID and RFC 8785 byte serializer as the target**;此前 AI-D `SB-FRS-JCS-v1/SB-FRS-JCS-v1` 自定义格式现正式撤回为历史计算草案，**不得**与 JCS 共同作为正式 spec digest。此处在 AI-C 12 个顶层键形状内补齐精确流描述符/完整 fixture，供 AI-C 再次会签；没有声称已获得 EXP-01/ARCH-02 的正式 ADR。

### 2.1 唯一根对象 Schema

恰好存在 AI-C 指定的 12 个 root keys：`schema_version,world,scenario,code,inputs,assembly,config,execution,seed,metrics,failure_policy,evidence_policy`；`schema_version="SB-FRS-JCS-v1"`。**禁止无声明键、缺键、变动执行隐式默认值**。V1 子结构规定：

| Root | 精确最低字段和冻结事实 |
|---|---|
| `world` | `{ref,digest}`：不可变 World/revision 和完整内容 digest |
| `scenario` | `{ref,digest,seed_default_uint64}`：固定场景/外生事件配方，原默认种子也保留 |
| `code` | `{digest}`：内容寻址的 code manifest，必须递归锁 engine 40-char commit、dirty-tree snapshot、runtime code/worker/adapter 版本；不能仅存可变 branch |
| `inputs` | `[{id,digest}]`：全部不可变数据快照/OSM/外生输入，按 `id` 的有效 Unicode UTF-16 代码单元序稳定排序，重复 id 拒绝 |
| `assembly` | `{digest}`：全部组件有序 DAG、model/algorithm manifest、实现版本、参数、依赖、capabilities |
| `config` | `{digest}`：所有 effective config 参数/展开默认/单位和转换/路径内容 hashes，不能指向运行时可变设置 |
| `execution` | `{clock_policy_digest,horizon_seconds,numeric_profile_digest}`：精确秒数字符串，数字/时钟相位含在引用；ARCH-02 的 B03 签字仍需完成 |
| `seed` | `{source,master_seed_uint64,seed_allocation_digest,streams}`；**seed_allocation_digest 是 AI-D 提出的附加必需子键**，明确绑定 Plan 前种子分配内容；须 AI-C/EXP 会签或版本化更改 |
| `metrics` | `{definition_digests}`：所有指标完整含分母/窗口语义的摘要，按 digest 字符串字节排序，不能隐式运行后重解释 |
| `failure_policy` | `{digest}`：事务失败/退化/取消/超时/重试能力的固定策略 |
| `evidence_policy` | `{digest}`：输出/工件完整性/资源预算/终止与可审计要求均由引用指向的已冻结资源完全覆盖 |

`seed.streams` 为按 `name` 唯一且稳定排序的对象数组，**每个对象精确包含**：
`name,namespace,owner_id,source_digest,exposure_ref,stream_schema_version,kdf_id,bit_generator_id,bit_generator_impl_digest,distribution_id,distribution_parameters_digest,sampler_algorithm_version,transform_version,draw_address_schema,numeric_profile_digest,checkpoint_policy`。当 stream 属私有域，`exposure_ref=null`（显式 null），不允许空字符串伪装外生引用。参数、采样支持域、随机变量单位、原始外部 tape、抽样公式在对应 `*_digest` 内容里；无法解析并验真实内容则严格 Run 必须拒绝。`seed_allocation_digest` 在 **Spec freeze 前** 从 ExperimentDefinition/seed root 和预注册分配计算，绝不包含最终 plan_digest，杜绝循环。

完整 Spec 指的是以上强制引用的**传递性完整冻结**：只 hash 根对象而引用内容缺失、悬挂、路径随时间变、未被采样器版本解释，均 `SPEC_UNFREEZABLE`。新增任何执行语义字段须升级 schema 版本和向量，不能把它藏在未纳入哈希的 Run envelope。

### 2.2 精确 RFC 8785 (JCS) 字节规则

1. 验证全部 schema 字段、引用可解和 SHA256 与真实字节一致后，将整个根对象序列化为 RFC 8785 JCS；UTF-8，无 BOM、无额外换行/空白。Object 键按 **UTF-16 代码单元顺序**排序（不是 UTF-8 字节序）；转义、Unicode 和键排序以完整 RFC 8785 为准，不能用 `sort_keys=True` 对所有 Unicode 输入宣称完整实现。
2. 所有键和值为有效 Unicode scalar、NFC 规范化；重复 JSON object keys 在**解析前拒绝**，不得最后值覆盖；含 lone surrogate、非规范化别名均拒绝。数组顺序有语义：`inputs` 按唯一 `id` 排序、`seed.streams` 按唯一 `name` 排序、`metrics.definition_digests` 词典序排序并去重；不允许未申报的 set/map 迭代顺序参与哈希。
3. 为避免跨语言整数精度丢失，**禁止整个 RunSpec 中的原始 JSON number**；数值必须是带明确 schema 单位/类型的**规范十进制字符串**。无符号整数以 `0|[1-9][0-9]*` 且 uint64 范围校验，decimal 只允许无指数/无多余尾零/无前导+号的最短合法形式；拒绝 `-0`、NaN、Inf、`01`、JS Number 四舍五入。bool 用 JSON boolean；null 仅对明确许可字段。
4. `canonical_bytes=UTF8(JCS(validated_spec))`；`frozen_run_spec_digest="sha256:"+lowerhex(SHA256(canonical_bytes))`；摘要外层引用，不可作为 spec 自身字段。**plan_digest/cell_key/run_id/attempt_id/attempt_ordinal/generation/retry_of/worker/log/timestamp/status** 不进入规格的语义内容。Schema 编码、外部引用解析、RNG 分布清单、时钟及数值环境每项变化应产生独立的新 digest，不能沿用先前哈希。

### 2.3 JCS-FULL-01/02 合成 full-schema golden vector

- 参考材料 label 规则与 AI-C 保持同一命名空间：`H(label)="sha256:"+lowerhex(SHA256(UTF8("fixture:frs:"+label)))`。
- 精确 12 root keys 的**全字段合成向量生成代码**（仅 ASCII 字符，因此 Python `json.dumps(sort_keys=True)` 在这个特定向量与 RFC 8785 JCS 产生相同字节；对完整 Unicode 必须使用真正 JCS 实现并运行 RFC 测试集）：

```python
import json, hashlib
H=lambda n:"sha256:"+hashlib.sha256(("fixture:frs:"+n).encode()).hexdigest()
s={
 "schema_version":"SB-FRS-JCS-v1",
 "world":{"ref":"world:fixture@1","digest":H("world")},
 "scenario":{"ref":"scenario:fixture@1","digest":H("scenario"),"seed_default_uint64":"101"},
 "code":{"digest":H("code")},
 "inputs":[{"id":"dataset:fixture","digest":H("dataset")}],
 "assembly":{"digest":H("assembly")},
 "config":{"digest":H("config")},
 "execution":{"clock_policy_digest":H("clock"),"horizon_seconds":"600","numeric_profile_digest":H("numeric")},
 "seed":{"source":"experiment_plan","master_seed_uint64":"5928125456373989572",
         "seed_allocation_digest":H("allocation"),
         "streams":[{"name":"exogenous.demand.arrival","namespace":"exo","owner_id":"scenario:demand",
           "source_digest":H("exo"),"exposure_ref":"exposure:p02@1","stream_schema_version":"v1",
           "kdf_id":"C03-HKDF-HMAC-SHA256-v1","bit_generator_id":"HMAC-INDEXED-U64-v1",
           "bit_generator_impl_digest":H("bitgen"),"distribution_id":"UNIFORM53-v1",
           "distribution_parameters_digest":H("distribution"),"sampler_algorithm_version":"v1",
           "transform_version":"v1","draw_address_schema":"SB-DRAW-v1",
           "numeric_profile_digest":H("numeric"),"checkpoint_policy":"BY_ADDRESS"}]},
 "metrics":{"definition_digests":[H("metric")]},
 "failure_policy":{"digest":H("failure")},
 "evidence_policy":{"digest":H("evidence")}
}
b=json.dumps(s,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
assert len(b)==2217
assert hashlib.sha256(b).hexdigest()=="bec73edca85a81be16a2664e4c189c19be3df79dce4aecea2d4d94e7ad687d38"
s["metrics"]["definition_digests"]=[H("metric-v2")]
changed=json.dumps(s,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
assert hashlib.sha256(changed).hexdigest()=="c241a98aeef32b30d31fb1141f8849646200393c168f1bb7ee5539360f3e52e1"
```

- **JCS-FULL-01：2217 UTF-8 bytes，`sha256:bec73edca85a81be16a2664e4c189c19be3df79dce4aecea2d4d94e7ad687d38`。**
- **JCS-FULL-02：仅 `metric` digest 变 `fixture:frs:metric-v2`，`sha256:c241a98aeef32b30d31fb1141f8849646200393c168f1bb7ee5539360f3e52e1`。**
- Python `hashlib/json` 与独立 Node.js `crypto` + 显式键排序编码路径分别计算，**此 ASCII 测试向量 2/2 一致**。这不等于完整 RFC 8785 Unicode 边界测试通过，也不代表资源 manifest 真验签或真实 Run 可复算。
- AI-C 原 #56 §9.3 的 `1538 bytes/sha256:9521ff3ae9fc51263863bafda8567b2b184dad055234609a3c4238dfd8a26d34` 是**较小的结构性 JCS 草案 fixture**；二者根形状相容但 seed.streams 完整字段覆盖不同，不可误认为是**同一序列化对象**或跨版本替代关系。补全子键需 AI-C 明确核准；没有将 #56 的原历史内容当作新正式 SPEC-01 实现证据。
- 原 AI-D 自定义 `SB-FRS-JCS-v1` 的 `2471 bytes/sha256:d2c07f032498322da6130f153d72199052e249559707574559c8791e2959ddf8` 和改指标版本摘要 `sha256:99353448ec6277f9bac835e82f573bf9f8051832d45db0c5307f38ac5f68e5dd` **仅为被取代的历史数学 fixture，非当前采用的 FrozenRunSpec digest**；严禁在 Plan 中与 JCS-FULL 混用。
- LP4/HKDF 原 G01–G13 使用各自合成字符串 SHA256 作为 spec 输入，与 JCS-FULL-01 哈希不相同；**身份编码数学向量与真实 Spec 序列化是两套独立测试层**。

## 3. RNG/采样器/数值环境：最低有效合同

- KDF 字节规则仍为候选 `C03-HKDF-HMAC-SHA256-v1`：`LP4` 的 uint32 大端长度前缀、NFC/UTF-8，HKDF-Extract 的 IKM=BE64(seed)，盐=`SwarmBalance/C03-HKDF-HMAC-SHA256-v1`，HKDF-Expand info=`LP4("SB-RNG-v1",domain,ordered_fields...)`，L=32，首次 HMAC 末尾 `0x01`。**AI-C 需对 #57 全部原始 G01–G13、JCS-FULL-01/02 和异常输入明确 ACCEPT/CHANGES_REQUESTED**，仅知道 13/13 哈希复算一致不等于 AI-C 已签字。
- 最低随机引擎 `HMAC-INDEXED-U64-v1`：每个 draw 由 `HMAC-SHA256(stream_key,LP4("SB-DRAW-v1",source_id,slot_id,ordinal_id))` 输出，首 8 字节 BE64；不共享 mutable PRNG；地址重复映射不同机会必须拒绝。`UNIFORM53-v1`：`u53=draw_u64>>11`，`U=u53/2^53`（IEEE-754 binary64, ties-to-even）。原 G13 检查一个地址和输出。**仅 indexed U64/UNIFORM53 基元**在此版本具有可核对的字节向量。
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
| JCS-FULL-01/02 | full-spec 规范字节/摘要跨 Python+Node 一致；指标变更生成不同摘要 | **仅合成数学计算完成，已取得两语言匹配结果** |
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

实测范围：只做了 GitHub HEAD/文档/白名单静态核验及合成 JSON canonical SHA-256 的 Python、Node.js 两个独立计算路径；无 GitHub Actions、完整 RunSpec freeze 实现、持久 journal crash 注入、Harness/Experiment 运行、PRNG 分布采样器全向量、物理 Validation/UQ 的成功证据。**不允许将 JCS-FULL-01/02 或 G01–G13 数学通过写成 M2/R3/研究 PASS**。

签字工作：AI-C 对 `LP4/HKDF`、PRNG/draw addressing/stream 与 SPEC-01/02 的相容性明确 `ACCEPT/CHANGES_REQUESTED`；EXP-01 确定 ExperimentPlan 分配表与 retry policy；ARCH-02 审核 RunRecord durable writer/fencing；ARCH-03 审核 stream manifest 与 MetricDefinition 锁；AI-R 完整负例/崩溃独立评审；主控冻结 ADR。未会签前保持 **HOLD / NO-FREEZE**。
