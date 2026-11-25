# UART 模块协作演练

模拟网表为 `board.net`。公开契约 `include/serial_link.h` 预先锁定。L3 UART 单槽发送模型保存一次提交，L6 应用对采样做异或编码并经公共契约提交。演练按文件所有权拆分 Driver、Application 和测试，协调者合并并运行宿主测试。

验收输入为 `0x31`，期望发送 `0x94`。忙时拒绝再次发送并保留旧值，释放后允许再次提交，空对象报告参数错误。全部值及连接为模拟定义，目标 SDK、引脚复用、寄存器和真实 UART 时序需另行核对。

在仓库根运行 `python -X utf8 -B embedded-firmware-engineer/examples/collaboration/run_collaboration.py --cc gcc`。本地 Git 隔离出三个任务工作树，检测故意加入的所有权冲突，读取四份恢复记录，核对锁定头、合并并执行严格 C11 宿主构建。加 `--work-dir <新目录>` 保留演练。真实角色分派时先用 `--prepare` 生成工作树，再由协调者用 `--finish` 检查并集成。
