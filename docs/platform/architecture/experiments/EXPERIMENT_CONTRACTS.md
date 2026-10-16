# EXP-01｜逻辑接口与失效语义（PROPOSED）

以下伪类型不是实现代码。
```python
class ExperimentDefinition:
    experiment_id: str
    revision: int
    research_question: str
    hypothesis: str
    base_world_ref: str
    base_scenario_ref: str
    treatments: tuple
    controlled_variables: tuple
    metric_definition_refs: tuple
    replication_plan: object
    analysis_plan: object
    scope_and_exclusions: object

class ExperimentService:
    def validate(self, definition) -> "DesignValidationReport": ...
    def plan(self, definition, frozen_resources) -> "ExperimentPlan": ...
    def dispatch(self, plan, harness_runner) -> "BatchRecord": ...
    def analyze(self, batch_record, metric_definitions) -> "AnalysisRecord": ...
```
每个 Run 的输入为不可变 FrozenRunSpec；ExperimentRunner 不依赖 web session 和模块全局配置。RunRecord 必含状态 PREPARED/RUNNING/SUCCEEDED/FAILED/CANCELLED/INVALIDATED，错误定位和 retry attempt。

输入校验包括版本锁、模型所需字段、单位/CRS、时域、实验因子、对照变量、数据分组边界、重复策略、指标定义与比较规则。出现有因子的非受控变化、缺失指标、未声明的模型版本、非法随机流配对时返回结构化 NOT_COMPARABLE，并保留原始结果，不伪造排名。

向 ARCH-02 请求：create/assemble/initialize/step or run-to-end/result，隔离各 Run StateStore。向 ARCH-03 请求：组件锁、MetricDefinition/MetricSample 语义稳定。向 VVE-01 交付 claims + provenance refs，不直接产生 V&V 结论。