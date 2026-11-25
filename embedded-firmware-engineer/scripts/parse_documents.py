"""只读工程资料，输出带原始位置和确认状态的提取候选。"""

from pathlib import Path
import sys

from document_data import fingerprint, load_registry
from project_data import cli_main, emit, get_project, parser, require, safe_path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parsers import capabilities, extract
from parsers.base import MAX_FILE


def main(args):
    project = get_project(args)
    if args.capabilities:
        emit(args, project, {"schema_version": 1, "adapters": capabilities()})
        return 0
    require(args.file, "需要 --file 或 --capabilities")
    registry, _ = load_registry(project, optional=True)
    registered = {doc["path"]: doc for doc in registry["documents"]}
    paths = [(name, safe_path(project[0], name)) for name in dict.fromkeys(args.file)]
    results = []
    for name, path in paths:
        doc = registered.get(name, {})
        old = doc.get("fingerprint") or {}
        before = path.stat() if path.is_file() else None
        observed = fingerprint(path) if before and before.st_size <= MAX_FILE else {}
        match = observed["sha256"] == old["sha256"] if "sha256" in observed and "sha256" in old else None
        version = (doc.get("version") if match else None) or observed.get("observed_version")
        result = extract(path, name, document_id=doc.get("id"), version=version,
                         scope=(doc.get("scope") or None) if match else None, include_images=args.include_images)
        if observed:
            try:
                after = path.stat()
            except FileNotFoundError:
                after = None
            if not after or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                result.update(status="error", error="提取期间文件已更改，请重试。", facts=[])
                observed, match = {}, None
        result["sha256"] = observed.get("sha256")
        result["baseline_match"] = match
        if match is False:
            result["limitations"].append("文件偏离已登记散列，批准的版本和适用范围需要重新核对。")
        results.append(result)
    emit(args, project, {"schema_version": 1, "documents": results})
    return int(any(item["status"] not in ("parsed", "partial") or args.strict and item["status"] == "partial" for item in results))


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--file", action="append", default=[], help="项目相对源文件，可重复")
    cli.add_argument("--capabilities", action="store_true", help="列出当前适配器能力和降级路径")
    cli.add_argument("--strict", action="store_true", help="部分可读也返回 1")
    cli.add_argument("--include-images", action="store_true", help="在报告中附带限额内的 Office 原始嵌入图像及 PDF 图像区域")
    raise SystemExit(cli_main(cli, main))
