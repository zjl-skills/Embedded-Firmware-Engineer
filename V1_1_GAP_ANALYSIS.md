# V1.1 基线与差距分析

基线为 `main` 上的 `700f9d5d405de24c4fabfb4634019412de5892ae`。从该提交创建 `feature/v1.1-engineering-enhancement`。基线的 Skill 内容源自 `537b2b5`，后续基线提交只改动仓库主页和 `.gitignore`。核查范围包括 Skill 入口、13 篇 Reference、界面 YAML、9 份角色 TOML、模板、Python 命令及测试、三个示例、V1.0 验收报告、实施计划和变更记录。

## 基线实测

Windows、Python 3.10.11、GCC 14.2.0。`python -X utf8 -B -m unittest discover -s embedded-firmware-engineer/tests -v` 退出 0，38 项中 37 通过，链接路径保护用例因沙箱无法创建符号链接或 junction 跳过。本机 `quick_validate.py` 通过。`python -X utf8 -B embedded-firmware-engineer/examples/run_examples.py --cc gcc` 退出 0，三个工程和四个宿主配置全部通过。V1.0 的历史 Codex 加载及独立 Agent 验证见 [V1.0 验收报告](embedded-firmware-engineer/FINAL_ACCEPTANCE_REPORT.md)。真实目标构建、实板及跨宿主回归无本次基线证据。

| 范围 | V1.0 现状 | V1.1 设计与核验 |
| --- | --- | --- |
| 资料读取 | 已登记路径、版本线索、散列，示例独立读取 SVG/CSV。通用内容提取、定位模型和能力探测缺失。 | 分格式适配器和统一候选记录。用真实格式夹具验证读取结果、定位和工具缺失时的降级。 |
| 一致性及变更 | 已验证同键同作用域的字面冲突、指纹与追溯遍历。工程单位和容差会被字面比较误判。影响报告没有事实和交付物关系。 | 可比量归一化、数值/适用范围判断、可审查冲突和 Markdown 影响报告。保留原记录、散列与审批入口。 |
| 并行及恢复 | 已有角色、所有权和交接约定。没有自动检查文件重叠、接口漂移或模块当前 Git 状态。 | 增补计划检查与恢复命令。实际运行受宿主并发约束的多角色协作及 Git 隔离、冲突与集成演练。 |
| 验证证据 | `Passed` 与证据文件存在性即可参加需求追溯。 | 执行记录与日志散列、用例/需求绑定、结构化验收记录和严格证据策略。保留 V1.0 台账读取行为与迁移说明。 |
| 质量标准 | 已有分层、可靠性和安全原则，C++ 所有权、ABI 与启动链接复核需细化。 | 增补检查方法、栈堆及中断/并发证据。MISRA 合规以明确版本、工具和偏离记录为依据。 |
| CI | 仓库无 Actions，Windows 链接测试有缺口。 | CI 覆盖 Windows/Ubuntu 与 Python 3.10–3.13，执行 Skill 配置/内链、CLI、单元和三个实编译宿主演练，区分替代路径检查与原生链接检查。 |

## 接口兼容策略

现有七个命令保持位置参数、默认输出和检查退出语义。新增能力走命令或可选参数。现有 `schema_version: 1` 台账保留，新增字段或独立记录可选。Document ID、Requirement ID 和文件指纹延续，升级不批准现场工程的旧决策。新增严格证据记录通过显式文件和策略启用，旧证据需要重测后迁移。以 V1.0 的原测试和样例验证兼容性，再逐阶段执行新测试并记录结果。
