"""统一资料事实、原始定位及有界文件读取。"""

from dataclasses import dataclass, field
from base64 import b64encode
import hashlib
import json
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAX_FILE = 32 * 1024 * 1024
MAX_PART = 8 * 1024 * 1024
MAX_FACTS = 4000
MAX_IMAGE = 512 * 1024
MAX_IMAGE_TOTAL = 2 * 1024 * 1024


class Unavailable(ValueError):
    """格式已识别，缺少工具或可靠的可读表示。"""


class ExtractionLimit(ValueError):
    """提取达到有界处理限额。"""


@dataclass
class Result:
    path: str
    document_id: str | None
    version: str | None
    scope: str | None
    adapter: str | None
    method: str | None = None
    status: str = "parsed"
    facts: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    error: str | None = None
    include_images: bool = False
    image_bytes_used: int = 0

    def add(self, category, content, raw, location, *, confidence="high", evidence="document"):
        if len(self.facts) >= MAX_FACTS:
            raise ExtractionLimit(f"已达到 {MAX_FACTS} 条提取上限")
        seed = json.dumps([self.document_id or self.path, category, location, raw], ensure_ascii=False, sort_keys=True)
        identity = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()
        self.facts.append({"id": "EX-" + identity, "path": self.path, "document_id": self.document_id,
                           "version": self.version, "category": category, "content": content, "raw": raw,
                           "location": location, "method": self.method, "confidence": confidence,
                           "scope": self.scope, "confirmation": "Unconfirmed", "evidence": evidence})

    def partial(self, message):
        self.status = "partial"
        if message not in self.limitations:
            self.limitations.append(message)

    def image_data(self, data, media_type, method):
        if len(data) > MAX_IMAGE or self.image_bytes_used + len(data) > MAX_IMAGE_TOTAL:
            self.partial("图像数据超限，报告保留原资料定位。")
            return {}
        self.image_bytes_used += len(data)
        return {"image_data": {"encoding": "base64", "media_type": media_type, "method": method,
                               "sha256": hashlib.sha256(data).hexdigest(), "value": b64encode(data).decode("ascii")}}


class BaseParser:
    suffixes = frozenset()
    fallback = "提供可读文本或带定位的源格式导出。"

    def recognizes(self, path):
        return path.suffix.lower() in self.suffixes

    def capability(self, suffix):
        return "builtin"

    def extract(self, path, report):
        raise NotImplementedError


def read_text(path):
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = raw.decode(encoding)
    if "\x00" in text:
        raise Unavailable("检测到二进制内容，请提供可读导出。")
    return text


def xml(raw):
    if len(raw) > MAX_PART:
        raise ExtractionLimit("单个 XML 超出 8 MiB")
    plain = raw.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in plain or b"<!ENTITY" in plain:
        raise ValueError("资料 XML 含 DTD 或实体声明")
    return ET.fromstring(raw)


def tag(node):
    return node.tag.rsplit("}", 1)[-1]


def children(node, name):
    return [item for item in node if tag(item) == name]


def elements(node, name):
    return (item for item in node.iter() if tag(item) == name)


def attribute(node, name):
    return next((value for key, value in node.attrib.items() if key.rsplit("}", 1)[-1] == name), None)


class Package(ZipFile):
    """只读取 ZIP 成员，不展开到磁盘，也不访问外部关系。"""

    def __enter__(self):
        try:
            members = self.infolist()
            if (len(members) > 10000 or sum(item.file_size for item in members) > 2 * MAX_FILE
                    or len({item.filename for item in members}) != len(members)):
                raise ExtractionLimit("ZIP 成员过多、解压总量超限或存在重名")
        except Exception:
            self.close()
            raise
        return self

    def part(self, name):
        try:
            member = self.getinfo(name)
        except KeyError as exc:
            raise ValueError(f"缺少包成员 {name}") from exc
        if member.file_size > MAX_PART:
            raise ExtractionLimit(f"{name} 超出 8 MiB")
        return xml(self.read(member))

    def relationships(self, source):
        directory, name = posixpath.split(source)
        path = posixpath.join(directory, "_rels", name + ".rels")
        if path not in self.namelist():
            return {}
        links = {}
        for item in elements(self.part(path), "Relationship"):
            target = item.get("Target", "")
            if not target or item.get("TargetMode") == "External" or ":" in target or "\\" in target:
                continue
            target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(directory, target))
            if target.startswith("../") or target == "..":
                raise ValueError(f"包关系越界: {target}")
            links[item.get("Id")] = target
        return links
