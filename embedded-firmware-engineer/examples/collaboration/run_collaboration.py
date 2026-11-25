"""在独立 Git 仓库演练任务工作树、冲突检测、恢复及宿主集成。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / "scripts/check_collaboration.py"
TASKS = {
    "driver": ("MOD-UART", "Driver Developer", "src/serial_driver.c"),
    "application": ("MOD-APP", "Firmware Developer", "src/app_sample.c"),
    "test": ("MOD-TEST", "Test Engineer", "tests/test_serial_link.c"),
}
HEADER = "include/serial_link.h"


def run(cwd, *args, expected=0):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode != expected:
        raise RuntimeError(f"{args} 返回 {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def git(cwd, *args):
    return run(cwd, "git", "-c", "user.name=Embedded Fixture", "-c", "user.email=fixture@example.invalid",
               "-c", "core.hooksPath=.git/no-hooks", *args)


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(work):
    repo = work / "integration"
    repo.mkdir()
    for name in ("README.md", "board.net", HEADER):
        put(repo / name, (HERE / name).read_text(encoding="utf-8"))
    put(repo / ".gitattributes", "* text eol=lf\n")
    put(repo / ".gitignore", "/build/\n")
    plan = {"schema_version": 1, "interfaces": [{"id": "IF-SERIAL", "path": HEADER, "version": "1",
                                                 "approved_by": "Simulation Coordinator", "sha256": digest(repo / HEADER)}],
            "tasks": []}
    put(repo / ".embedded/PROJECT_CONTEXT.md", "# 项目上下文\n\n协作演练，采用 B 模式，目标为宿主验证。\n")
    put(repo / ".embedded/PROJECT_BASELINE.md", "# 项目基线\n\n采用 Git 初始提交，公共串口接口 v1 与模拟网表。\n")
    for name, (module, role, source) in TASKS.items():
        folder = f".embedded/modules/{module}"
        plan["tasks"].append({"id": name, "module": module, "role": role, "branch": f"demo/{name}",
                              "interfaces": ["IF-SERIAL"], "writes": [source, f"{folder}/HANDOFF.md"], "depends_on": []})
        put(repo / folder / "MODULE_CONTEXT.md", f"# 模块上下文\n\n{module} · {role} · `{source}`。公共头由协调者管理。\n")
        put(repo / folder / "DESIGN.md", f"# 设计\n\n{module} 按 README 验收条件实现或验证。\n")
        put(repo / folder / "INTERFACE.md", f"# 接口\n\nIF-SERIAL v1 位于 `{HEADER}`。\n")
        put(repo / folder / "TEST_REPORT.md", "# 模块测试\n\n待完成宿主集成验证。\n")
        put(repo / folder / "HANDOFF.md", f"# 交接\n\n{module} · `{source}`。下一步在独立任务分支实现。\n")
    put(repo / ".embedded/collaboration.json", json.dumps(plan, ensure_ascii=False))
    git(repo, "init", "-q", "-b", "integration")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "Lock simulation interface")
    base = git(repo, "rev-parse", "HEAD")
    put(work / "baseline.txt", base + "\n")
    for name in TASKS:
        git(repo, "worktree", "add", "-q", "-b", f"demo/{name}", str(work / name), base)
    return base


def check(root, *options, expected=0):
    return json.loads(run(root, sys.executable, "-B", str(SCRIPT), str(root), *options, expected=expected))


def finish(work, compiler):
    repo = work / "integration"
    base = (work / "baseline.txt").read_text(encoding="utf-8").strip()
    evidence = {}
    plan = json.loads((repo / ".embedded/collaboration.json").read_text(encoding="utf-8"))
    duplicate = {**plan, "tasks": [dict(task) for task in plan["tasks"]]}
    duplicate["tasks"][1]["writes"] = [TASKS["driver"][2]]
    put(repo / "build/collision.json", json.dumps(duplicate))
    rejected = check(repo, "--plan", "build/collision.json", expected=1)
    if not any(row["kind"] == "overlapping_ownership" for row in rejected["findings"]):
        raise RuntimeError("未发现故意加入的写入重叠")
    for name, (_, _, source) in TASKS.items():
        tree = work / name
        report = check(tree, "--task", name, "--base", base, "--resume")
        if source not in report["git"]["changes"] or len(report["records"]) != 4:
            raise RuntimeError(f"{name} 缺任务变更或恢复记录")
        git(tree, "add", "--", *report["git"]["changes"])
        git(tree, "commit", "-q", "--no-gpg-sign", "-m", f"Complete {name} task")
        task_commit = git(tree, "rev-parse", "HEAD")
        git(repo, "merge", "-q", "--no-ff", "--no-edit", "--no-gpg-sign", f"demo/{name}")
        evidence[name] = {"before_commit": report["git"], "task_commit": task_commit, "merge_commit": git(repo, "rev-parse", "HEAD")}
    check(repo)
    binary = repo / "build" / ("serial.exe" if os.name == "nt" else "serial")
    build = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic", "-Iinclude",
             *(value[2] for value in TASKS.values()), "-o", str(binary)]
    run(repo, *build)
    result = run(repo, str(binary))
    if result != "PASS serial collaboration":
        raise RuntimeError(f"集成测试输出异常: {result}")
    summary = {"baseline": base, "interface_sha256": digest(repo / HEADER), "collision_detected": True,
               "tasks": evidence, "integration_head": git(repo, "rev-parse", "HEAD"), "build_command": build,
               "test_result": result}
    put(work / "summary.json", json.dumps(summary, indent=2))
    return summary


def replay(work, compiler):
    prepare(work)
    for name, (_, _, source) in TASKS.items():
        put(work / name / source, (HERE / source).read_text(encoding="utf-8"))
    return finish(work, compiler)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cc", default="cc")
    cli.add_argument("--work-dir", type=Path)
    phase = cli.add_mutually_exclusive_group()
    phase.add_argument("--prepare", action="store_true")
    phase.add_argument("--finish", action="store_true")
    args = cli.parse_args()
    if (args.prepare or args.finish) and args.work_dir is None:
        cli.error("--prepare/--finish 需要 --work-dir")
    compiler = shutil.which(args.cc)
    if not args.prepare and not compiler:
        cli.error("未找到兼容 GCC 的宿主编译器")
    try:
        if args.work_dir:
            work = args.work_dir.resolve()
            if not args.finish:
                work.mkdir(parents=True, exist_ok=False)
            result = finish(work, compiler) if args.finish else {"baseline": prepare(work)} if args.prepare else replay(work, compiler)
        else:
            with tempfile.TemporaryDirectory(prefix="efw-collab-") as scratch:
                result = replay(Path(scratch).resolve(), compiler)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"协作演练失败 {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
