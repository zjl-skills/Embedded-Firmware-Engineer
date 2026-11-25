"""按工程映射检查 C/C++ 层间 include、应用限制和模块依赖环。"""

from collections import defaultdict
import posixpath
import re

from project_data import (
    CODE_SUFFIXES, array_at, cli_main, emit, get_project, load_config, object_at, parser, relative_name,
    require, safe_path, string_at, strings_at, walk_files,
)
from trace_data import load_trace


INCLUDE = re.compile(r'^[ \t]*#[ \t]*include\b(?P<target>[^\n]*)', re.M)
LITERAL = re.compile(r'^[ \t]*(?:"([^"\n]+)"|<([^>\n]+)>)[ \t]*$')
TOKEN = re.compile(
    r'(?P<comment>//[^\n]*|/\*.*?(?:\*/|\Z))'
    r'|(?P<raw>R"(?P<delimiter>[^\s()\\]{0,16})\(.*?\)(?P=delimiter)")'
    r'|(?P<string>"(?:\\[^\n]|[^"\\\n])*"|\'(?:\\[^\n]|[^\'\\\n])*\')', re.S,
)
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
EXCEPTION_RULES = ("upward_include", "application_forbidden_include", "application_forbidden_symbol")


def load_rules(root, config):
    architecture = config["architecture"]
    layers, prefixes = [], set()
    for value in array_at(architecture.get("layers"), "architecture.layers"):
        rule = object_at(value, "architecture.layers")
        prefix = relative_name(rule.get("prefix"), "layer.prefix", allow_root=True)
        canonical = safe_path(root, prefix, allow_root=True)
        require(canonical not in prefixes, f"层路径映射重复: {prefix}")
        prefixes.add(canonical)
        layer = rule.get("layer")
        require(type(layer) is int and 1 <= layer <= 6, f"层编号需为 1–6: {prefix}")
        if rule.get("module") is not None:
            string_at(rule["module"], "layer.module")
        layers.append(rule)
    include_dirs = strings_at(architecture.get("include_dirs"), "architecture.include_dirs")
    for include_dir in include_dirs:
        safe_path(root, include_dir, allow_root=True)
    include_limits = strings_at(architecture.get("application_forbidden_includes"), "architecture.application_forbidden_includes")
    symbol_limits = strings_at(architecture.get("application_forbidden_symbols"), "architecture.application_forbidden_symbols")
    for symbol in symbol_limits:
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\*?", symbol), f"无效符号约束: {symbol}")

    exceptions = {}
    for row in array_at(architecture.get("exceptions"), "architecture.exceptions"):
        entry = object_at(row, "架构例外")
        rule = entry.get("rule")
        require(rule in EXCEPTION_RULES, f"不支持的架构例外规则: {rule}")
        source = relative_name(entry.get("source"), "exception.source")
        target = string_at(entry.get("target"), "exception.target")
        for field in ("decision", "rationale"):
            string_at(entry.get(field), f"exception.{field}")
        key = rule, source, target
        require(key not in exceptions, f"架构例外重复: {key}")
        exceptions[key] = entry
    layers.sort(key=lambda item: -len(item["prefix"]))
    return layers, include_dirs, include_limits, symbol_limits, exceptions


def layer_of(path, rules):
    return next((item for item in rules if item["prefix"] == "." or path == item["prefix"]
                 or path.startswith(item["prefix"] + "/")), None)


def source_events(text):
    """展开续行，保持逻辑行到物理行的映射。"""
    line_starts, pieces = [], []
    start_new = True
    for index, part in enumerate(text.splitlines(keepends=True), 1):
        if start_new:
            line_starts.append(index)
        start_new = not part.endswith("\\\n")
        pieces.append(part if start_new else part[:-2])
    logical = "".join(pieces)

    def blank(match):
        return re.sub(r"[^\n]", " ", match[0])

    preprocessor = TOKEN.sub(lambda match: match[0] if match.lastgroup == "string" else blank(match), logical)
    code = TOKEN.sub(blank, logical)
    for index, line in enumerate(preprocessor.splitlines()):
        directive = INCLUDE.match(line)
        if directive:
            token = directive["target"].strip()
            match = LITERAL.fullmatch(token)
            if match:
                yield "include", line_starts[index], match[1] or match[2], match[1] is not None
            else:
                yield "nonliteral", line_starts[index], token, False
    for index, line in enumerate(code.splitlines()):
        for match in IDENTIFIER.finditer(line):
            yield "symbol", line_starts[index], match[0], False


def resolve_include(source, name, quoted, include_dirs, files):
    if not name or name.startswith("/") or any(char in name for char in "\\:\x00"):
        return None
    search = [posixpath.dirname(source), *include_dirs] if quoted else include_dirs
    for folder in search:
        target = posixpath.normpath(posixpath.join(folder, name))
        if target in files:
            return target
    return None


