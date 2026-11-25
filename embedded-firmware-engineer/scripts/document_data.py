"""资料分类、文件指纹、登记结构和显式基线写入。"""

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import tempfile

from project_data import (
    DataError, json_text, object_at, parse_json, records_at, require, safe_path, state_file,
    string_at, strings_at, walk_files,
)


FORMATS = {
    "text": set(".md .txt .csv .tsv .json .xml .yaml .yml .ini .toml .rst .log .net .kicad_sch .kicad_pcb .svg".split()),
    "pdf_or_image": set(".pdf .png .jpg .jpeg .bmp .gif .tif .tiff .webp".split()),
    "office": set(".doc .docx .ppt .pptx .xls .xlsx .ods .odt .odp".split()),
    "diagram": set(".vsd .vsdx .drawio .dio .mmd .puml".split()),
    "eda": set(".sch .pcb .pcbdoc .schdoc .prjpcb .brd .dsn .gbr .pro .kicad_pro .epro .esch .epcb .asc".split()),
}
TEXT_CANDIDATES = FORMATS["text"] | {".mmd", ".puml", ".drawio", ".dio", ".kicad_pro", ".gbr"}
DOCUMENT_TYPES = {**{suffix: kind for kind, extensions in FORMATS.items() for suffix in extensions},
                  ".kicad_sch": "eda", ".kicad_pcb": "eda", ".svg": "diagram", ".net": "eda"}
STATUSES = {"Valid", "Pending Confirmation", "Conflict", "Outdated", "Superseded", "Archived"}
ACTIVE_STATUSES = {"Valid", "Pending Confirmation", "Conflict"}
AUTHORITIES = {"Unreviewed", "Authoritative", "Supporting", "Reference"}
PRIORITIES = ("P0", "P1", "P2")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
SNAPSHOT_LIMIT = 32 * 1024
VERSION_LINE = re.compile(r"^[#*\- \t]*(?:version|revision|版本|修订号?)[ \t]*[:：][ \t]*(\S[^\r\n]*)$", re.I | re.M)


def utc_time(timestamp=None):
    time = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return time.isoformat(timespec="microseconds")


def date_or_none(value, where):
    if value is not None:
        text = string_at(value, where)
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DataError(f"{where} 需要 ISO 8601 日期或时间: {text}") from exc


def document_type(path):
    return DOCUMENT_TYPES.get(path.suffix.lower())


def discover_documents(project, config):
    root, _ = project
    paths = set()
    for name in config["document_roots"]:
        start = safe_path(root, name, allow_root=True)
        require(start.is_dir(), f"资料目录不存在: {name}")
        paths.update(path for path in walk_files(project, config, start) if document_type(path))
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def observed_version(path, text):
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return None
        values = {data[key] for key in ("version", "revision")
                  if isinstance(data, dict) and isinstance(data.get(key), str) and data[key].strip()}
    else:
        values = {value.strip() for value in VERSION_LINE.findall(text.replace("\r\n", "\n").replace("\r", "\n"))}
    return next(iter(values)) if len(values) == 1 else None


def fingerprint(path, *, capture_text=False):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        text_possible = path.suffix.lower() in TEXT_CANDIDATES and before.st_size <= SNAPSHOT_LIMIT
        small_content = bytearray()
        while block := handle.read(128 * 1024):
            digest.update(block)
            if text_possible:
                small_content.extend(block)
                if len(small_content) > SNAPSHOT_LIMIT:
                    small_content.clear()
                    text_possible = False
        after = os.fstat(handle.fileno())
    current = path.stat()

    def identity(info):
        return info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev

    require(identity(before) == identity(after) == identity(current), f"读取期间资料已变化，请重试: {path}")
    result = {"sha256": digest.hexdigest(), "size_bytes": after.st_size, "modified_utc": utc_time(after.st_mtime),
              "observed_version": None, "comparison": "hash_only"}
    if text_possible:
        try:
            body = small_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            result["comparison"] = "unsupported_text_encoding"
        else:
            if "\x00" not in body:
                result["comparison"] = "utf8_text"
                result["observed_version"] = observed_version(path, body)
                if capture_text:
                    result["text_snapshot"] = body
    return result


def new_document(root, path, capture_text):
    relative = path.relative_to(root).as_posix()
    path_hash = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12].upper()
    return {"id": f"DOC-{path_hash}", "name": path.name, "path": relative, "type": document_type(path),
            "version": None, "scope": "", "authority": "Unreviewed", "status": "Pending Confirmation",
            "impact": None, "modules": [], "requirements": [], "related_documents": [],
            "last_checked": utc_time(), "fingerprint": fingerprint(path, capture_text=capture_text)}


def validate_registry(root, registry):
    rows = records_at(registry, "documents")
    seen = set()
    for ident, row in rows.items():
        path = safe_path(root, row.get("path"))
        require(path not in seen, f"{ident} 资料路径重复: {row['path']}")
        seen.add(path)
        for field in ("name", "type"):
            string_at(row.get(field), f"{ident}.{field}")
        string_at(row.get("scope"), f"{ident}.scope", allow_empty=True)
        if row.get("version") is not None:
            string_at(row["version"], f"{ident}.version")
        require(row.get("authority") in tuple(AUTHORITIES), f"{ident} 资料权威性无效")
        require(row.get("status") in tuple(STATUSES), f"{ident} 资料状态无效")
        require(row.get("impact") in (None, *PRIORITIES), f"{ident} 资料影响等级无效")
        date_or_none(row.get("last_checked"), f"{ident}.last_checked")
        for field in ("modules", "requirements", "related_documents"):
            values = strings_at(row.get(field), f"{ident}.{field}")
            if field == "related_documents":
                require(all(value in rows and value != ident for value in values), f"{ident} 关联资料 ID 无效")
        info = row.get("fingerprint")
        if info is None:
            continue
        object_at(info, f"{ident}.fingerprint")
        sha = string_at(info.get("sha256"), f"{ident}.sha256")
        require(SHA_PATTERN.fullmatch(sha), f"{ident} SHA-256 无效")
        size = info.get("size_bytes")
        require(type(size) is int and size >= 0, f"{ident} 文件大小无效")
        date_or_none(string_at(info.get("modified_utc"), f"{ident}.modified_utc"), f"{ident}.modified_utc")
        if info.get("observed_version") is not None:
            string_at(info["observed_version"], f"{ident}.observed_version")
        if "text_snapshot" in info:
            text = string_at(info["text_snapshot"], f"{ident}.text_snapshot", allow_empty=True)
            require(len(text.encode("utf-8")) <= SNAPSHOT_LIMIT, f"{ident} 文本快照超过上限")
    return rows


def load_registry(project, *, optional=False):
    path = state_file(project, "documents.json")
    if optional and not path.exists():
        return {"schema_version": 1, "documents": []}, None
    raw = path.read_bytes()
    data = parse_json(raw, path)
    validate_registry(project[0], data)
    return data, raw


def save_registry(project, data, original):
    path = state_file(project, "documents.json")
    lock = state_file(project, "documents.json.lock")
    try:
        handle = lock.open("xb")
    except FileExistsError as exc:
        raise DataError(f"资料登记正在写入或遗留锁待检查: {lock}") from exc
    temporary = None
    try:
        with handle:
            handle.write(f"pid={os.getpid()}\n".encode("ascii"))
        require(path.read_bytes() == original, "资料登记在读取后已改变，请重新预览")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".documents-", suffix=".tmp", delete=False) as output:
            temporary = output.name
            output.write(json_text(data).encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        require(path.read_bytes() == original, "资料登记在写入时已改变，请重新预览")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
        lock.unlink()
