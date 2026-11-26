# 命令与数据契约

运行方式为 `python <Skill目录>/scripts/<命令>.py <项目目录> [选项]`。Python 3.10+，仅依赖标准库。项目目录默认当前目录，可用 `--state-dir <项目相对目录>` 选择已有管理布局。配置文件和跨项目工具的报告使用 UTF-8。项目相对路径使用 `/`，显式管理路径需要留在项目内且经过路径核对。

## 命令

| 命令 | 写入及检查 |
| --- | --- |
| `init_project.py` | 填补缺少的项目模板，已存在文件保留。支持 `--mode A/B/C`（仅新配置）和重复的 `--module MOD-ID`。 |
| `scan_project.py` | 也可用于未初始化工程。列出源码、头文件、构建、启动/链接、配置等，以及带文件、行和匹配内容的 MCU、工具链、SDK、RTOS 候选。内容读取上限 256 KiB，标出限制和跳过项。 |
| `parse_documents.py` | 使用 `--capabilities` 检查可用后端，用 `--file` 逐个指定文件。结果区分提取、部分提取、不可用、未知格式和错误，保留原始定位。[资料解析](../02_document_analysis/analysis.md) |
| `inventory_documents.py` | 默认输出合并后的登记预览。`--update-registry` 只加入新资料，保留既有指纹、状态和版本。`--accept DOC-ID=SHA256` 显式核对并推进既有指纹，可重复。登记写入有锁及并发快照复查。 |
| `check_document_changes.py` | 只读，识别新增、缺失、未建基线、元数据变化、内容变化、可用版本和文本差异。遍历资料、事实、需求、模块及消费者、设计、接口、代码、测试和交付文件。`--format md` 输出待批准的 `DOCUMENT_IMPACT.md`，默认 JSON。`--include-unchanged` 扩大报告，`--fail-on-change` 可用于检查关卡。 |
| `generate_traceability.py` | 检查并生成需求→验收关系。默认 JSON，`--format md` 输出矩阵。可重复 `--scan-code <目录>` 查额外目录中遗漏的 C/C++ 实现文件。 |
| `check_architecture.py` | 读取配置及已登记模块依赖。报告可解析的向上 include、L6 规定限制、模块环、例外、映射覆盖和未解析项。 |
| `validate_project.py` | 检查初始化、配置、资料、追溯与结构化事实。`--check-hashes` 重算活动资料哈希，`--strict` 使警告退出 1。 |
| `check_collaboration.py` | 用可选协作台账核对任务所有权、依赖、锁定接口和实际 Git 状态。`--resume` 输出上下文和交接。[协作检查](../08_multi_agent/collaboration.md) |
| `record_test_evidence.py` | 执行授权 argv，输出执行日志和结构化证据。不同结果使用独立文件。 |

除初始化外，可用 `--output <相对新文件>` 写报告并在 stderr 记录位置，已有输出文件保留。正式登记写入的回执走 stdout。退出码 `0` 表示命令成功且未命中所选关卡，`1` 表示检查发现或静态架构覆盖缺失，`2` 表示参数、输入或 I/O 错误。`validate_project.py` 能在报告中列出的项目配置错误按发现返回 1。扫描遍历避开管理、版本控制目录、用户排除目录和链接/重解析项。架构未解析的外部头和宏、未映射源码单独列出，按工程覆盖评审。

## 配置和台账

所有 JSON 根对象使用 `"schema_version": 1`。以 [`config.json`](../../templates/project/config.json) 为起点。`mode` 为 `A/B/C`，`coding_standard` 可为具体编码规范文件路径。`exclude_dirs` 为目录名列表，`document_roots` 为相对路径列表（`.` 表示项目根）。初始化后修改配置以适配工程目录。目录扫描读取名称和可读内容，命令无需执行仓库脚本。

### `documents.json`

`documents` 数组中的记录包含 `id`、`name`、`path`、`type`、`version`、`scope`、`authority`、`status`、`impact`、`modules`、`requirements`、`related_documents`、`last_checked` 和 `fingerprint`。文件更新时间在 `fingerprint.modified_utc`，`last_checked` 为最近指纹核对时间。`version` 是工程认可的版本，`fingerprint.observed_version` 是文件中的单一明确标记或空值。JSON 资料识别顶层 `version` / `revision` 字符串，其他文本识别明确版本标签。

`authority` 为 `Unreviewed`、`Authoritative`、`Supporting`、`Reference`，`impact` 为 `P0`、`P1`、`P2` 或 `null`。新文件按路径获得 ID，自动设为 `Pending Confirmation`。移动候选比较哈希，核对后可在记录中更新路径并保留 ID。关联 ID 使用已登记的稳定编号。文件未备案时指纹可为 `null`。历史资料仍可登记为 `Outdated`、`Superseded` 或 `Archived`，不参与活动一致性判定。

使用 `--capture-text` 为新增或显式接受的 UTF-8 文本（32 KiB 以内）保存快照，以备下一次比对。快照随登记文件存放，按项目权限保管。编码或格式不支持时记录哈希及比较边界。PDF、Office、EDA 等类型的登记依据扩展名，内容核对和原生比较见 [资料解析](../02_document_analysis/analysis.md)。旧指纹和设计变更评审完成后，使用 `inventory_documents.py … --update-registry --capture-text --accept DOC-ID=<报告中的当前SHA256>`。再由工程所有者同步版本、状态、事实、决策及下游记录。

### `traceability.json`