def dependency_cycles(graph):
    """返回强连通分量中的环。分开遍历原图及转置图。"""
    reverse = {node: set() for node in graph}
    for node, others in graph.items():
        for other in others:
            reverse[other].add(node)
    visited, finished = set(), []
    for node in sorted(graph):
        if node in visited:
            continue
        visited.add(node)
        stack = [(node, iter(sorted(graph[node])))]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is None:
                finished.append(current)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(graph[child]))))
    cycles = []
    visited.clear()
    for node in reversed(finished):
        if node in visited:
            continue
        visited.add(node)
        stack, component = [node], []
        while stack:
            current = stack.pop()
            component.append(current)
            for parent in reverse[current] - visited:
                visited.add(parent)
                stack.append(parent)
        if len(component) > 1 or node in graph[node]:
            cycles.append(sorted(component))
    return sorted(cycles)


def check(project, config, modules):
    root, _ = project
    layers, include_dirs, include_limits, symbol_limits, exceptions = load_rules(root, config)
    files = {path.relative_to(root).as_posix(): path for path in walk_files(project, config)}
    mapped = {name: rule for name in files if (rule := layer_of(name, layers))}
    sources = sorted(name for name in mapped if files[name].suffix.lower() in CODE_SUFFIXES)
    violations, excepted, unresolved, skipped, unmapped_targets = [], [], [], [], []
    observations = set()
    graph = defaultdict(set)
    for ident, module in modules.items():
        graph[ident].update(module.get("depends_on", []))
        for dep in module.get("depends_on", []):
            graph.setdefault(dep, set())
    edges = []

    def finding(rule, path, line, target, **details):
        key = rule, path, line, target
        if key in observations:
            return
        observations.add(key)
        row = {"rule": rule, "source": path, "line": line, "target": target, **details}
        exception = exceptions.get((rule, path, target))
        if exception:
            excepted.append({**row, "decision": exception["decision"], "rationale": exception["rationale"]})
        else:
            violations.append(row)

    for name in sources:
        try:
            text = files[name].read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            skipped.append({"source": name, "reason": "unsupported_text_encoding"})
            continue
        source_rule = mapped[name]
        source_layer, source_module = source_rule["layer"], source_rule.get("module")
        for kind, line, target, quoted in source_events(text):
            if kind == "symbol":
                if source_layer == 6 and any(target.startswith(item[:-1]) if item.endswith("*") else target == item
                                             for item in symbol_limits):
                    finding("application_forbidden_symbol", name, line, target)
                continue
            if kind == "nonliteral":
                unresolved.append({"source": name, "line": line, "target": target, "reason": "nonliteral"})
                continue
            if source_layer == 6 and any(target.startswith(item) or posixpath.basename(target).startswith(item)
                                         for item in include_limits):
                finding("application_forbidden_include", name, line, target)
            resolved = resolve_include(name, target, quoted, include_dirs, files)
            if resolved is None:
                unresolved.append({"source": name, "line": line, "target": target, "reason": "not_on_scan_paths"})
                continue
            target_rule = mapped.get(resolved)
            if target_rule is None:
                unmapped_targets.append({"source": name, "line": line, "target": resolved})
                continue
            if source_layer < target_rule["layer"]:
                finding("upward_include", name, line, resolved, source_layer=source_layer, target_layer=target_rule["layer"])
            target_module = target_rule.get("module")
            if source_module and target_module and source_module != target_module:
                graph[source_module].add(target_module)
                graph.setdefault(target_module, set())
                edges.append({"from_module": source_module, "to_module": target_module,
                              "source": name, "line": line, "target": resolved})
    for cycle in dependency_cycles(graph):
        violations.append({"rule": "module_cycle", "modules": cycle})
    coverage = "not_configured" if not layers else "no_mapped_sources" if not sources else "partial" if skipped else "checked"
    return {"coverage": coverage, "mapped_sources": len(sources), "examined_sources": len(sources) - len(skipped),
            "unmapped_code_files": sorted(name for name in files.keys() - mapped.keys() if files[name].suffix.lower() in CODE_SUFFIXES),
            "violations": violations, "exceptions_applied": excepted, "unresolved_includes": unresolved,
            "unmapped_targets": unmapped_targets, "skipped_sources": skipped, "include_module_edges": edges,
            "declared_module_edges": {ident: module.get("depends_on", []) for ident, module in modules.items()},
            "limitations": ["按 include 路径和文本规则检查。条件编译未展开，结果可能涉及未启用分支。",
                            "宏 include、外部头、生成文件、链接、回调与运行时调用需另外验证。",
                            "L6 限制使用项目配置的头文件前缀与符号规则。"]}


def main(args):
    project = get_project(args)
    _, modules, _ = load_trace(project, optional=True)
    report = check(project, load_config(project), modules)
    emit(args, project, report)
    return int(bool(report["violations"]) or report["coverage"] != "checked")


if __name__ == "__main__":
    raise SystemExit(cli_main(parser(__doc__), main))
