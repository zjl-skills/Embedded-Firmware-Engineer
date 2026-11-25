# Embedded Firmware Engineer

面向 MCU 固件开发与工程接手的 Codex Skill，覆盖原理图与芯片资料核对、架构设计、固件开发、移植和验证交付。

## 主要功能

- 识别 MCU、工具链、RTOS 和构建入口，登记硬件资料并检查版本、冲突和变更影响。
- 采用六层架构划分模块和接口，支持驱动、裸机和 RTOS 开发，以及跨 MCU 移植与构建调试。
- V1.1 提供 10 个 Python 命令，新增可定位的资料解析、协作检查和结构化测试证据，增强单位、范围与变更影响核对。
- 提供 3 种工作模式、9 个子 Agent 角色模板，以及需求、接口、测试和交接模板。

## 快速开始

1. 将完整的 `embedded-firmware-engineer/` 目录复制到目标仓库的 `.agents/skills/`，或复制到用户级 `~/.agents/skills/`。
2. 在目标项目中打开 Codex，通过 `$embedded-firmware-engineer` 调用 Skill。

```text
使用 $embedded-firmware-engineer 接手当前项目，采用 B 模式。
核对原理图和芯片版本，定位构建入口，并列出需要确认的资料缺口。
```

自动化脚本需要 Python 3.10 或更高版本。工程接手命令和子 Agent 配置见 [使用说明](embedded-firmware-engineer/README.md)。

## 示例与验证

三个模拟工程分别覆盖 GPIO 心跳、FreeRTOS 队列替身和移植前后的 UART 行为。 [STM32 裸机](embedded-firmware-engineer/examples/baremetal_stm32/README.md) · [GD32 + FreeRTOS](embedded-firmware-engineer/examples/freertos_gd32/README.md) · [STM32 → CH32 移植](embedded-firmware-engineer/examples/existing_project_migration/README.md)

在仓库根目录运行以下命令。示例另需 Git 和宿主 GCC。

```sh
python -X utf8 -B -m unittest discover -s embedded-firmware-engineer/tests -v
python -X utf8 -B embedded-firmware-engineer/examples/run_examples.py --cc gcc
```

示例默认在临时目录运行。给第二条命令追加 `--work-dir build/example-runs` 可保留工程副本、构建产物和验证日志，指定的输出目录须尚未创建。

## 项目文档

[Skill 定义](embedded-firmware-engineer/SKILL.md) · [V1.1 验收](V1_1_ACCEPTANCE_REPORT.md) · [V1.1 测试](V1_1_TEST_REPORT.md) · [V1.1 差距分析](V1_1_GAP_ANALYSIS.md) · [V1.0 验收](embedded-firmware-engineer/FINAL_ACCEPTANCE_REPORT.md) · [变更记录](embedded-firmware-engineer/CHANGELOG.md) · [Apache-2.0 许可证](LICENSE)
