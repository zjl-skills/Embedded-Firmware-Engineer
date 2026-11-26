"""需求、模块设计、接口、代码、测试和验收的结构化关系。"""

from evidence_data import KINDS, verify_acceptance, verify_execution
from project_data import (
    array_at, object_at, read_json, records_at, relative_name, require, safe_path, state_file, string_at, strings_at,
)


REQUIREMENT_STATES = ("Proposed", "Confirmed", "Designed", "Implemented", "Verified", "Accepted", "Deferred", "Rejected")
TEST_STATES = ("Not Run", "Passed", "Failed", "Blocked")


def file_reference(root, value, label):
    if value is not None:
        safe_path(root, relative_name(value, label))
    return value


def load_trace(project, *, optional=False, with_policy=False):
    root, _ = project
    path = state_file(project, "traceability.json")
    if optional and not path.exists():
        return (({}, {}, {}), "legacy") if with_policy else ({}, {}, {})
    data = read_json(path)
    policy = data.get("evidence_policy", "legacy")
    require(policy in ("legacy", "structured"), "evidence_policy 需要 legacy 或 structured")
    requirements, modules, tests = (records_at(data, key) for key in ("requirements", "modules", "tests"))
    for ident, module in modules.items():
        file_reference(root, module.get("design"), f"{ident}.design")
        for item in strings_at(module.get("code", []), f"{ident}.code"):
            file_reference(root, item, f"{ident}.code")
        strings_at(module.get("depends_on", []), f"{ident}.depends_on")
        for interface in records_at(module, "interfaces").values():
            file_reference(root, string_at(interface.get("path"), f"{ident}.interface.path"), f"{ident}.interface.path")
    for ident, test in tests.items():
        file_reference(root, string_at(test.get("path"), f"{ident}.path"), f"{ident}.path")
        file_reference(root, test.get("evidence"), f"{ident}.evidence")
        require(test.get("status") in TEST_STATES, f"{ident} 测试状态无效")
    for ident, req in requirements.items():
        string_at(req.get("title"), f"{ident}.title")
        require(req.get("priority") in ("P0", "P1", "P2"), f"{ident} 需求优先级无效")
        require(req.get("status") in REQUIREMENT_STATES, f"{ident} 需求状态无效")
        string_at(req.get("acceptance", ""), f"{ident}.acceptance", allow_empty=True)
        file_reference(root, req.get("acceptance_evidence"), f"{ident}.acceptance_evidence")
        for item in strings_at(req.get("deliverables", []), f"{ident}.deliverables"):
            file_reference(root, item, f"{ident}.deliverables")
        kinds = strings_at(req.get("verification_kinds", []), f"{ident}.verification_kinds")
        require(all(kind in KINDS for kind in kinds), f"{ident} 验证类别无效")
        if req.get("decision") is not None:
            string_at(req["decision"], f"{ident}.decision")
        if req.get("source") is not None:
            source = object_at(req["source"], f"{ident}.source")
            for key in ("document", "locator"):
                string_at(source.get(key), f"{ident}.source.{key}")
        for link in array_at(req.get("links", []), f"{ident}.links"):
            object_at(link, f"{ident}.links")
            string_at(link.get("module"), f"{ident}.links.module")
            string_at(link.get("interface"), f"{ident}.links.interface")
            for item in strings_at(link.get("code", []), f"{ident}.links.code"):
                file_reference(root, item, f"{ident}.links.code")
            strings_at(link.get("tests", []), f"{ident}.links.tests")
    trace = requirements, modules, tests
    return (trace, policy) if with_policy else trace


