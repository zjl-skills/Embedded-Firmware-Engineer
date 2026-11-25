"""检查工程初始化、配置、资料登记、追溯以及结构化事实一致性。"""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import PurePosixPath

from check_architecture import load_rules
from document_data import ACTIVE_STATUSES, PRIORITIES, fingerprint, load_registry
from project_data import (
    DataError, STATE_FILES, cli_main, emit, get_project, load_config, object_at, parser, read_json,
    records_at, require, safe_path, state_file, string_at,
)
from trace_data import load_trace, trace_report


CATEGORIES = ("mcu", "pin", "electrical", "protocol", "requirement", "timing", "architecture", "version", "capability")


def inspect_facts(data, documents):
    groups = defaultdict(list)
    dangling = []
    unconfirmed_scopes = []
    for ident, row in records_at(data, "facts").items():
        category = row.get("category")
        require(category in CATEGORIES, f"{ident} 无效事实类别: {category}")
        key = string_at(row.get("key"), f"{ident}.key")
        require("scope" in row, f"{ident}.scope 需要已确认范围或 null")
        scope = row["scope"]
        if scope is not None:
            string_at(scope, f"{ident}.scope")
        value = string_at(row.get("value"), f"{ident}.value")
        require(row.get("severity") in PRIORITIES, f"{ident} 无效事实严重度")
        require(row.get("state") in ("Asserted", "Inferred"), f"{ident} 无效事实状态")
        source = object_at(row.get("source"), f"{ident}.source")
        source_id = string_at(source.get("document"), f"{ident}.source.document")
        for field in ("locator", "excerpt"):
            string_at(source.get(field), f"{ident}.source.{field}")
        document = documents.get(source_id)
        if document is None:
            dangling.append({"fact": ident, "document": source_id})
        elif row["state"] == "Asserted" and document["status"] in ACTIVE_STATUSES:
            definition = {"id": ident, "value": value, "severity": row["severity"],
                          "source": source, "document_path": document["path"],
                          "document_version": document.get("version"), "document_status": document["status"],
                          "authority": document["authority"]}
            if scope is None:
                unconfirmed_scopes.append({"category": category, "key": key, **definition})
            else:
                groups[category, key, scope].append(definition)
    conflicts, authority_overlaps = [], []
    for (category, key, scope), members in sorted(groups.items()):
        if len({row["value"] for row in members}) > 1:
            token = json.dumps([category, key, scope], ensure_ascii=False).encode("utf-8")
            priority = min((row["severity"] for row in members), key=PRIORITIES.index)
            conflicts.append({"id": "CF-" + hashlib.sha256(token).hexdigest()[:12].upper(), "category": category,
                              "key": key, "scope": scope, "severity": priority, "definitions": members})
        authoritative = sorted({row["source"]["document"] for row in members if row["authority"] == "Authoritative"})
        if len(authoritative) > 1:
            authority_overlaps.append({"category": category, "key": key, "scope": scope, "documents": authoritative})
    return conflicts, authority_overlaps, dangling, unconfirmed_scopes


