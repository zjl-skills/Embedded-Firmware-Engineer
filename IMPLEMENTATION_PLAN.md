# Embedded Firmware Engineer 实施计划

## Phase 0 环境和规范核对

核对日期为 2026-11-25，时区为 Asia/Shanghai。开发工作区 `E:\zjl-skills\Embedded-Firmware-Engineer` 的 Git 工作树干净，已存在两行项目说明 `README.md` 和 Apache-2.0 `LICENSE`。保留原说明及许可证。计划将源码和交付物放在新建的 `embedded-firmware-engineer/`，仅在原 README 追加入口。

| 项目 | 核对结果与实施决定 |
| --- | --- |
| Codex | Windows Desktop 内的 CLI 报告 `0.171.0-alpha.13.2`。`--help` 显示应用服务和调试入口，桌面会话提供子 Agent 工具。CLI 访问默认临时目录时有权限提示，将用隔离目录测试发现和配置。运行时权限、并发数和功能仍以实际宿主配置为准。 |
| Skill 规范 | `SKILL.md` 使用 YAML frontmatter 和 Markdown。名称与目录同名，入口保留 `name`、`description` 和适用元数据。`agents/openai.yaml` 用于界面元数据和调用策略。 |
| 安装和发现 | 发布源码为工作区下的 `embedded-firmware-engineer/`。目标工程的安装路径为 `<目标仓库>/.agents/skills/embedded-firmware-engineer/`，用户级发现位置为 `C:\Users\zjl\.agents\skills\embedded-firmware-engineer\`。当前两处开发工作区目标与用户级同名路径均未发现现有 Skill。验收在隔离项目验证 Codex 发现，交付不修改实际用户配置。 |
| 子 Agent | 定义模板使用独立 TOML，包含 `name`、`description`、`developer_instructions`。实例配置从项目 `.codex/agents/` 或用户 `~/.codex/agents/` 加载。模板放在包内 `agents/specialists/`，只有安排协作且目标运行时支持时才注册使用。 |
| Python 和测试 | `python` 为 3.10.11，`unittest` 和 PyYAML 6.0.3 可用，当前 Python 未安装 pytest。项目命令与单元测试只依赖标准库。PyYAML 用于本机 Skill 校验工具。 |
| 编译及解析工具 | Git 2.47.1、GNU Make 和宿主 GCC 14.2.0 可用。当前 PATH 未发现 Arm GCC、Keil `UV4`、`IarBuild`、QEMU、CMake 或 `pdftotext`。Python 环境未发现 `docx`、`openpyxl`、`pypdf`、`fitz`。文档规范按宿主能力路由，示例使用明确的宿主模拟。 |

规范来源为 [Agent Skills Specification](https://agentskills.io/specification)、[Codex Skill 发现及元数据](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)、[Codex 自定义子 Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) 和本机 `skill-creator` 的 `openai_yaml.md` 与 `quick_validate.py`。

## 实施顺序及检查点

| 阶段 | 实现 | 阶段检查 |
| --- | --- | --- |
| 1 | Skill 入口、UI 元数据、模式与证据规则、Reference 索引。 | 运行本机 Skill 校验器，解析 YAML 并检查入口路由。 |
| 2 | 工程管理、文档/原理图、证据与信息冲突、六层接口、固件与平台、构建调试、质量与交付 Reference。 | 核对覆盖范围、引用、角色边界与可验证的输出。 |
| 3 | 九个原生 TOML 模板、调度与文件所有权、Git 协作、逻辑会话与交接。 | 解析 TOML 并比对已公开字段，尽可能用本机 CLI 验证加载，记录实际运行限制。 |
| 4 | 工程模板与七个 Python CLI。JSON 持久化注册表、架构映射、追溯连线和已提取事实。Markdown 保存人审的基线、问题、决策和交接。 | 检查各命令帮助、初始化的幂等性和一个最小工程的 CLI 流程。 |
| 5 | 使用 `unittest` 覆盖正常与异常路径，按照失败证据修复。 | 全量测试、Python 和工程配置检查。 |
| 6 | STM32 裸机、GD32 + FreeRTOS、已有工程跨 MCU 移植三个模拟项目。 | 分别运行 CLI、资料差异与冲突检查、会话恢复、构建链接及行为测试。在授权和运行时支持时安排独立子 Agent 前向验证。 |
| 7 | 发布 README、变更记录、验收报告。 | 逐项复核交付、证据和未验证范围，保留现有仓库内容。 |

## 自动化边界

- 确定性自动化覆盖目录扫描与证据标注、资料哈希和可读文本比对、结构化工程事实冲突、需求链关联、静态层间依赖以及工程完整性。默认以报告或预览输出，初始化只填补缺失文件，登记或推进哈希基线需要显式命令。
- 资料解析、语义影响、故障根因、运行时 Agent 调度、交付评审采用按需 Reference，取决于实际输入和宿主。项目资料字段、批准状态和实板结果由证据支持并在项目内持久化。
- 专有格式导出、商业工具链、真实 MCU、探针及烧录需要相应资料、工具或授权。本期用可检查的模拟资料和宿主测试验证流程，验收报告逐项登记未执行的目标环境验证。
