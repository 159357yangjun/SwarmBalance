# VVE-01｜证据引用及声明契约（PROPOSED）

```yaml
claim:
  claim_id: claim:example
  research_question: "指定配送条件下两策略超时率有无差异？"
  intended_use: "低空物流离线策略研究"
  scope: {world_ref: pinned, scenario_ref: pinned, model_lock: pinned}
  status: NOT_ASSESSED
  analysis_ref: sha256:placeholder
  run_refs: []
  dataset_provenance_refs: []
  validation_refs: []
  uq_refs: []
  limitations: ["尚未完成现实模型确认"]
```
以上仅为字段示例，placeholder 并非真实哈希。EvidenceStore 应以稳定哈希记录内容，保留原件与转换链，拒绝悬挂引用。每项证据记录 source_version, method, sample/domain, reviewer, accepted_scope, errors, timestamp。缺失证据必须标为 NOT_ASSESSED、FAILED 或 INSUFFICIENT，不以空列表表示验证通过。

接口：inspect_claim(claim_ref)->EvidenceGapReport；verify_links(bundle)->IntegrityReport；assess_scope(claim,validation_records)->ScopeDecision；produce_package(claim_refs)->PortableEvidenceManifest。

兼容边界：ARCH-03 ModelManifest 声明 required fields、unit、CRS、dt、assumptions 与 evidence refs；ARCH-02 RunRecord 锁定 exact hashes 和日志；EXP-01 AnalysisRecord 声明纳入样本、统计方法、comparison gate。VVE 不改写 WorldState、不驱动 Harness、不运行 scheduler。

审查负例：真实来源数据却外推未覆盖风速；训练数据当独立验证集；两算法指标定义不同；参数单位不匹配；失败 run 静默排除；无校准条件却声称能预测现实；随机种子相同但随机流消费不同。
