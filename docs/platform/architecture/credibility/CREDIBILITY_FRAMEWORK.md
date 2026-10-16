# VVE-01｜Validation & Evidence 可信性体系（PROPOSED v0.1）

状态：设计草案，不能被解读为模型已验证。基线 master@2ab60c69a806a22d7ba20353dee0571752a0e8e5。

## 四个不同评价对象
1. Verification（软件验证）：给定模型是否被正确编码和执行；证据为单元/边界/回归/不变量及重放。
2. Validation（现实模型确认）：模型相对目标用途与独立现实参照是否足够准确；需记录验证域、数据独立性、误差和接受准则。
3. Uncertainty Quantification：输入测量误差、参数不确定性、结构假设与随机波动对结果的影响；区分认知与随机不确定性。
4. Experiment Integrity：对照、重复、统计估计、排除规则和比较适格性；由 EXP-01 主责，VVE 提供证据审查。

CI SUCCESS、真实日志导入、相同 seed 重现只证明部分工程性质，不能自动提升为现实 Validation PASS。

## 必须维护的对象
DatasetProvenance: source, acquisition time, license, original hash, conversion chain, units, missingness, sample coverage, data partitions。
ModelAssumption: equation or algorithm, inputs/outputs, calibration dataset, parameter sources, simplifying assumptions, operating domain, known failure modes。
VerificationRecord: target version, test case, expected invariant, actual evidence, status, code hash。
ValidationRecord: intended use, reference dataset, calibration/validation split, domain, error metric, acceptance rule, actual error, limitation, reviewer, status。
UQRecord: variables, distributions/ranges and justifications, sampling design, result spread, sensitivity, incomplete assumptions。
EvidenceBundle: immutable content references and provenance DAG from claim to analysis to runs to model/world/scenario/dataset/code。
CredibilityClaim: text, scope, confidence qualifier, limitations, evidence refs, reviewer decision; no single global credibility percentage。

## 模型边界
一项 Validation 结论仅对声明的型号、载荷、航线、风场、任务分布、时间窗口和用途成立。外推超出域必须降低主张强度或要求追加证据。无法独立验证的数据标注 UNKNOWN/NOT_ASSESSED，不能被标为 PASS。

## 最小门禁
V0：数据来源和模型版本完整；
V1：软件规则/不变量验证有执行证据；
V2：目标模型与独立参照做适用性校验；
V3：不确定性与统计结论在明确范围内可解释。
可发布平台工程版本不等于 V2/V3 达标，研究报告必须对各门单独披露。

## 首期排除
不建立“可信度 98%”单值、不假装支持所有真实场景、不把模型认证当作飞行安全许可、不对缺失数据自动填真实值。
