# 模拟器件约束

Revision: SIM-1
MCU: CH32V203C8T6
Interface: UART_LOGIC_TX

两个宿主替身使用不同的内部返回规则，通过共同 `uart_port_try_write` 映射到接口状态。需分别核对真实 MCU 的 UART 资源、芯片修订、时钟、启动和编译 ABI。模拟符号与真实焊盘没有映射。[ST Datasheet](https://www.st.com/resource/en/datasheet/stm32f103c8.pdf) · [WCH CH32V203 SDK 及参考设计](https://github.com/openwch/ch32v20x)
