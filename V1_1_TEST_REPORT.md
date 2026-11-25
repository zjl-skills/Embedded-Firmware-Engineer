# V1.1 测试报告

基线 `700f9d5d405de24c4fabfb4634019412de5892ae`，开发分支 `feature/v1.1-engineering-enhancement`。计划和原始基线见 [差距分析](V1_1_GAP_ANALYSIS.md)。本地使用 Windows、Python 3.10.11、GCC 14.2.0。可选 PDF 后端为 `pdfplumber` 0.11.10。

| 阶段 | 已执行检查及结果 |
| --- | --- |
| 0 | V1.0 全量 38 项，37 通过、1 跳过，命令退出 0。Skill 格式和三个原始示例通过。 |
| 1 | 8 项解析测试通过。测试 PDF 降级与实装 PDF 后端两条路径，核对页定位、无文本页、XLSX 公式缓存、DOCX 图像/表格、PPTX 页序、Draw.io、VSDX、EDA 网表、SVG 候选、源码和不支持格式。 |
| 2 | 4 项单位和范围测试、6 项文档变更测试通过。覆盖十类工程量、开闭区间、百分比和绝对容差、版次/变体、P0 处理、追溯到交付及只读输出。 |
| 3 | 3 项协作测试及真实三个 Git 工作树的合并通过。接口哈希一致，实际发现故意加入的所有权冲突，各工作树恢复四份记录，宿主集成输出 `PASS serial collaboration`。 |
| 4 | 6 项测试证据测试通过。验证日志和输入篡改、实际失败、错误需求/验证类别、旧证据兼容及授权记录变更。原三个示例用新证据执行通过。 |
| 5 | Skill validator 和本地 CI 元数据/内链/语法/10 个 CLI 帮助检查通过。全量结果见下段。 |

本地全量 `unittest` 共 63 项，62 通过、1 跳过，退出 0。原生链接夹具在台式沙箱没有权限。替代测试实际覆盖 Windows 设备名及别名、UNC/驱动器/数据流和路径越界，另用模拟重定向及 reparse 属性验证应用分支。真实 NTFS 链接行为以具备权限的运行记录为准。

## 实际 Codex 与 Git 演练

协调者锁定接口并在独立临时 Git 工程创建三个任务工作树。Hardware Analyst 只读复核模拟 `UART_TX_SIM` 网表、来源和可用范围，Architecture Designer 确认模块及验收。Driver Developer、Firmware Developer 和 Test Engineer 实际并行编写各自 C 文件与交接。Code Reviewer 核对工作树、接口哈希、覆盖和集成结果，并指出提交前快照应与任务最终提交分开记录。演练器已修正并重跑。

实际协作基线 `afa2d51f2296ede539d7aeb7c422eed8772880cc`，集成提交 `65a5a9db928f7861be96e35bfc4560f75a23b5c7`。三个任务各仅变更源或测试文件和自己的交接。限于并发槽位，前置角色和独立审查按依赖分批。调用的是当前 Codex 通用子 Agent 接口，专业职责由各自任务包承载。[可重跑演练](embedded-firmware-engineer/examples/collaboration/README.md)

## 本地复现

```sh
python -m pip install PyYAML tomli pdfplumber
python -X utf8 -B .github/check_skill.py
python -X utf8 -B -m unittest discover -s embedded-firmware-engineer/tests -v
python -X utf8 -B embedded-firmware-engineer/examples/run_examples.py --cc gcc
python -X utf8 -B embedded-firmware-engineer/examples/collaboration/run_collaboration.py --cc gcc
```

## GitHub Actions

工作流配置 Ubuntu 和 Windows 各四个 Python 版本。PR 上的运行结果待实际回写。[工作流](.github/workflows/ci.yml)
