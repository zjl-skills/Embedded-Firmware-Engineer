"""测试执行、日志散列与验收记录的字段和验证逻辑。"""

from datetime import datetime, timezone
import hashlib
import platform
import subprocess

from document_data import SHA_PATTERN, fingerprint
from project_data import array_at, json_text, object_at, parse_json, require, safe_path, string_at, strings_at, write_new


KINDS = ("Host Unit Test", "Host Integration Test", "Target Build Test", "Hardware Test", "System Acceptance Test")
MAX_RECORD = 8 * 1024 * 1024
EXECUTION_FIELDS = ("test_id", "requirement_ids", "kind", "command", "working_directory", "toolchain_version", "environment",
                    "started_at", "finished_at", "input_sha256")


def sha256(contents):
    return hashlib.sha256(contents).hexdigest()


def read_record(root, path):
    file = safe_path(root, path)
    with file.open("rb") as handle:
        raw = handle.read(MAX_RECORD + 1)
    require(len(raw) <= MAX_RECORD, f"证据记录超过 8 MiB: {path}")
    return parse_json(raw, path), sha256(raw)


def time_at(text, label):
    value = string_at(text, label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} 需要 ISO 8601 时间") from exc
    require(result.utcoffset() is not None, f"{label} 需要时区")
    return result


def command_at(value):
    command = array_at(value, "command")
    require(command, "command 需要可执行文件")
    for index, part in enumerate(command):
        require("\0" not in string_at(part, "command", allow_empty=index > 0), "命令参数含 NUL")
    return command


def measure_inputs(root, paths):
    return {path: fingerprint(safe_path(root, path))["sha256"] for path in dict.fromkeys(paths)}


def outcome(expected, log):
    required_exit = expected.get("exit_code")
    exit_code = log.get("exit_code")
    require(type(required_exit) is int and type(exit_code) is int, "预期与实际退出码需要整数")
    text = string_at(log.get("stdout"), "log.stdout", allow_empty=True)
    string_at(log.get("stderr"), "log.stderr", allow_empty=True)
    contains = expected.get("stdout_contains")
    if contains is not None:
        string_at(contains, "expected.stdout_contains")
    matches = contains is None or contains in text
    return {"exit_code": exit_code, "stdout_matches": matches}, "Passed" if matches and exit_code == required_exit else "Failed"


def record_execution(root, *, test_id, requirements, kind, command, cwd, toolchain, notes, expected, inputs,
                     manifest_path, log_path, timeout=60):
    """运行已提供的 argv。每次执行保留独立的日志及证据文件。"""
    command_at(command)
    string_at(test_id, "test_id")
    strings_at(requirements, "requirement_ids")
    require(requirements and kind in KINDS, "需要需求 ID 和已支持的测试类别")
    string_at(toolchain, "toolchain_version")
    require(type(expected.get("exit_code")) is int, "预期退出码需要整数")
    if expected.get("stdout_contains") is not None:
        string_at(expected["stdout_contains"], "expected.stdout_contains")
    manifest, logfile = (safe_path(root, path) for path in (manifest_path, log_path))
    require(manifest != logfile and not manifest.exists() and not logfile.exists(), "证据和日志需要不同的新文件路径")
    where = safe_path(root, cwd, allow_root=True)
    require(where.is_dir(), "测试工作目录不存在")
    hashes = measure_inputs(root, inputs)
    started = datetime.now(timezone.utc)
    try:
        run = subprocess.run(command, cwd=where, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"测试执行超过 {timeout} 秒") from exc
    finished = datetime.now(timezone.utc)
    require(measure_inputs(root, inputs) == hashes, "测试期间输入已改变，请重试")
    info = {"test_id": test_id, "requirement_ids": requirements, "kind": kind, "command": command, "working_directory": cwd,
            "toolchain_version": toolchain, "environment": {"system": platform.system(), "release": platform.release(),
                                                              "machine": platform.machine(), "description": notes},
            "started_at": started.isoformat(), "finished_at": finished.isoformat(), "input_sha256": hashes}
    log = {"schema_version": 1, **info, "exit_code": run.returncode,
           "stdout": run.stdout.decode("utf-8", errors="replace"), "stderr": run.stderr.decode("utf-8", errors="replace")}
    raw_log = json_text(log).encode("utf-8")
    require(len(raw_log) <= MAX_RECORD, "执行日志超过 8 MiB，请缩小执行输出")
    actual, status = outcome(expected, log)
    evidence = {"schema_version": 1, "evidence_type": "test_run", **info, "expected": expected, "actual": actual,
                "status": status, "log_path": log_path, "sha256": sha256(raw_log)}
    write_new(logfile, raw_log)
    write_new(manifest, json_text(evidence).encode("utf-8"))
    return evidence


def verify_execution(root, path, test_id, test_file):
    record, record_digest = read_record(root, path)
    require(record.get("evidence_type") == "test_run" and record.get("test_id") == test_id, "证据的 Test ID 或类型不匹配")
    requirements = strings_at(record.get("requirement_ids"), "evidence.requirement_ids")
    require(requirements, "证据缺少 Requirement ID")
    require(record.get("kind") in KINDS, "证据测试类别无效")
    command_at(record.get("command"))
    safe_path(root, record.get("working_directory"), allow_root=True)
    string_at(record.get("toolchain_version"), "toolchain_version")
    environment = object_at(record.get("environment"), "environment")
    for field in ("system", "release", "machine"):
        string_at(environment.get(field), "environment." + field)
    start, finish = (time_at(record.get(key), key) for key in ("started_at", "finished_at"))
    require(start <= finish, "测试结束时间早于开始时间")
    log, log_digest = read_record(root, record.get("log_path"))
    require(log_digest == record.get("sha256"), "执行日志 SHA-256 不匹配")
    require(all(key in log and key in record and log[key] == record[key] for key in EXECUTION_FIELDS), "日志与证据执行字段不一致")
    inputs = object_at(record.get("input_sha256"), "input_sha256")
    require(test_file in inputs, "证据缺少已登记测试文件的输入散列")
    require(measure_inputs(root, inputs) == inputs, "测试输入 SHA-256 不匹配，需重跑")
    actual, status = outcome(object_at(record.get("expected"), "expected"), log)
    actual_record = object_at(record.get("actual"), "actual")
    require(type(actual_record.get("exit_code")) is int and type(actual_record.get("stdout_matches")) is bool
            and actual_record == actual and status == record.get("status") == "Passed", "证据的实际结果与日志/预期不符或测试未通过")
    return {"requirement_ids": requirements, "kind": record["kind"], "record_sha256": record_digest}


def verify_acceptance(root, path, requirement_id, evidence):
    record, _ = read_record(root, path)
    require(record.get("evidence_type") == "acceptance" and record.get("requirement_id") == requirement_id
            and record.get("decision") == "Accepted", "验收记录的需求或决策不匹配")
    string_at(record.get("approved_by"), "acceptance.approved_by")
    time_at(record.get("approved_at"), "acceptance.approved_at")
    authority = object_at(record.get("authorization"), "acceptance.authorization")
    approval_path = string_at(authority.get("path"), "authorization.path")
    require(approval_path != path, "授权依据需要独立记录")
    hash_value = string_at(authority.get("sha256"), "authorization.sha256")
    require(SHA_PATTERN.fullmatch(hash_value) and measure_inputs(root, [approval_path])[approval_path] == hash_value,
            "授权依据 SHA-256 不匹配")
    require(evidence and record.get("test_evidence_sha256") == evidence, "验收记录与当前关联测试证据不匹配")
