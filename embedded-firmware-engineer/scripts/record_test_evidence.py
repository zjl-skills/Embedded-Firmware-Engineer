"""执行明确给出的测试命令并记录可核验的证据及日志。"""

import json

from evidence_data import KINDS, record_execution
from project_data import DataError, cli_main, get_project, json_text, parser, require


def main(args):
    root, _ = get_project(args)
    require(0 < args.timeout <= 3600, "--timeout 需在 1–3600 秒之间")
    try:
        command = json.loads(args.command_json)
    except ValueError as exc:
        raise DataError(f"无效 --command-json: {exc}") from exc
    evidence = record_execution(root, test_id=args.test_id, requirements=args.requirement_id, kind=args.kind,
                                command=command, cwd=args.cwd, toolchain=args.toolchain_version, notes=args.environment,
                                expected={"exit_code": args.expected_exit, "stdout_contains": args.stdout_contains},
                                inputs=args.input, manifest_path=args.output, log_path=args.log, timeout=args.timeout)
    print(json_text(evidence), end="")
    return int(evidence["status"] != "Passed")


if __name__ == "__main__":
    cli = parser(__doc__, output=False)
    cli.add_argument("--test-id", required=True)
    cli.add_argument("--requirement-id", action="append", required=True)
    cli.add_argument("--kind", choices=KINDS, required=True)
    cli.add_argument("--toolchain-version", required=True)
    cli.add_argument("--environment", default="")
    cli.add_argument("--command-json", required=True, help="包含程序及参数的 JSON 字符串数组，不经 shell")
    cli.add_argument("--cwd", default=".", help="项目相对工作目录")
    cli.add_argument("--expected-exit", type=int, default=0)
    cli.add_argument("--stdout-contains")
    cli.add_argument("--input", action="append", required=True, help="待校验散列的项目相对输入文件，可重复")
    cli.add_argument("--output", required=True, help="新证据 JSON 的项目相对路径")
    cli.add_argument("--log", required=True, help="新执行日志 JSON 的项目相对路径")
    cli.add_argument("--timeout", type=int, default=60)
    raise SystemExit(cli_main(cli, main))
