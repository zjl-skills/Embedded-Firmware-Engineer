"""检查任务依赖、文件所有权、锁定接口和 Git 会话恢复状态。"""

from itertools import combinations
from pathlib import Path
import re
import subprocess

from check_architecture import dependency_cycles
from document_data import SHA_PATTERN, fingerprint
from project_data import (
    cli_main, emit, get_project, module_name, parser, read_json, records_at, relative_name, require,
    safe_path, state_file, string_at, strings_at,
)


def claim(root, value):
    recursive = value.endswith("/**")
    name = value[:-3] if recursive else value
    path = safe_path(root, relative_name(name, "任务写入范围"))
    return path.relative_to(root).as_posix().casefold(), recursive


def covers(scope, name):
    prefix, recursive = scope
    return name == prefix or recursive and name.startswith(prefix + "/")


def overlapping(a, b):
    return covers(a, b[0]) or covers(b, a[0])


def dependencies_of(nodes, ident):
    found, pending = set(), [ident]
    while pending:
        for dep in nodes.get(pending.pop(), ()):
            if dep not in found:
                found.add(dep)
                pending.append(dep)
    return found


def inspect_plan(root, data):
    tasks, interfaces = records_at(data, "tasks"), records_at(data, "interfaces")
    owners, graph, findings = {}, {}, []

    def issue(kind, **detail):
        findings.append({"kind": kind, **detail})

    locked = {}
    for ident, interface in interfaces.items():
        path = string_at(interface.get("path"), f"{ident}.path")
        locked[ident] = claim(root, path)[0]
        string_at(interface.get("version"), f"{ident}.version")
        string_at(interface.get("approved_by"), f"{ident}.approved_by")
        sha = string_at(interface.get("sha256"), f"{ident}.sha256")
        require(SHA_PATTERN.fullmatch(sha), f"锁定接口散列无效: {ident}")
        file = safe_path(root, path)
        current = fingerprint(file)["sha256"] if file.is_file() else None
        if current != sha:
            issue("locked_interface_drift", interface=ident, path=path, expected=sha, actual=current)
    for ident, row in tasks.items():
        module_name(string_at(row.get("module"), f"{ident}.module"))
        string_at(row.get("role"), f"{ident}.role")
        owners[ident] = [claim(root, item) for item in strings_at(row.get("writes", []), f"{ident}.writes")]
        graph[ident] = set(strings_at(row.get("depends_on", []), f"{ident}.depends_on"))
        for missing in sorted(graph[ident] - tasks.keys()):
            issue("unknown_task_dependency", task=ident, reference=missing)
        graph[ident].intersection_update(tasks)
        for reference in strings_at(row.get("interfaces", []), f"{ident}.interfaces"):
            if reference not in interfaces:
                issue("unknown_interface_lock", task=ident, interface=reference)
        for interface, path in locked.items():
            if any(covers(scope, path) for scope in owners[ident]):
                issue("locked_interface_ownership", task=ident, interface=interface)
    for cycle in dependency_cycles(graph):
        issue("task_dependency_cycle", tasks=cycle)
    transitive = {ident: dependencies_of(graph, ident) for ident in tasks}
    for left, right in combinations(sorted(tasks), 2):
        if left in transitive[right] or right in transitive[left]:
            continue
        for a in owners[left]:
            for b in owners[right]:
                if overlapping(a, b):
                    issue("overlapping_ownership", tasks=[left, right], paths=[a[0], b[0]])
    return tasks, owners, findings


def git(root, *args, check=True):
    try:
        result = subprocess.run(["git", "--no-optional-locks", *args], cwd=root, capture_output=True,
                                encoding="utf-8", errors="strict", timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Git 查询超时") from exc
    if check:
        require(result.returncode == 0, result.stderr.strip() or "Git 状态不可读")
    return result


def inspect_task(project, data, task, owner, base):
    root, _ = project
    base = base or task.get("baseline") or data.get("baseline")
    require(isinstance(base, str) and re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", base), "任务需要 Git 基线完整提交哈希")
    top = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    require(top == root, "任务检查须从 Git 工作树根执行")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    branch = git(root, "branch", "--show-current").stdout.strip() or None
    findings = []
    if task.get("branch") and branch != task["branch"]:
        findings.append({"kind": "branch_mismatch", "expected": task["branch"], "actual": branch})
    ancestor = git(root, "merge-base", "--is-ancestor", base, head, check=False)
    if ancestor.returncode:
        findings.append({"kind": "baseline_not_ancestor", "baseline": base, "head": head})
        return {"branch": branch, "head": head, "baseline": base, "changes": []}, findings
    tracked = git(root, "diff", "--name-only", "--no-renames", "-z", base, "--").stdout
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    changes = sorted(set(tracked.split("\0") + untracked.split("\0")) - {""})
    outside = [path for path in changes if not any(covers(scope, path.casefold()) for scope in owner)]
    if outside:
        findings.append({"kind": "outside_ownership", "paths": outside})
    return {"branch": branch, "head": head, "baseline": base, "changes": changes}, findings


def handoff(project, module):
    files = ("PROJECT_CONTEXT.md", "PROJECT_BASELINE.md", f"modules/{module}/MODULE_CONTEXT.md", f"modules/{module}/HANDOFF.md")
    recovered, missing = [], []
    for name in files:
        path = state_file(project, name)
        if path.is_file() and path.stat().st_size <= 512 * 1024 and (content := path.read_text(encoding="utf-8-sig")).strip():
            recovered.append({"record": name, "content": content})
        else:
            missing.append(name)
    return recovered, missing


def main(args):
    project = get_project(args)
    require(not args.resume or args.task, "--resume 需要 --task")
    path = safe_path(project[0], args.plan) if args.plan else state_file(project, "collaboration.json")
    data = read_json(path)
    tasks, owners, findings = inspect_plan(project[0], data)
    report = {"tasks": list(tasks), "findings": findings}
    if args.task:
        require(args.task in tasks, f"未登记任务 {args.task}")
        task = tasks[args.task]
        report["git"], new_findings = inspect_task(project, data, task, owners[args.task], args.base)
        findings.extend(new_findings)
        if args.resume:
            report["records"], missing = handoff(project, task["module"])
            if missing:
                findings.append({"kind": "handoff_records_unavailable", "records": missing})
    emit(args, project, report)
    return int(bool(findings))


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--plan", help="项目相对协作计划，默认管理目录的 collaboration.json")
    cli.add_argument("--task", help="同时检查指定任务的 Git 基线和写入范围")
    cli.add_argument("--base", help="任务观察使用的完整 Git 基线哈希")
    cli.add_argument("--resume", action="store_true", help="读取项目及模块的四份恢复记录")
    raise SystemExit(cli_main(cli, main))
