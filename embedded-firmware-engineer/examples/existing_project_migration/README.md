# 已有工程跨 MCU 移植模拟

从 STM32 的 Keil 配置和预先存在的项目上下文恢复，识别 CH32V203 目标。两种宿主 BSP 替身通过同一串口契约处理忙态和成功，使用同一 Service 和测试验证字节编码及重试语义。

从 `examples/` 运行 `python run_examples.py --case existing_project_migration --work-dir <空缺路径>`。案例保留原有 `legacy.uvprojx`，回归两条宿主构建。目标 SDK、编译器、启动、链接、IRQ 和真实 UART 仍需在实际移植项目验证。
