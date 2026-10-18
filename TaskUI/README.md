# TaskUI — 面向 AI 开发的任务驱动 UI/UX 规则包

**版本：1.0.0（最小可运行规范）**  |  **技术栈无关**  |  **Python 标准库校验，无第三方依赖**

TaskUI 不是一个组件库，也不是固定布局模板。它要求 AI 在写 React/Vue/Tauri/Electron 界面前，先说明**谁要完成什么任务、对象和操作如何组织、入口为什么放在这里**，并通过静态规则与人工任务验证两道关卡。

## 快速使用

1. 把本目录的 `AGENTS.md`、`core/`、`patterns/`、`adapters/`、`schemas/`、`tools/` 等放进项目，或将整个 TaskUI 目录作为项目规则资料。
2. 告诉 Codex/Cursor：**“阅读 TaskUI/AGENTS.md，先执行 G0/G1 设计阶段，不要直接写前端页面。”**
3. 从 `examples/good.project.taskui.json` 复制为你自己的 `project.taskui.json`，替换用户任务、功能、工作区、操作入口和设计证据。
4. 运行检查：

```bash
python tools/taskui_check.py examples/good.project.taskui.json
python tools/taskui_check.py examples/good.project.taskui.json --strict
python -m unittest discover -s tests -v
```

对于实际项目：

```bash
python TaskUI/tools/taskui_check.py project.taskui.json --strict
```

> 路径约定：`design_evidence` 中的相对路径，相对于**manifest JSON 文件所在目录**解析。

## 文件结构

```text
TaskUI/
├── AGENTS.md                        # AI 编码助手入口规则
├── README.md                        # 使用指南
├── core/
│   ├── 00-task-analysis.md          # 用户任务与对象建模
│   ├── 01-placement.md              # 功能入口决策原则
│   ├── 02-layout-interaction.md     # 工作区、交互、视觉约束
│   └── 03-gates.md                  # G0–G3 阶段门与审查证据
├── patterns/                        # 布局模式（可以组合）
├── adapters/                        # Web、桌面与触摸设备差异
├── schemas/project.schema.json     # JSON Schema，供 IDE / 外部工具用
├── tools/taskui_check.py           # 标准库静态校验器
├── prompts/design.md               # 设计助手提示词
├── prompts/review.md               # 审查助手提示词
├── checklists/human-review.md      # 人工可用性验收单
├── examples/                        # 一个通过示例和一个反例
├── tests/                           # 自动测试
└── .github/workflows/taskui.yml    # 可选 GitHub Actions 样例
```

## 机器能检查什么

`taskui_check.py` 会检查清单的结构、必填信息、唯一 ID、任务与操作引用、屏幕及区域引用、主工作区配置、高风险操作保障、变更反馈、菜单深度，以及一些**启发式警告**（例如高频操作只藏在深层菜单）。它会打印可定位的错误代码和清单路径；`--json` 可供 CI/AI 读取，`--strict` 将警告也视为失败。

## 机器不能证明什么

**静态检查通过 ≠ 界面好用。** 本脚本不解析真实的 Vue/React 组件树，不读取运行时布局，不测量点击次数，也不会自动证明焦点操作、键盘可达性、触控尺寸、响应式设计或工作区视觉层级正确。这些必须依据 `checklists/human-review.md`，对真实界面运行任务脚本、截图及键盘测试；证据文件的存在只证明*提交了文件*，不证明其内容真实或结论正确。

## 核心原则

- **任务驱动，而非功能堆砌**：先列高频任务与对象，再决定导航和入口。
- **主工作区优先**：高频工作不应被装饰区和次要功能挤压。
- **按上下文分层**：全局操作归全局；对象操作靠对象；高级功能按需出现。
- **布局模式可组合**：编辑器、对象管理器、流程、监控、向导没有统一的固定页面。
- **可追溯决策**：每个核心任务可追溯到操作、屏幕、入口及验收动作。
- **容错与可访问性**：反馈、撤销、键盘、焦点和可访问性不是事后美化。

## 适配建议

- Codex：在项目根 `AGENTS.md` 中添加“遵循 `TaskUI/AGENTS.md`”，或直接使用本文件作项目规则。
- Cursor：将本文的规则纳入项目规则文件；引用 `TaskUI/AGENTS.md` 和 `TaskUI/core/`，无需复制全部内容到每条提示词。
- 其他 AI 开发工具：先附上 `AGENTS.md` 与适合的软件模式，再提供当前项目的 `project.taskui.json`。

## 注意

本框架是用于约束设计决策的**工作流 + 可审查清单**，不是一个能自动推断真实用户行为的万能评分器。没有真实任务验证，任何规则分数都只能说明声明的一致性。

> `steps`/`step_budget` 指 manifest 中定义的**抽象任务操作数**，不是鼠标点击次数或任务耗时；任何真实步数/时间评估都需要运行任务脚本。`test_plan.status` 也只是项目方声明，检查器不核实其真实性。
