"""生成需求到验收的追溯矩阵并报告悬空项。"""

from document_data import ACTIVE_STATUSES, load_registry
from project_data import cli_main, emit, emit_text, get_project, load_config, parser, require, safe_path, walk_files
from trace_data import load_trace, trace_report


def markdown(report):
    def cell(value):
        return str(value if value is not None else "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    lines = ["# 需求追溯矩阵", "", "| 需求 | 状态 | 来源 | 设计 | 模块与接口 | 代码 | 测试 | 验收 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for req in report["requirements"]:
        source = req["source"] or {}
        acceptance = " ".join(filter(None, (req["acceptance"], req["acceptance_evidence"])))
        for link in req["links"] or [{}]:
            values = (f"{req['id']} {req['title']}", req["status"],
                      " ".join(filter(None, (source.get("document"), source.get("locator")))),
                      link.get("design"), " ".join(filter(None, (link.get("module"), link.get("interface"),
                                                                  link.get("interface_path")))),
                      ", ".join(link.get("code", [])), ", ".join(link.get("tests", [])), acceptance)
            lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines.extend(("", "## 追溯缺口", ""))
    lines.extend(f"- {cell(gap['kind'])} · {cell(gap['id'])} {cell(gap['detail'])}".rstrip() for gap in report["gaps"])
    if not report["gaps"]:
        lines.append("已登记范围内未发现追溯缺口。")
    return "\n".join(lines) + "\n"


def main(args):
    project = get_project(args)
    config = load_config(project)
    root, _ = project
    registry, _ = load_registry(project)
    extra_code = set()
    for name in args.scan_code:
        start = safe_path(root, name, allow_root=True)
        require(start.is_dir(), f"扫描代码目录不存在: {name}")
        extra_code.update(path.relative_to(root).as_posix() for path in walk_files(project, config, start)
                          if path.suffix.lower() in {".c", ".cc", ".cpp", ".cxx", ".c++"})
    documents = {row["id"] for row in registry["documents"] if row["status"] in ACTIVE_STATUSES}
    report = trace_report(root, load_trace(project), documents, extra_code)
    if args.format == "md":
        emit_text(args, project, markdown(report))
    else:
        emit(args, project, report)
    return int(bool(report["gaps"]))


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--format", choices=("json", "md"), default="json", help="报告格式")
    cli.add_argument("--scan-code", action="append", default=[], help="检查额外源码目录内未关联需求的 C/C++ 文件")
    raise SystemExit(cli_main(cli, main))