def trace_report(root, trace, documents, extra_code=(), *, evidence_policy="legacy"):
    requirements, modules, tests = trace
    gaps, rows = [], []

    def exists(path):
        return path is not None and safe_path(root, path).is_file()

    def gap(kind, ident, detail):
        gaps.append({"kind": kind, "id": ident, "detail": detail})

    for ident, module in modules.items():
        if not exists(module.get("design")):
            gap("missing_design", ident, module.get("design"))
        for dep in module.get("depends_on", []):
            if dep not in modules:
                gap("unknown_dependency", ident, dep)
        for interface in module["interfaces"]:
            if not exists(interface["path"]):
                gap("missing_interface_file", ident, interface["path"])
        for path in module.get("code", []):
            if not exists(path):
                gap("missing_code_file", ident, path)

    passed = {}
    for ident, test in tests.items():
        if not exists(test["path"]):
            gap("missing_test_file", ident, test["path"])
        if test["status"] == "Passed":
            if not exists(test.get("evidence")):
                gap("pass_without_evidence", ident, test.get("evidence"))
            elif exists(test["path"]):
                if evidence_policy == "legacy":
                    passed[ident] = None
                else:
                    try:
                        passed[ident] = verify_execution(root, test["evidence"], ident, test["path"])
                    except (ValueError, OSError, RuntimeError) as exc:
                        gap("invalid_test_evidence", ident, str(exc))

    traced_code, traced_tests = set(), set()
    for ident, req in requirements.items():
        status = req["status"]
        row = {"id": ident, "title": req["title"], "priority": req["priority"], "status": status,
               "source": req.get("source"), "acceptance": req.get("acceptance", ""),
               "acceptance_evidence": req.get("acceptance_evidence"), "links": []}
        if status in ("Verified", "Accepted") and evidence_policy == "legacy":
            row["evidence_assurance"] = "legacy_unconfirmed"
        rows.append(row)
        if status in ("Deferred", "Rejected"):
            if not req.get("decision"):
                gap("inactive_without_decision", ident, status)
            continue
        if not req.get("source") or req["source"]["document"] not in documents:
            gap("missing_requirement_source", ident, req.get("source"))
        if not row["acceptance"].strip():
            gap("missing_acceptance_criteria", ident, None)
        if not req.get("links"):
            gap("missing_implementation_chain", ident, None)
        seen_links = set()
        verified_records = {}
        verified_kinds = set()
        for link in req.get("links", []):
            module_id, interface_id = link["module"], link["interface"]
            if (module_id, interface_id) in seen_links:
                gap("duplicate_requirement_link", ident, f"{module_id}/{interface_id}")
            seen_links.add((module_id, interface_id))
            module = modules.get(module_id, {})
            interface = next((face for face in module.get("interfaces", []) if face["id"] == interface_id), {})
            design = module.get("design")
            row["links"].append({**link, "design": design, "interface_path": interface.get("path")})
            if not module:
                gap("unknown_module", ident, module_id)
            if not interface:
                gap("unknown_interface", ident, f"{module_id}/{interface_id}")
            code = set(link.get("code", []))
            declared = set(module.get("code", []))
            if not code:
                gap("missing_implementation", ident, f"{module_id}/{interface_id}")
            if code - declared:
                gap("undeclared_code", ident, sorted(code - declared))
            traced_code.update(code & declared)
            linked_tests = set(link.get("tests", []))
            if not linked_tests:
                gap("implementation_without_tests", ident, f"{module_id}/{interface_id}")
            if linked_tests - tests.keys():
                gap("unknown_test", ident, sorted(linked_tests - tests.keys()))
            traced_tests.update(linked_tests & tests.keys())
            if status in ("Verified", "Accepted"):
                proven = set()
                for test_id in linked_tests & passed.keys():
                    proof = passed[test_id]
                    if proof is None or ident in proof["requirement_ids"]:
                        proven.add(test_id)
                        if proof is not None:
                            verified_records[test_id] = proof["record_sha256"]
                            verified_kinds.add(proof["kind"])
                if missing := linked_tests - proven:
                    gap("verification_not_proven", ident, sorted(missing))
        if status in ("Verified", "Accepted") and evidence_policy == "structured":
            if missing := set(req.get("verification_kinds", [])) - verified_kinds:
                gap("verification_kind_missing", ident, sorted(missing))
        if status == "Accepted":
            if not exists(row["acceptance_evidence"]):
                gap("acceptance_not_proven", ident, row["acceptance_evidence"])
            elif evidence_policy == "structured":
                try:
                    verify_acceptance(root, row["acceptance_evidence"], ident, verified_records)
                except (ValueError, OSError, RuntimeError) as exc:
                    gap("acceptance_not_proven", ident, str(exc))

    all_code = set(extra_code)
    for module in modules.values():
        all_code.update(module.get("code", []))
    for path in sorted(all_code - traced_code):
        gap("code_without_requirement", path, None)
    for ident in sorted(tests.keys() - traced_tests):
        gap("test_without_requirement", ident, tests[ident]["path"])
    return {"requirements": rows, "gaps": gaps, "evidence_policy": evidence_policy,
            "legacy_test_evidence": sorted(ident for ident, proof in passed.items() if proof is None),
            "counts": {"requirements": len(requirements), "modules": len(modules),
                                                           "tests": len(tests), "managed_code_files": len(all_code)}}
