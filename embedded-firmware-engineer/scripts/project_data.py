"""项目路径、CLI、配置和结构化记录的公共约定。"""

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
STATE_FILES = (
    "project/PROJECT_CONTEXT.md", "project/PROJECT_BASELINE.md", "project/DOCUMENT_REGISTRY.md",
    "requirements/REQUIREMENTS.md", "architecture/ARCHITECTURE.md", "interface/INTERFACE_CONTRACTS.md",
    "project/DECISIONS.md", "project/ISSUES.md", "project/AGENT_REGISTRY.md", "project/MODULE_STATUS.md",
    "project/CHANGELOG.md", "project/config.json", "project/documents.json", "project/traceability.json",
    "project/facts.json",
)
MODULE_FILES = (
    "module/MODULE_CONTEXT.md", "module/DESIGN.md", "interface/INTERFACE.md",
    "test/TEST_REPORT.md", "handoff/HANDOFF.md",
)
CODE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".h++", ".inc", ".inl", ".ipp"}
INTERNAL_DIRS = {".git", ".hg", ".svn", ".embedded", ".agents", ".codex", "__pycache__"}


class DataError(ValueError):
    """输入不满足工程数据约定。"""


def require(condition, message):
    if not condition:
        raise DataError(message)


def object_at(value, where):
    require(isinstance(value, dict), f"{where} 需要 JSON 对象")
    return value


def array_at(value, where):
    require(isinstance(value, list), f"{where} 需要 JSON 数组")
    return value


def string_at(value, where, *, allow_empty=False):
    require(isinstance(value, str) and (allow_empty or value.strip()), f"{where} 需要字符串")
    return value


def strings_at(value, where):
    result = [string_at(item, where) for item in array_at(value, where)]
    require(len(set(result)) == len(result), f"{where} 含重复值")
    return result


def records_at(data, key):
    """返回有唯一 id 的记录，保留输入顺序。"""
    result = {}
    for index, value in enumerate(array_at(data.get(key), key)):
        row = object_at(value, f"{key}[{index}]")
        identifier = string_at(row.get("id"), f"{key}[{index}].id")
        require(identifier not in result, f"{key} 重复 ID {identifier}")
        result[identifier] = row
    return result


def _unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"重复 JSON 键 {key}")
        obj[key] = value
    return obj


def _invalid_constant(token):
    raise DataError(f"无效 JSON 常量 {token}")


def parse_json(data, source):
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_keys,
                           parse_constant=_invalid_constant)
        obj = object_at(value, str(source))
        require(type(obj.get("schema_version")) is int and obj["schema_version"] == 1,
                "schema_version 必须为 1")
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DataError(f"{source}: {exc}") from exc
    return obj


def read_json(path):
    return parse_json(path.read_bytes(), path)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def relative_name(value, where, *, allow_root=False):
    value = string_at(value, where)
    if value == "." and allow_root:
        return value
    parts = value.split("/")
    require(not any(part in {"", ".", ".."} for part in parts)
            and not any(c in value for c in "\\:\x00"), f"{where} 需要项目相对路径，使用 / 分隔: {value!r}")
    if os.name == "nt":
        require(not any(part.endswith((".", " ")) or PureWindowsPath(part).is_reserved() for part in parts)
                and not any(c in value for c in '<>"|?*'), f"{where} 包含 Windows 保留路径: {value!r}")
    return value


def safe_path(root, name, *, allow_root=False):
    name = relative_name(name, "path", allow_root=allow_root)
    path = root.joinpath(*PurePosixPath(name).parts)
    # 符号链接和重解析点会使写入位置偏离配置声明。
    resolved = path.resolve()
    require(resolved.is_relative_to(root), f"路径超出项目范围: {name}")
    require(resolved == path, f"路径经过链接或重定向: {name}")
    return path


def state_path(project):
    """分别验证管理目录和每个将要读写的记录。"""
    root, state = project
    require(not state.exists() or state.is_dir(), f"管理路径不是目录: {state}")
    return state.relative_to(root).as_posix()


def state_file(project, name):
    root, _ = project
    return safe_path(root, state_path(project) + "/" + name)


def get_project(args, *, create=False):
    root = Path(args.project).expanduser().resolve()
    state = safe_path(root, args.state_dir)
    require(not {part.casefold() for part in state.relative_to(root).parts} & (INTERNAL_DIRS - {".embedded"}),
            f"管理路径不可位于保留目录: {state}")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    require(root.is_dir(), f"项目目录不存在或不可用: {root}")
    result = (root, state)
    state_path(result)
    return result


def load_config(project, *, optional=False):
    root, _ = project
    path = state_file(project, "config.json")
    if optional and not path.exists():
        path = TEMPLATES / "project/config.json"
    config = read_json(path)
    require(config.get("mode") in ("A", "B", "C"), "config.mode 需要 A、B 或 C")
    for name in strings_at(config.get("exclude_dirs"), "config.exclude_dirs"):
        relative_name(name, "config.exclude_dirs")
        require("/" not in name, f"exclude_dirs 需要目录名: {name}")
    for name in strings_at(config.get("document_roots"), "config.document_roots"):
        safe_path(root, name, allow_root=True)
    coding_standard = config.get("coding_standard")
    if coding_standard is not None:
        safe_path(root, coding_standard)
    object_at(config.get("architecture"), "config.architecture")
    return config


def _redirected(path):
    info = path.lstat()
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def walk_files(project, config, start=None):
    root, state = project
    start = root if start is None else start
    excluded = {name.casefold() for name in INTERNAL_DIRS | set(config["exclude_dirs"])}

    def on_error(exc):
        raise exc

    if start.is_relative_to(state) or any(part.casefold() in excluded for part in start.relative_to(root).parts):
        return
    for directory, dirs, files in os.walk(start, onerror=on_error, followlinks=False):
        current = Path(directory)
        dirs[:] = sorted(d for d in dirs if d.casefold() not in excluded
                         and current / d != state and not _redirected(current / d))
        for filename in sorted(files):
            path = current / filename
            if not _redirected(path) and path.is_file():
                yield path


def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(content)


def emit(args, project, data):
    emit_text(args, project, json_text(data))


def emit_text(args, project, result):
    if args.output:
        path = safe_path(project[0], args.output)
        write_new(path, result.encode("utf-8"))
        print(f"报告已写入 {path}", file=sys.stderr)
    else:
        sys.stdout.write(result)


def parser(description, *, output=True):
    cli = argparse.ArgumentParser(description=description)
    cli.add_argument("project", nargs="?", default=".", help="项目根目录，默认当前目录")
    cli.add_argument("--state-dir", default=".embedded", help="项目相对管理目录，默认 .embedded")
    if output:
        cli.add_argument("--output", help="输出到新的项目相对报告文件，默认标准输出")
    return cli


def cli_main(cli, action):
    args = cli.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        return action(args)
    except (DataError, OSError, RuntimeError, UnicodeError) as exc:
        print(f"错误 {exc}", file=sys.stderr)
        return 2


def module_name(value):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value), f"无效模块目录名: {value}")
    require(not re.fullmatch(r"CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]", value, re.I), f"保留模块目录名: {value}")
    return value
