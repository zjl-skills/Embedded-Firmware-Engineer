"""检查发布目录的元数据、引用、语法与 CLI 入口。"""

import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "embedded-firmware-engineer"
sys.path.insert(0, str(SKILL / "scripts"))
from project_data import STATE_FILES

LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\((?:<([^>]+)>|([^\s)]+))\)")
CLI_FILES = {
    "init_project", "scan_project", "inventory_documents", "parse_documents", "check_document_changes",
    "generate_traceability", "check_architecture", "validate_project", "check_collaboration", "record_test_evidence",
}


def verify(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return path.read_text(encoding="utf-8-sig")


def check_metadata():
    source = read(SKILL / "SKILL.md")
    match = re.match(r"\A---\n(.+?)\n---(?:\n|$)", source, re.S)
    verify(match is not None, "SKILL.md 缺 YAML frontmatter")
    data = yaml.safe_load(match[1])
    name, description = data.get("name"), data.get("description")
    verify(name == SKILL.name and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) and len(name) <= 64, "Skill 名称无效")
    verify(isinstance(description, str) and 0 < len(description.strip()) <= 1024, "Skill 描述无效")
    verify(set(data) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}, "Skill 元数据存在未知字段")

    interface = yaml.safe_load(read(SKILL / "agents/openai.yaml"))["interface"]
    verify(isinstance(interface.get("display_name"), str) and interface["display_name"].strip(), "UI 名称无效")
    verify(isinstance(interface.get("short_description"), str) and 25 <= len(interface["short_description"]) <= 64, "UI 描述无效")
    verify(isinstance(interface.get("default_prompt"), str) and "$" + SKILL.name in interface["default_prompt"], "UI 调用示例无效")

    paths = sorted((SKILL / "agents/specialists").glob("*.toml"))
    verify(len(paths) == 9, "专业角色模板数不匹配")
    for path in paths:
        role = tomllib.loads(read(path))
        verify(set(role) == {"name", "description", "developer_instructions"}, f"角色配置字段不匹配: {path.name}")
        verify(role["name"] == path.stem and all(isinstance(value, str) and value.strip() for value in role.values()),
               f"角色配置值无效: {path.name}")


def check_markdown():
    relocated = {Path(path).name for path in STATE_FILES}
    routed = set()
    paths = sorted([*ROOT.glob("*.md"), *SKILL.rglob("*.md")])
    for path in paths:
        for match in LINK.finditer(read(path)):
            link = urlsplit(match[1] or match[2])
            if link.scheme or link.netloc or not link.path:
                continue
            local = (path.parent / unquote(link.path)).resolve()
            relative_template = path.is_relative_to(SKILL / "templates") and link.path in relocated
            verify(local.is_relative_to(ROOT) and (local.exists() or relative_template), f"断开的链接 {path.relative_to(ROOT)} → {link.path}")
            if path == SKILL / "SKILL.md" and local.is_relative_to(SKILL / "references"):
                routed.add(local)
    verify(routed == set((SKILL / "references").rglob("*.md")), "Reference 路由与实际文件不一致")
    return len(paths)


def main():
    check_metadata()
    docs = check_markdown()
    python = sorted(SKILL.rglob("*.py"))
    for path in [Path(__file__), *python]:
        compile(read(path), str(path), "exec")
    for path in SKILL.rglob("*.json"):
        json.loads(read(path))
    for name in sorted(CLI_FILES):
        path = SKILL / "scripts" / (name + ".py")
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(path), "--help"], capture_output=True, timeout=30)
        verify(result.returncode == 0 and b"usage:" in result.stdout, f"CLI --help 失败: {name}")
    print(f"Checked metadata, {docs} Markdown files, {len(python)} Python files, JSON and {len(CLI_FILES)} command interfaces.")


if __name__ == "__main__":
    main()