| 数组 | 记录字段 |
| --- | --- |
| `requirements` | `id`、`title`、`priority`、`status`、`source`（`document` 和 `locator`）、`acceptance`、`links`、可选 `acceptance_evidence` 文件、可选 `decision`。每条 link 指定 `module`、`interface`、`code` 路径列表和 `tests` ID 列表。 |
| `modules` | `id`、`design` 文件、`interfaces`（模块内唯一 `id` 与 `path`）、`code` 路径列表和 `depends_on` 模块 ID 列表。 |
| `tests` | `id`、`path`、`status`（`Not Run`、`Passed`、`Failed`、`Blocked`）和可选 `evidence` 文件。 |

新建台账默认为 `evidence_policy: structured`。`Verified` / `Accepted` 需由已通过且关联正确的执行证据佐证，`Accepted` 另需授权验收记录。`Deferred` / `Rejected` 要有 `decision`。对未纳管的源码可补 `--scan-code`，用项目规则定义覆盖范围。状态定义见 [工程接手与追溯](../01_project_management/workflow.md)。

#### 执行和验收记录

证据记录 `schema_version: 1`、`evidence_type: test_run`、`test_id`、`requirement_ids`、`kind`、`command`（argv）、`working_directory`、`toolchain_version`、`environment`、`started_at`、`finished_at`、`input_sha256`、`expected`、`actual`、`status`、`log_path`、`sha256`。日志与证据分别保留。`expected` 含 `exit_code` 和可选 `stdout_contains`。要求使用 `--input` 添加已登记的测试文件与关键源。把证据路径写入测试行的 `evidence`，使用 `verification_kinds` 表达需求所需验证层。[质量验证](../07_quality_assurance/verification.md)

验收记录 `evidence_type: acceptance`，并含 `schema_version: 1`、`requirement_id`、`decision: Accepted`、`approved_by`、`approved_at`、`authorization`（独立授权依据的 `path` 和 `sha256`）及 `test_evidence_sha256`（所有相关 Test ID 到执行证据 JSON SHA-256 的映射）。在 `acceptance_evidence` 引用此记录。记录须反映已经取得的授权，并保留可核对的授权原文。

#### V1.0 台账迁移与回滚

旧台账继续读取，原 ID 保留。旧的 `Passed` 及文件存在性会在报告中标为 `legacy_unconfirmed`，供历史流程使用。迁移先在 Git 或独立备份保存原 `traceability.json` 和所有旧日志，重跑测试生成新证据并取得必要验收批准。可用 `--require-structured-evidence` 试运行严格校验。确认报告后将 `evidence_policy` 设为 `structured` 并保留旧日志。回滚恢复备份中的台账及路径，保留新版日志，以旧证据状态继续读取。升级沿用版本 1，没有强制结构重写。

### `facts.json`

`facts` 条目含 `id`、`category`、`key`、`scope`、`value`、`state`、`severity`、`source`。`category` 可为 `mcu`、`pin`、`electrical`、`protocol`、`requirement`、`timing`、`architecture`、`version`、`capability`。`key` 表示可比的工程断言，`scope` 确定板版次、运行方式或变体，`value` 为已按约定归一的字符串。`state` 为 `Asserted` 或 `Inferred`，`severity` 为 `P0/P1/P2`，来源包含 `document`、`locator`、`excerpt`。只有活动资料中已指定范围的 `Asserted` 值参与逐组比较。适用范围待确认时填写 `"scope": null`，校验会给出带出处的待核对告警。个别断言说明某份资料的主张，经核对才纳入工程基线。冲突候选带稳定 ID 和各方出处，按 [一致性处置](../02_document_analysis/consistency.md) 记录与复核。

保留原始 `value` 字符串。支持 `3.3V`、`10ms`、`3.0–3.6 V`、`>= 2.7V`、`3.3 V ± 100 mV` 和 `10V ± 5%`。需要明确边界时加 `quantity`，如 `{"min":"2.7","max":"3.6","unit":"V","max_inclusive":false}`。容差使用 `nominal`、`tolerance` 和可选 `tolerance_unit`。温度采用带偏移的换算，温差使用比例换算。`kB`/`KB` 为十进制，`KiB` 为二进制。判断使用精确有理数，归一化结果保留原信息。

可选 `applicability` 接受 `product`、`variant`、`board`、`board_revision` 的单值或列表，以及数字点分 `versions` 的 `min`、`max` 和可选包含状态。已审查的结构化范围可与 `scope: null` 共存。未指定的结构化维度视为该事实在该维度未限定，旧字符串与结构化范围的关系需人工映射。`fact_comparisons` 表示范围及值关系，只有适用范围有交集且定义冲突才生成候选。相交的数值区间和不可比语义应复核。

事实可附 `requirements` 和 `modules` ID。需求可附 `deliverables` 项目相对文件列表。影响跟踪时核对这些引用，提交用户决定后再使用资料登记命令推进指纹。

### `config.json` 的 `architecture`

- `layers` 元素为 `{"prefix": "src/app", "layer": 6, "module": "MOD-APP"}`，`module` 可省略，最具体的相对目录或文件路径优先。
- `include_dirs` 按编译搜索顺序填相对目录。引号头文件优先查源文件目录，尖括号按配置查找。
- `application_forbidden_includes` 填头文件名或 include 路径前缀。`application_forbidden_symbols` 填精确标识符或尾部带 `*` 的前缀，如 `HAL_*`。
- `exceptions` 包含 `rule`、`source`、`target`、`decision`、`rationale`。规则为 `upward_include`、`application_forbidden_include` 或 `application_forbidden_symbol`，按报告中的源文件与目标精确匹配。记录批准 ADR，环依赖需要独立评审、解耦及重新检查。
