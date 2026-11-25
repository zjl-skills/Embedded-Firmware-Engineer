# Embedded Firmware Engineer V1.0 最终验收报告

验收日期为 2026-11-25，时区为 Asia/Shanghai。本次完成 Skill 源码、工程自动化和模拟验证。实板、目标工具链和真实项目验收的边界如下。

## 交付与工程决策

| 位置 | 已交付内容 |
| --- | --- |
| [Skill 入口](SKILL.md)、[专业 Reference](references/) | 中文入口、A/B/C 模式、按任务加载的十三篇参考。覆盖资料治理、工程生命周期、六层架构、平台适配、开发与质量。 |
| [界面元数据](agents/openai.yaml)、[子 Agent 模板](agents/specialists/) | UI 配置和九个独立角色 TOML。项目协调、文件所有权、Git 工作区和逻辑会话流程见 [协作与恢复](references/08_multi_agent/collaboration.md)。 |
| [工程模板](templates/) | 项目与模块上下文、资料和需求台账、架构和接口、ADR、验证、问题、交接和交付。 |
| [Python 自动化](scripts/) | 初始化、扫描、资料登记、变更比对、需求矩阵、分层检查和项目校验。采用标准库，默认只读或创建缺失文件。 |
| [单元测试](tests/)、[案例](examples/) | 七组 CLI 回归测试及三个可复现演练。 |
| [实施计划](../IMPLEMENTATION_PLAN.md)、[使用说明](README.md)、[发行变更](CHANGELOG.md) | 阶段、配置及运行方式。仓库原 README 保留原说明后追加入口，Apache-2.0 许可证保持原样。 |

结构化台账采用四份 UTF-8 JSON，Markdown 保存人工确认的基线、决策、问题和交接。资料受单一登记指纹约束，已有指纹只有在显式批准的 SHA-256 仍匹配时推进。默认六层约束由项目规则适配已有布局。模块会话以项目文件和 Git 为长期记录，执行实例取决于宿主。[数据契约](references/00_core/automation.md)

## 环境与阶段核验

| 阶段 | 实际结果 |
| --- | --- |
| Phase 0–2 | Windows、Codex CLI `0.171.0-alpha.13.2`、Python `3.10.11`、GCC `14.2.0`、Git `2.47.1.windows.1`。完成实施计划、元数据和 Reference 核对。本机 `skill-creator` 校验器使用 `-X utf8` 后通过。隔离项目的 `skills/list` 返回该 Skill，scope 为 `repo`，启用且读取界面元数据。 |
| Phase 3 | 九份 TOML 均通过解析和必需字段检查。本机 app-server 以正确文件启动的配置告警为零，在隔离对照中加入同名副本后，实际加载器给出了九个角色的重名告警。两次独立子 Agent 验证使用本会话提供的通用调度接口与明确职责。 |
| Phase 4–5 | 七个 CLI 的 `--help` 和冒烟路径通过。`unittest` 发现 38 项，37 项通过、1 项跳过、0 失败，退出码 `0`。跳过项为链接路径保护测试，当前 Windows 沙箱不允许创建符号链接或 junction。普通越界路径、已有文件保护和登记并发检查已执行。 |
| Phase 6 | 三个案例运行器退出码 `0`，含七个 CLI、实际宿主编译/链接/行为执行和工程状态同步。独立 Agent 分别从 GD32 原始资料接手及从共享移植副本恢复。 |
| Phase 7 | 复核结构、元数据、Reference 和主要内链，输出本报告、使用说明和版本变更。 |

Agent Skills 和 Codex 的配置依据为其公开规范及本机配置验证结果。[Agent Skills Specification](https://agentskills.io/specification) · [Codex Skills](https://learn.chatgpt.com/docs/build-skills) · [Codex 自定义子 Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)

## 模拟结果

| 工程 | 资料及 P0 流程 | 宿主编译、链接与执行 | 追溯 |
| --- | --- | --- | --- |
| STM32 裸机 | 6 份登记。SVG、网表确认模拟标记 `SIM_PAD_2`，旧说明差异报告 `CF-E945395BEF46`。 | 3 个 C 编译单元、1 次链接和 1 次行为执行通过。覆盖心跳时限、回绕和无效周期。 | `REQ-BM-001` `Verified` |
| GD32 + FreeRTOS | 6 份登记。模拟输入 `SIM_IRQ_3` 的差异报告 `CF-F6BCD46C75C7`。 | 3 个 C 编译单元、1 次链接和 1 次行为执行通过。队列替身覆盖零等待、背压、空态和恢复。 | `REQ-GD-001` `Verified` |
| STM32 → CH32 已有工程移植 | 6 份登记。旧工程配置和上下文被保留，模拟端口差异报告 `CF-411F75C21BEC`。 | 源和目标替身各编译 3 个 C 单元，各链接并执行一次。同一用例覆盖忙态、编码、重试和参数错误。 | `REQ-PORT-001` `Verified` |

演练用可检查的 SVG 标签、CSV 网表和模拟器件约束作为输入。各工程先捕获预期的 P0，再按场景提供的授权修订同步旧说明及指纹，记录影响、ADR 和重新检查。共复核六个模块恢复入口。最终各案例的已映射架构违规、追溯缺口、严格校验错误和告警均为零。化简的测试范围和命令证据按 `--work-dir` 保留在各副本 `.embedded/reports/`。

独立 Hardware Analyst 捕获了旧说明缺失适用板范围和可能的引脚差异，复验宿主队列行为。针对该反馈增加 `scope: null` 的出处告警和单元测试。另一位 Agent 顺序读取四份恢复记录，复核移植副本的 HEAD、文件所有权、接口 v1、两组通过的日志，并重新执行资料漂移和严格校验，均返回 `0`。架构检查、工程台账复核和这些独立检查构成本次代码与资料审查范围。

从 Skill 目录复现核心结果。

```text
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B examples/run_examples.py --cc gcc
```

## 验证范围与待完成项

| 能力 | 状态与边界 |
| --- | --- |
| 工程自动化 | 七个命令已实现并执行。哈希与有限文本比较报告候选影响，支持的版本格式见数据契约。资料解析、语义判断、变更批准、跨团队通知及业务文档同步由工程流程执行。 |
| 信息一致性与追溯 | 自动检查同类别、键和归一化范围内的结构化明示值、出处和关联。数值容差、范围重叠、推断、复杂协议和声明真实性仍需工程核对。状态证据文件存在性可检查，实际证明力由人员评审。 |
| 静态分层 | 可解析 C/C++ include、显式 L6 限制和声明/观察到的模块环已检查。预处理、链接调用图、动态调用、运行时调度和正式 MISRA 合规需要额外工具及人工验证。 |
| 专业文档与 Agent | PDF/图片、Office、专有 EDA 和 Visio 等内容读取取决于对应工具或用户导出。示例验证了可读 SVG、CSV、文本及原生工程配置线索。命名角色配置已经实际加载验证，角色按名称启动及真实工程的长时多线程调度待使用对应宿主复验。用户安装位置仅作为发布路径，发现测试在隔离仓库完成。 |
| 目标与硬件 | 本次结果适用于宿主 GCC 模拟。Keil、IAR、Arm/RISC-V 目标工具链、实际 FreeRTOS 内核/port、实板时序、功耗、IRQ/DMA、烧录和板级验收需实际工程、工具、设备及授权。其它宿主系统待运行同一套回归。 |

实际项目的下一步为确认工作模式、板卡版本、官方资料、目标 SDK 和构建入口，逐项开展目标编译链接、硬件测量与需求签收。