def validate(project, *, check_hashes=False):
    root, _ = project
    issues = []

    def issue(code, detail, *, severity="error"):
        issues.append({"code": code, "severity": severity, "detail": detail})

    def attempt(code, operation):
        try:
            return operation()
        except (DataError, OSError, RuntimeError) as exc:
            issue(code, str(exc))
            return None

    for template in STATE_FILES:
        name = PurePosixPath(template).name
        path = attempt("invalid_management_path", lambda: state_file(project, name))
        if path is not None and not path.is_file():
            issue("missing_management_file", name)
    config = attempt("invalid_config", lambda: load_config(project))
    trace = attempt("invalid_traceability", lambda: load_trace(project))
    loaded = attempt("invalid_document_registry", lambda: load_registry(project))
    facts = attempt("invalid_facts", lambda: read_json(state_file(project, "facts.json")))
    conflicts = []

    if config is not None:
        for name in config["document_roots"]:
            if not safe_path(root, name, allow_root=True).is_dir():
                issue("missing_document_root", name)
        if config.get("coding_standard") and not safe_path(root, config["coding_standard"]).is_file():
            issue("missing_coding_standard", config["coding_standard"])
        rules = attempt("invalid_architecture_config", lambda: load_rules(root, config))
        if rules is not None:
            layers, include_dirs, *_ = rules
            if not layers:
                issue("unconfigured_layer_mapping", None, severity="warning")
            for layer in layers:
                if not safe_path(root, layer["prefix"], allow_root=True).exists():
                    issue("missing_layer_path", layer["prefix"])
            for name in include_dirs:
                if not safe_path(root, name, allow_root=True).is_dir():
                    issue("missing_include_directory", name)

    if trace is not None and not trace[0]:
        issue("empty_requirements", None, severity="warning")
    if loaded is not None:
        docs = {row["id"]: row for row in loaded[0]["documents"]}
        active = {ident for ident, row in docs.items() if row["status"] in ACTIVE_STATUSES}
        if not active:
            issue("empty_active_documents", None, severity="warning")
        for ident, row in docs.items():
            if trace is not None:
                for field, records in (("modules", trace[1]), ("requirements", trace[0])):
                    for reference in row[field]:
                        if reference not in records:
                            issue("unknown_document_link", {"id": ident, "field": field, "reference": reference})
            if ident not in active:
                continue
            path = safe_path(root, row["path"])
            if not path.is_file():
                issue("missing_active_document", {"id": ident, "path": row["path"]})
            elif row.get("fingerprint") is None:
                issue("missing_fingerprint", ident, severity="warning")
            elif check_hashes:
                current = attempt("unreadable_document", lambda: fingerprint(path))
                if current and current["sha256"] != row["fingerprint"]["sha256"]:
                    issue("document_hash_changed", {"id": ident, "path": row["path"], "current": current["sha256"]})
        if trace is not None:
            report = trace_report(root, trace, active)
            for item in report["gaps"]:
                provisional = item["kind"] in {"missing_requirement_source", "missing_acceptance_criteria",
                                               "missing_implementation_chain", "missing_implementation",
                                               "implementation_without_tests"}
                state = trace[0].get(item["id"], {}).get("status")
                severity = "warning" if provisional and state in {"Proposed", "Confirmed", "Designed"} else "error"
                issue("traceability_gap", item, severity=severity)
        if facts is not None:
            result = attempt("invalid_facts", lambda: inspect_facts(facts, docs))
            if result is not None:
                conflicts, overlaps, dangling, unconfirmed_scopes = result
                for item in conflicts:
                    issue("fact_conflict", item["id"], severity="warning" if item["severity"] == "P2" else "error")
                for item in overlaps:
                    issue("overlapping_authority", item, severity="warning")
                for item in dangling:
                    issue("unknown_fact_document", item)
                for item in unconfirmed_scopes:
                    issue("unconfirmed_fact_scope", item, severity="warning")
    counts = Counter(item["severity"] for item in issues)
    return {"issues": issues, "fact_conflicts": conflicts, "errors": counts["error"], "warnings": counts["warning"],
            "checked_document_hashes": check_hashes,
            "limits": ["只比较同类、同键且作用域完全相同的活动资料结构化明示值。",
                       "定位、提取、单位和范围归一化、语义差异、批准和工程风险需要人工确认。"]}


def main(args):
    project = get_project(args)
    report = validate(project, check_hashes=args.check_hashes)
    emit(args, project, report)
    return int(bool(report["errors"] or args.strict and report["warnings"]))


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--check-hashes", action="store_true", help="重算活动资料 SHA-256")
    cli.add_argument("--strict", action="store_true", help="将警告也作为返回码 1 的检查项")
    raise SystemExit(cli_main(cli, main))
