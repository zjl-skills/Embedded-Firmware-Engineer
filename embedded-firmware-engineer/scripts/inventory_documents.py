"""预览资料登记或经显式选择添加资料、推进已审查的指纹。"""

import sys

from document_data import (
    SHA_PATTERN, discover_documents, fingerprint, load_registry, new_document, save_registry, utc_time, validate_registry,
)
from project_data import cli_main, emit, get_project, load_config, parser, require, safe_path


def acceptance_options(items):
    result = {}
    for item in items:
        ident, separator, digest = item.partition("=")
        require(separator and ident and SHA_PATTERN.fullmatch(digest), f"--accept 需要 DOC-ID=sha256: {item}")
        require(ident not in result, f"--accept 存在重复 ID: {ident}")
        result[ident] = digest
    return result


def inventory(project, config, registry, accepted, *, capture_text=False):
    root, _ = project
    rows = validate_registry(root, registry)
    known = {safe_path(root, row["path"]) for row in rows.values()}
    added, refreshed = [], []
    for ident, expected in accepted.items():
        require(ident in rows, f"无法推进未知资料的基线: {ident}")
        row = rows[ident]
        info = fingerprint(safe_path(root, row["path"]), capture_text=capture_text)
        require(info["sha256"] == expected, f"{ident} 当前 SHA-256 不匹配已审查散列")
        row["fingerprint"] = info
        row["last_checked"] = utc_time()
        refreshed.append(ident)
    for path in discover_documents(project, config):
        if path not in known:
            row = new_document(root, path, capture_text)
            require(row["id"] not in rows, f"资料 ID 冲突，先为现有资料指定独立 ID: {row['path']}")
            rows[row["id"]] = row
            registry["documents"].append(row)
            added.append(row["id"])
    return added, refreshed


def main(args):
    require(not args.accept or args.update_registry, "--accept 需要 --update-registry")
    require(not (args.update_registry and args.output), "写入正式登记时将 JSON 回执输出到标准输出")
    accepted = acceptance_options(args.accept)
    project = get_project(args)
    config = load_config(project, optional=not args.update_registry)
    registry, original = load_registry(project, optional=not args.update_registry)
    added, refreshed = inventory(project, config, registry, accepted, capture_text=args.capture_text)
    if args.update_registry:
        if added or refreshed:
            save_registry(project, registry, original)
        print(f"登记新增 {len(added)}，推进指纹 {len(refreshed)}", file=sys.stderr)
        emit(args, project, {"added": added, "refreshed": refreshed, "count": len(registry["documents"])})
    else:
        emit(args, project, registry)
    return 0


if __name__ == "__main__":
    cli = parser(__doc__)
    cli.add_argument("--capture-text", action="store_true", help="为新增或获准更新的 UTF-8 文档保留小文本快照")
    cli.add_argument("--update-registry", action="store_true", help="显式增补正式登记并处理 --accept")
    cli.add_argument("--accept", action="append", default=[], metavar="DOC-ID=SHA256",
                     help="将已人工审查且散列仍匹配的资料推进到当前指纹，可重复指定")
    raise SystemExit(cli_main(cli, main))
