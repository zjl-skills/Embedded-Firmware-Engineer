# 模拟器件约束

Revision: SIM-1
MCU: GD32F303VCT6
Interface: TASK_QUEUE_SAMPLE

单字节采样由任务上下文发布。`SAMPLE_READY` 是上游模拟事件。宿主替身记录零等待要求，既不验证 GD32 的 IRQ 配置，也不执行 FreeRTOS 内核调度。目标需按实际 kernel/port 版本另行核对。[GigaDevice 选型手册](https://www.gd32mcu.com/data/documents/otherDocument/GD32_Series_of_MCUs_Selection_Guide_EN_March_2023.pdf) · [FreeRTOS 官方队列接口](https://github.com/FreeRTOS/FreeRTOS-Kernel/blob/main/include/queue.h)
