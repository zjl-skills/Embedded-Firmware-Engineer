"""对比已登记资料的哈希、版本线索与小文本，并列出候选影响。"""

from collections import Counter, defaultdict
from difflib import unified_diff
from itertools import islice

from document_data import ACTIVE_STATUSES, PRIORITIES, discover_documents, fingerprint, load_registry
from project_data import cli_main, emit, emit_text, get_project, load_config, object_at, parser, read_json, records_at, safe_path, state_file, strings_at
from trace_data import load_trace


def spread(seeds, graph):
    visited = set(seeds)
    todo = list(visited)
    while todo:
        for member in graph.get(todo.pop(), ()):
            if member not in visited:
                visited.add(member)
                todo.append(member)
    return visited


def impact_for(identifier, documents, trace, facts=None):
    reqs, modules, tests = trace
    document_graph = defaultdict(set)
    for ident, row in documents.items():
        for other in row["related_documents"]:
            document_graph[ident].add(other)
            document_graph[other].add(ident)
    affected_docs = spread([identifier], document_graph)
    origins = set()
    affected_facts = []
    for ident in affected_docs:
        origins.update(("requirement", req) for req in documents[ident]["requirements"])
        origins.update(("module", mod) for mod in documents[ident]["modules"])
    for ident, fact in (facts or {}).items():
        source = object_at(fact.get("source"), f"{ident}.source")
        if source.get("document") not in affected_docs:
            continue
        affected_facts.append({"id": ident, "key": fact.get("key"), "source": source})
        origins.update(("requirement", req) for req in strings_at(fact.get("requirements", []), f"{ident}.requirements"))
        origins.update(("module", mod) for mod in strings_at(fact.get("modules", []), f"{ident}.modules"))
    relations = defaultdict(set)
    for ident, req in reqs.items():
        if (req.get("source") or {}).get("document") in affected_docs:
            origins.add(("requirement", ident))
        for link in req.get("links", []):
            relations["requirement", ident].add(("module", link["module"]))
            relations["module", link["module"]].add(("requirement", ident))
    for ident, module in modules.items():
        for dep in module.get("depends_on", []):
            relations["module", dep].add(("module", ident))
    affected = spread(origins, relations)
    affected_reqs = {ident for kind, ident in affected if kind == "requirement"}
    affected_modules = {ident for kind, ident in affected if kind == "module"}
    test_ids, code, deliverables = set(), set(), set()
    for ident in affected_reqs:
        requirement = reqs.get(ident, {})
        deliverables.update(requirement.get("deliverables", []))
        if requirement.get("acceptance_evidence"):
            deliverables.add(requirement["acceptance_evidence"])
        for link in requirement.get("links", []):
            test_ids.update(link.get("tests", []))
            code.update(link.get("code", []))

    design, interfaces = set(), set()
    for ident in affected_modules:
        module = modules.get(ident, {})
        if module.get("design"):
            design.add(module["design"])
        interfaces.update(row["path"] for row in module.get("interfaces", []))
        code.update(module.get("code", []))
    hints = {documents[ident].get("impact") for ident in affected_docs}
    return {"assessment": "candidate_links_require_review", "priority_hint": next((p for p in PRIORITIES if p in hints), None),
            "related_documents": sorted(affected_docs - {identifier}), "requirements": sorted(affected_reqs),
            "document_paths": sorted(documents[ident]["path"] for ident in affected_docs - {identifier}), "facts": affected_facts,
            "modules": sorted(affected_modules), "design": sorted(design), "interfaces": sorted(interfaces),
            "code": sorted(code), "tests": sorted(test_ids),
            "delivery_documents": sorted(deliverables), "confirmation": "Pending Confirmation",
            "test_files": sorted({tests[ident]["path"] for ident in test_ids if ident in tests})}


def text_difference(previous, current, path):
    if "text_snapshot" not in previous or "text_snapshot" not in current:
        return {"state": "unavailable", "previous": previous.get("comparison"), "current": current.get("comparison")}
    old = previous["text_snapshot"].splitlines(keepends=True)
    new = current["text_snapshot"].splitlines(keepends=True)
    if old == new:
        return {"state": "readable_text_equal"}
    limit = 160
    lines = list(islice(unified_diff(old, new, fromfile=f"baseline/{path}", tofile=f"current/{path}", lineterm=""), limit + 1))
    return {"state": "changed_text", "lines": [line.rstrip("\r\n") for line in lines[:limit]],
            "line_limit_reached": len(lines) > limit}


