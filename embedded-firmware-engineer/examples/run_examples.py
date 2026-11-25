"""在独立副本中执行三个嵌入式工程演练并记录证据。"""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
CASES = ("baremetal_stm32", "freertos_gd32", "existing_project_migration")
NOTE = "docs/pin-note.md"


def expect(condition, message):
    if not condition:
        raise RuntimeError(message)


def execute(root, command, *, expected=0, journal=None):
    result = subprocess.run(command, cwd=root, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=45)
    if journal is not None:
        journal.append({"command": command, "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
    expect(result.returncode == expected, f"{root.name}: {command} → {result.returncode}\n{result.stderr}\n{result.stdout}")
    return result.stdout.strip()


def command(root, script, *options, expected=0):
    args = [sys.executable, "-B", str(SCRIPTS / f"{script}.py"), str(root), *options]
    return json.loads(execute(root, args, expected=expected))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_text(path, body):
    path.write_text(body, encoding="utf-8", newline="\n")


def fixture_fields(path):
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(": ")
        if separator and key in {"Revision", "MCU", "Interface", "ID", "Acceptance", "Signal", "Pad"}:
            fields[key] = value
    return fields


def inspect_fixture(root, scenario):
    with (root / "docs/netlist.csv").open(encoding="utf-8", newline="") as handle:
        connection, = csv.DictReader(handle)
    picture = ElementTree.parse(root / "docs/schematic.svg")
    visible = {element.get("id"): element.text for element in picture.iter("{http://www.w3.org/2000/svg}text")}
    device = fixture_fields(root / "docs/device.md")
    note = fixture_fields(root / NOTE)
    expect(connection["scope"] == visible["board-scope"] == scenario["scope"], "原理图和网表范围不一致")
    expect(connection["signal"] == visible["signal-label"] == note["Signal"], "原理图、网表和说明的信号不一致")
    expect(connection["pad"] == visible["board-pad"] and connection["pad"].startswith("SIM_"), "模拟原理图和网表定义不一致")
    expect(note["Pad"] != connection["pad"] and note["Revision"] == "A", "预期的旧说明冲突缺失")
    expect(device["MCU"] in scenario["mcus"] and bool(device["Interface"]) and device["Revision"] == "SIM-1", "模拟器件约束不匹配")
    return connection, visible, device, note


def baseline_git(root, git):
    execute(root, [git, "init", "-q"])
    execute(root, [git, "add", "--", "."])
    execute(root, [git, "-c", "user.name=Embedded Fixture", "-c", "user.email=fixture@example.invalid",
                   "-c", "core.hooksPath=.git/no-hooks", "commit", "-q", "--no-gpg-sign", "-m", "Fixture baseline"])
    return execute(root, [git, "rev-parse", "HEAD"])


def prepare_trace(root, scenario, documents):
    requirement = fixture_fields(root / "docs/requirements.md")
    tests = [{"id": "T-" + profile["id"], "path": scenario["test_source"], "status": "Not Run"}
             for profile in scenario["profiles"]]
    modules, links = [], []
    for module in scenario["modules"]:
        interface = "IF-" + module["id"].removeprefix("MOD-")
        modules.append({"id": module["id"], "design": "docs/design.md",
                        "interfaces": [{"id": interface, "path": module["interface"]}], "code": module["code"],
                        "depends_on": module["depends_on"]})
        links.append({"module": module["id"], "interface": interface, "code": module["code"],
                      "tests": [test["id"] for test in tests]})
    return {"schema_version": 1, "modules": modules, "tests": tests, "requirements": [
        {"id": requirement["ID"], "title": "模拟场景行为", "priority": "P1", "status": "Implemented",
         "source": {"document": documents["docs/requirements.md"]["id"], "locator": "Acceptance 行"},
         "acceptance": requirement["Acceptance"], "links": links}
    ]}


def record_facts(state, documents, wire, note):
    facts = [{"id": ident, "category": "pin", "key": wire["signal"], "scope": wire["scope"], "value": pad,
              "state": "Asserted", "severity": "P0", "source": {"document": documents[path]["id"],
                                                                  "locator": location, "excerpt": excerpt}}
             for ident, path, pad, location, excerpt in (
                 ("FACT-NET", "docs/netlist.csv", wire["pad"], "行 2 / pad", f"{wire['reference']},{wire['signal']},{wire['pad']}"),
                 ("FACT-NOTE", NOTE, note["Pad"], "Pad 行", f"Pad: {note['Pad']}")
             )]
    write_json(state / "facts.json", {"schema_version": 1, "facts": facts})


def resolve_fixture(root, state, documents, wire, note, trace, reports):
    record_facts(state, documents, wire, note)
    initial = command(root, "validate_project", "--check-hashes", expected=1)
    conflict, = initial["fact_conflicts"]
    expect(conflict["severity"] == "P0" and initial["errors"] == 1, "初始验证须仅报告预期的 P0 冲突")
    write_json(reports / "conflict.json", conflict)
    affected = ", ".join(module["id"] for module in trace["modules"])
    write_text(state / "ISSUES.md", f"# 工程问题\n\nISS-SIM-001 / {conflict['id']} / P0。\n"
               f"网表行 2 `{wire['pad']}`，旧说明 Pad 行 `{note['Pad']}`。暂停 {affected} 的映射依赖。"
               "预期风险为模拟信号路由错误。规格分析及纯逻辑设计可继续。\n")

    revision = root / "fixture_updates/pin-note.md"
    updated = fixture_fields(revision)
    expect(updated["Pad"] == wire["pad"] and updated["Signal"] == wire["signal"] and updated["Revision"] == "B", "模拟修订未满足审批条件")
    write_text(state / "DECISIONS.md", f"# 工程决策\n\nADR-SIM-001（场景预设批准）采用 {wire['scope']} 的受控网表。"
               "可选方案为保留旧映射或同步旧说明。图面可见标签与批准网表一致，选择同步说明并复核代码、接口和用例。"
               "真实板卡仍需提供实际设计和厂商资料。\n")
    shutil.copyfile(revision, root / NOTE)
    changed = command(root, "check_document_changes", "--fail-on-change", expected=1)
    drift, = changed["records"]
    expect(drift["kind"] == "content_changed" and drift["version_comparison"]["state"] == "changed"
           and drift["text_difference"]["state"] == "changed_text", "未生成预期的哈希、版本与正文差异")
    expect(drift["impact"]["requirements"] == [trace["requirements"][0]["id"]]
           and set(drift["impact"]["tests"]) == {test["id"] for test in trace["tests"]}, "影响链缺少需求或测试")
    write_json(reports / "change-impact.json", drift)
    note_id = documents[NOTE]["id"]
    accepted = command(root, "inventory_documents", "--update-registry", "--capture-text", "--accept", f"{note_id}={drift['current']['sha256']}")
    expect(accepted["refreshed"] == [note_id], "未按已审查的 SHA-256 推进资料")
    # 重新读取并保留 CLI 已原子写入的指纹。
    updated_registry = read_json(state / "documents.json")
    row = next(doc for doc in updated_registry["documents"] if doc["id"] == note_id)
    row.update(version="B", status="Valid", authority="Supporting")
    write_json(state / "documents.json", updated_registry)
    record_facts(state, documents, wire, updated)
    with (state / "ISSUES.md").open("a", encoding="utf-8") as handle:
        handle.write("\n已按 ADR-SIM-001 同步 Rev B 和指纹，待最后回归与集成检查。\n")
    write_text(state / "CHANGELOG.md", f"# 工程变更\n\nADR-SIM-001 同步 `{NOTE}` A → B。影响、旧新 SHA 和证据在 `reports/change-impact.json`。\n")
    expect(command(root, "check_document_changes", "--fail-on-change")["active_changes"] == 0, "资料仍存在未处理漂移")
    return conflict["id"]


def prepare_handoffs(root, state, scenario, baseline, git):
    if "existing_context" not in scenario:
        write_text(state / "PROJECT_CONTEXT.md", f"# 项目上下文\n\n模拟范围 {scenario['scope']}。B 模式。按公开接口执行宿主验证。\n")
    write_text(state / "PROJECT_BASELINE.md", f"# 项目基线\n\nGit `{baseline}`。模拟板 `{scenario['scope']}`。"
               "批准模拟网表和资料修订见 ADR-SIM-001。使用宿主 C 工具链。\n")
    registry = ["# 协作登记", "", "协调者持有公共接口、构建及集成。Hardware Analyst 负责资料定位和定义复核。", ""]
    status = ["# 模块状态", ""]
    architecture = ["# 模拟固件架构", "", "L1 的板和信号模型见 docs/schematic.svg 与 docs/netlist.csv。其余层按需使用。", ""]
    interfaces = ["# 公共接口契约", "", "协调者管理以下公共声明。语义和约束见 docs/design.md。", ""]
    owned = set()
    for module in scenario["modules"]:
        ident = module["id"]
        directory = state / "modules" / ident
        owner = "Firmware Developer" if module["layer"] == 5 else "RTOS Specialist" if module["layer"] == 4 else "Driver Developer"
        paths = ", ".join(module["code"])
        expect(not owned.intersection(module["code"]), f"模块写入范围重叠: {ident}")
        owned.update(module["code"])
        registry.append(f"- {owner} · {ident} · 逻辑会话 `{scenario['scope']}/{ident}` · 写入 `{paths}`")
        status.append(f"- {ident} · 接口 `{module['interface']}` v1 · 已实现，待宿主验证")
        dependencies = ", ".join(module["depends_on"]) or "无其他模块依赖"
        architecture.append(f"- L{module['layer']} · {ident} · `{module['prefix']}` · {dependencies}")
        interfaces.append(f"- {ident} v1 · `{module['interface']}`")
        write_text(directory / "MODULE_CONTEXT.md", f"# 模块上下文\n\n{ident} 位于 L{module['layer']}。"
                   f"设计 `docs/design.md`。{owner} 写入 `{paths}`。公共接口由协调者管理。\n")
        write_text(directory / "DESIGN.md", f"# 模块设计\n\n{ident} 的职责和生命周期见 `docs/design.md`。\n")
        write_text(directory / "INTERFACE.md", f"# 模块接口\n\n{ident} v1 的公开声明位于 `{module['interface']}`。\n")
        write_text(directory / "HANDOFF.md", f"# 模块交接\n\n{ident} 已完成模拟实现。基线 `{baseline}`。"
                   f"`{module['interface']}` v1，写入范围 `{paths}`。ISS-SIM-001 按 ADR-SIM-001 同步。\n\n"
                   "交接时计划为核对 Git 与接口，再执行对应宿主配置的回归。目标机验证仍待相应工具与实板。\n")
        files = [state / "PROJECT_CONTEXT.md", state / "PROJECT_BASELINE.md", directory / "MODULE_CONTEXT.md", directory / "HANDOFF.md"]
        context, base, mod, handoff = [path.read_text(encoding="utf-8") for path in files]
        expect(bool(context.strip()) and baseline in base and ident in mod and module["interface"] in handoff
               and "宿主配置" in handoff, "模块恢复资料不足")
    expect(execute(root, [git, "rev-parse", "HEAD"]) == baseline, "恢复基线已变化")
    expect(not execute(root, [git, "status", "--short", "--", "src", "tests"]), "恢复时发现源码或测试变化")
    write_text(state / "AGENT_REGISTRY.md", "\n".join(registry) + "\n")
    write_text(state / "MODULE_STATUS.md", "\n".join(status) + "\n")
    write_text(state / "ARCHITECTURE.md", "\n".join(architecture) + "\n")
    write_text(state / "INTERFACE_CONTRACTS.md", "\n".join(interfaces) + "\n")


def host_profiles(root, state, scenario, compiler, trace):
    tested = []
    expected_code = {path for module in scenario["modules"] for path in module["code"]}
    actual_code = set()
    for profile, test in zip(scenario["profiles"], trace["tests"]):
        out = Path("build") / profile["id"]
        (root / out).mkdir(parents=True)
        objects, journal = [], []
        flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic"]
        for directory in scenario["include_dirs"]:
            flags.extend(("-I", directory))
        for number, path in enumerate(profile["sources"]):
            obj = (out / f"unit-{number}.o").as_posix()
            execute(root, [compiler, *flags, "-c", path, "-o", obj], journal=journal)
            expect((root / obj).is_file(), f"缺少编译产物 {obj}")
            objects.append(obj)
            actual_code.add(path)
        binary = out / ("run.exe" if os.name == "nt" else "run")
        execute(root, [compiler, *objects, "-o", binary.as_posix()], journal=journal)
        output = execute(root, [str(root / binary)], journal=journal)
        expect(output == profile["expected_stdout"], f"宿主测试输出不符: {output}")
        evidence = state / "reports" / f"{profile['id']}.json"
        write_json(evidence, journal)
        test.update(status="Passed", evidence=evidence.relative_to(root).as_posix())
        tested.append({"profile": profile["id"], "compiled_units": len(objects), "linked": True, "test_output": output})
    expect(expected_code <= actual_code, "存在未编译的纳管实现文件")
    return tested


def run_case(root, name, compiler, git):
    shutil.copytree(HERE / name, root)
    state = root / ".embedded"
    scenario = read_json(root / "scenario.json")
    wire, visible, device, note = inspect_fixture(root, scenario)
    scan = command(root, "scan_project")
    evidence = {(row["category"], row["candidate"]) for row in scan["evidence"]}
    expect(all(("mcu", model) in evidence for model in scenario["mcus"])
           and all(("build_system", tool) in evidence for tool in scenario["build_systems"])
           and (not scenario["rtos"] or ("rtos", scenario["rtos"]) in evidence), "项目扫描缺少目标证据")
    baseline = baseline_git(root, git)
    if "existing_context" in scenario:
        state.mkdir()
        write_text(state / "PROJECT_CONTEXT.md", scenario["existing_context"])
    module_options = [item for module in scenario["modules"] for item in ("--module", module["id"])]
    initialized = command(root, "init_project", *module_options)
    expect(not command(root, "init_project", *module_options)["created"], "初始化不幂等")
    if "existing_context" in scenario:
        expect("PROJECT_CONTEXT.md" in initialized["preserved"] and
               (state / "PROJECT_CONTEXT.md").read_text(encoding="utf-8") == scenario["existing_context"], "既有上下文被改变")
    reports = state / "reports"
    reports.mkdir()
    write_json(reports / "scan.json", scan)
    config = read_json(state / "config.json")
    config["document_roots"] = ["docs"]
    config["architecture"].update(include_dirs=scenario["include_dirs"], application_forbidden_symbols=["HAL_*"],
                                  layers=[{"prefix": row["prefix"], "layer": row["layer"], "module": row["id"]}
                                          for row in scenario["modules"]])
    write_json(state / "config.json", config)

    preview = command(root, "inventory_documents", "--capture-text")
    receipt = command(root, "inventory_documents", "--update-registry", "--capture-text")
    expect(set(receipt["added"]) == {row["id"] for row in preview["documents"]}, "预览与登记的资料 ID 不一致")
    registry = read_json(state / "documents.json")
    documents = {row["path"]: row for row in registry["documents"]}
    trace = prepare_trace(root, scenario, documents)
    req_id = trace["requirements"][0]["id"]
    for path, record in documents.items():
        record.update(scope=scenario["scope"], status="Valid", authority="Supporting", version=record["fingerprint"]["observed_version"])
        if path in {"docs/netlist.csv", "docs/requirements.md"}:
            record["authority"] = "Authoritative"
    documents[NOTE].update(status="Conflict", impact="P0", related_documents=[documents["docs/netlist.csv"]["id"]])
    documents["docs/netlist.csv"].update(related_documents=[documents["docs/schematic.svg"]["id"]], requirements=[req_id])
    write_json(state / "documents.json", registry)
    write_json(state / "traceability.json", trace)
    conflict_id = resolve_fixture(root, state, documents, wire, note, trace, reports)
    prepare_handoffs(root, state, scenario, baseline, git)

    architecture = command(root, "check_architecture")
    expect(architecture["coverage"] == "checked" and architecture["include_module_edges"], "分层检查未覆盖真实模块引用")
    write_json(reports / "architecture.json", architecture)
    profiles = host_profiles(root, state, scenario, compiler, trace)
    trace["requirements"][0]["status"] = "Verified"
    write_json(state / "traceability.json", trace)
    matrix = command(root, "generate_traceability", "--scan-code", "src")
    write_json(reports / "traceability.json", matrix)
    validation = command(root, "validate_project", "--check-hashes", "--strict")
    expect(not validation["fact_conflicts"], "同步后仍存在资料冲突")
    write_json(reports / "validation.json", validation)
    evidence = ", ".join(f"`{test['evidence']}`" for test in trace["tests"])
    statuses = ["# 模块状态", ""]
    for module in trace["modules"]:
        directory = state / "modules" / module["id"]
        write_text(directory / "TEST_REPORT.md", f"# 宿主测试\n\n成功完成编译、链接及行为测试。证据为 {evidence}。"
                   "目标环境与真实硬件待验证。\n")
        with (directory / "HANDOFF.md").open("a", encoding="utf-8") as handoff:
            handoff.write(f"\n最新进展为宿主回归已完成。证据为 {evidence}。"
                          "下一步为在相应 MCU 和真实工程基线可用后复核平台资料并进行目标构建和板级验证。\n")
        statuses.append(f"- {module['id']} · v1 · 宿主已验证 · `modules/{module['id']}/TEST_REPORT.md`")
    with (state / "ISSUES.md").open("a", encoding="utf-8") as handle:
        handle.write("\n关闭模拟冲突。严格校验、追溯和宿主回归已通过。\n")
    write_text(state / "MODULE_STATUS.md", "\n".join(statuses) + "\n")
    write_text(reports / "DELIVERY.md", f"# 模拟交付\n\n保留初始源码和配置。同步 `{NOTE}` 至 Rev B，"
               f"批准记录 ADR-SIM-001，关闭 {conflict_id}。需求 {req_id} 经宿主验证。"
               "编译、链接、行为回归和架构检查通过，证据见同目录。"
               "实板、目标工具链、资源和时序等待真实项目验证。\n")
    return {"case": name, "baseline": baseline, "schematic_label": visible["board-pad"], "netlist_pad": wire["pad"],
            "device_interface": device["Interface"], "resolved_conflict": conflict_id, "documents": len(documents),
            "modules": len(scenario["modules"]), "recovered_module_records": len(scenario["modules"]),
            "requirement": req_id, "architecture_violations": len(architecture["violations"]),
            "traceability_gaps": len(matrix["gaps"]), "validation_errors": validation["errors"],
            "validation_warnings": validation["warnings"], "host_profiles": profiles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, action="append", help="选择案例，可重复。默认验证全部")
    parser.add_argument("--cc", default="cc", help="支持 GCC/Clang 命令行的宿主 C 编译器")
    parser.add_argument("--work-dir", type=Path, help="保留副本和证据的新目录，默认使用临时目录")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        compiler, git = shutil.which(args.cc), shutil.which("git")
        expect(compiler and git, "演练需要 Git 及兼容 GCC/Clang 的宿主 C 编译器")
        cases = list(dict.fromkeys(args.case or CASES))
        if args.work_dir:
            work = args.work_dir.expanduser().resolve()
            expect(not any(work.is_relative_to(HERE / case) for case in CASES), "演练目录需位于示例输入目录之外")
            work.mkdir(parents=True, exist_ok=False)
            result = [run_case(work / case, case, compiler, git) for case in cases]
            write_json(work / "summary.json", result)
        else:
            with tempfile.TemporaryDirectory(prefix="efw-examples-") as scratch:
                work = Path(scratch).resolve()
                result = [run_case(work / case, case, compiler, git) for case in cases]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"演练失败 {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
