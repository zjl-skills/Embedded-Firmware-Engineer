# Embedded Firmware Engineer

`embedded-firmware-engineer` V1.0 是面向 MCU 固件的 Codex Skill。它为项目接手、原理图核对、需求、架构、驱动、裸机/RTOS、移植、构建调试和协作交付提供约定与工具。默认中文，默认工作模式 B。小任务可以直接使用与改动有关的核对和验证流程。

## 安装与调用

将完整的 `embedded-firmware-engineer/` 目录复制到目标仓库的 `.agents/skills/`，或复制到用户级 `~/.agents/skills/`。启动 Codex 后可通过 `$embedded-firmware-engineer` 明确调用。打开会话时如果还没有发现新 Skill，可以重新打开。仓库级和用户级发现及重复名称行为以运行时为准。[Codex Skill 发现规范](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)

常见调用用语为「使用 `$embedded-firmware-engineer` 接手当前项目，采用 B 模式。核对原理图和芯片版本，定位构建入口及影响本模块的资料缺口。」

需要自定义子 Agent 时，从 [`agents/specialists/`](agents/specialists/) 选取角色，按授权复制到目标工程 `.codex/agents/` 或用户 `~/.codex/agents/`。先核对现有同名文件。界面元数据在 [`agents/openai.yaml`](agents/openai.yaml)。在提供通用子 Agent 的宿主可按角色任务包分派，其余环境可顺序运行同一流程。[协作与恢复](references/08_multi_agent/collaboration.md)

## 接手工程

自动化仅需要 Python 3.10+。下面是在目标固件仓库中运行的 PowerShell 示例，将 `$efwScripts` 改为已安装的 `scripts` 目录。

```powershell
$efwScripts = 'C:\work\embedded-firmware-engineer\scripts'
python "$efwScripts/scan_project.py" .
python "$efwScripts/init_project.py" . --mode B --module MOD-BOARD
python "$efwScripts/inventory_documents.py" .
python "$efwScripts/inventory_documents.py" . --update-registry --capture-text
python "$efwScripts/check_document_changes.py" . --fail-on-change
```

初始化后可将 `.embedded/config.json` 的 `document_roots` 限定到受控资料目录，如 `docs` 或 `hardware`。先审查登记预览和快照范围，再执行正式登记。沿项目现有格式工作时可通过 `--state-dir` 选择兼容的管理目录。填写工程上下文、基线、资料权威性和追溯关联后，可执行以下检查。[命令、退出码及数据契约](references/00_core/automation.md)

```powershell
python "$efwScripts/generate_traceability.py" . --format md --output .embedded/reports/traceability.md
python "$efwScripts/check_architecture.py" .
python "$efwScripts/validate_project.py" . --check-hashes --strict
```

工程事实以文档、版本、范围和定位为依据。手动提取的事实由一致性检查核对结构化明示值。信息冲突在 `ISSUES.md` 和 `DECISIONS.md` 处理。资料变动先审查哈希、版本、正文差异和关联影响，批准后通过 `--accept DOC-ID=SHA256` 推进指纹并同步设计、测试和交接。[资料治理与一致性](references/02_document_analysis/consistency.md)

## 复现验收

从本目录执行以下命令。工程演练需要 Git 及支持 GCC/Clang 参数的宿主 C 编译器。`--work-dir <新目录>` 可保留每个工程副本、生成的状态与完整命令日志。`--case` 可选择指定案例。

```text
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B examples/run_examples.py --cc gcc
```

三个案例覆盖 [STM32 裸机](examples/baremetal_stm32/README.md)、[GD32 + FreeRTOS](examples/freertos_gd32/README.md) 和 [现有工程移植](examples/existing_project_migration/README.md)。实板、目标 SDK、工具链和正式验收依实际项目验证。结果及限制见 [最终验收报告](FINAL_ACCEPTANCE_REPORT.md) 和 [变更记录](CHANGELOG.md)。