def changes(project, config, registry, trace, *, include_unchanged=False, facts=None):
    root, _ = project
    documents = {row["id"]: row for row in registry["documents"]}
    known = {safe_path(root, row["path"]) for row in documents.values()}
    added, matches = [], defaultdict(list)
    for path in discover_documents(project, config):
        if path not in known:
            current = fingerprint(path)
            relative = path.relative_to(root).as_posix()
            matches[current["sha256"]].append(relative)
            added.append({"path": relative, "kind": "added", "current": current})

    records = list(added)
    counts = Counter(added=len(added))
    active_changes = len(added)
    for identifier, row in documents.items():
        path = safe_path(root, row["path"])
        previous = row.get("fingerprint")
        current = fingerprint(path, capture_text=bool(previous and "text_snapshot" in previous)) if path.is_file() else None
        record = {"id": identifier, "path": row["path"], "registry_status": row["status"], "declared_version": row.get("version"),
                  "baseline": {k: v for k, v in previous.items() if k != "text_snapshot"} if previous else None,
                  "current": {k: v for k, v in current.items() if k != "text_snapshot"} if current else None}
        if current is None:
            kind = "missing"
            record["possible_moves_or_copies"] = matches.get(previous["sha256"], []) if previous else []
        elif previous is None:
            kind = "unbaselined"
        elif previous["sha256"] != current["sha256"]:
            kind = "content_changed"
            old_version, new_version = previous.get("observed_version"), current.get("observed_version")
            record["version_comparison"] = {"baseline": old_version, "current": new_version,
                                            "state": ("unavailable" if old_version is None or new_version is None
                                                      else "equal" if old_version == new_version else "changed")}
            record["text_difference"] = text_difference(previous, current, row["path"])
        else:
            kind = "metadata_only" if previous["modified_utc"] != current["modified_utc"] else "unchanged"
        if kind in {"missing", "unbaselined", "content_changed"}:
            record["impact"] = impact_for(identifier, documents, trace, facts)
            if row["status"] in ACTIVE_STATUSES:
                active_changes += 1
        counts[kind] += 1
        if kind != "unchanged" or include_unchanged:
            record["kind"] = kind
            records.append(record)

    return {"counts": dict(counts), "active_changes": active_changes, "records": records,
            "limitations": ["SHA-256 变化说明字节不同。工程影响和权威版本需人工核对。",
                            "文本差异限可用的 UTF-8 小文本快照。移动候选只按同一散列给出。",
                            "影响集合来自登记关联和模块依赖，新增资料需补充关联后审查。"]}


def markdown(report):
    lines = ["# DOCUMENT_IMPACT", "", f"活动资料候选变化 {report['active_changes']} 项。正式同步前复核原文、适用范围、责任人和批准记录。", ""]
    for record in report["records"]:
        if record["kind"] == "unchanged":
            continue
        lines.extend((f"## {record['path']}", "", f"- 变化类型 `{record['kind']}`"))
        for field, label in (("baseline", "基线 SHA-256"), ("current", "当前 SHA-256")):
            if record.get(field):
                lines.append(f"- {label} `{record[field]['sha256']}`")
        if version := record.get("version_comparison"):
            lines.append(f"- 版本线索 `{version['baseline']}` → `{version['current']}`")
        if impact := record.get("impact"):
            lines.append(f"- 影响级别候选 `{impact['priority_hint'] or '待分级'}`。批准状态 `待确认`。")
            fields = (("document_paths", "需评估同步的关联资料"), ("requirements", "需复核的需求"),
                      ("modules", "受影响模块"), ("design", "需复核的设计"), ("interfaces", "需复核的接口"),
                      ("code", "需审查的代码"), ("tests", "需重跑的用例"), ("test_files", "测试文件"),
                      ("delivery_documents", "需评估同步的交付文件"))
            for key, label in fields:
                if impact[key]:
                    lines.append(f"- {label} " + "、".join(f"`{value}`" for value in impact[key]))
            for fact in impact["facts"]:
                lines.append(f"- 需复核的工程事实 `{fact['id']}` · {fact['source'].get('locator', '待定位')}")
        if diff := record.get("text_difference"):
            lines.extend(("", f"文本比较 `{diff['state']}`。", ""))
            if diff.get("lines"):
                lines.extend("    " + line for line in diff["lines"])
        lines.append("")
    lines.extend(("在 ISSUES / DECISIONS 记录确认和历史依据。批准后按当前 SHA-256 显式推进资料指纹并重验。", ""))
    return "\n".join(lines)


def main(args):
    project = get_project(args)
    config = load_config(project)
    registry, _ = load_registry(project)
    path = state_file(project, "facts.json")
    facts = records_at(read_json(path), "facts") if path.is_file() else {}
    report = changes(project, config, registry, load_trace(project), include_unchanged=args.include_unchanged, facts=facts)
    if args.format == "md":
        emit_text(args, project, markdown(report))
    else:
        emit(args, project, report)
    return int(bool(args.fail_on_change and report["active_changes"]))


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--format", choices=("json", "md"), default="json", help="输出 JSON 或 DOCUMENT_IMPACT Markdown")
    cli.add_argument("--include-unchanged", action="store_true", help="包含未变更资料记录")
    cli.add_argument("--fail-on-change", action="store_true", help="发现新增或活动资料内容变化、缺失、无基线时返回 1")
    raise SystemExit(cli_main(cli, main))
