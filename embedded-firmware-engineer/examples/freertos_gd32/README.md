# GD32 + FreeRTOS 模拟

按 `GD32F303VCT6` 和 FreeRTOS 配置线索接手。`MOD-TLM` 通过 OS 邮箱发送采样，公开接口隔离内核类型。宿主提供单槽队列替身，验证零等待、满/空处理、保留原值和恢复；实际内核、调度、ISR 优先级及硬件接口需另行验证。

从 `examples/` 运行 `python run_examples.py --case freertos_gd32 --work-dir <空缺路径>`。模拟信号 `SAMPLE_READY` 的读图、网表、冲突和同步流程均在临时副本内执行。
