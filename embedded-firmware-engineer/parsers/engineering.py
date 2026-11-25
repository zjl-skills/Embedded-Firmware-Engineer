"""读取可定位的源文件、通用文本资料和 EDA 工程记录。"""

from dataclasses import dataclass, field
import importlib.util
import json
from math import isfinite
import re

from .base import BaseParser, ExtractionLimit, Unavailable, children, elements, read_text, tag, xml
from .visual import label_category


def json_constant(token):
    raise ValueError(f"无效 JSON 常量 {token}")


def json_number(token):
    value = float(token)
    return value if isfinite(value) else token


class SourceCodeParser(BaseParser):
    code = {".c", ".cpp", ".cc", ".cxx", ".c++", ".h", ".hpp", ".hh", ".hxx", ".h++", ".inc", ".s", ".ld", ".icf", ".sct"}
    suffixes = code | {".txt", ".md", ".rst", ".json", ".xml", ".yaml", ".yml", ".ini", ".mk", ".uvprojx", ".ewp", ".ioc"}

    def recognizes(self, path):
        return super().recognizes(path) or path.name.casefold() in {"makefile", "cmakelists.txt"}

    def capability(self, suffix):
        if suffix in {".yaml", ".yml"}:
            return "yaml-events" if importlib.util.find_spec("yaml") else "optional_tool"
        return "builtin"

    def extract(self, path, report):
        suffix = path.suffix.lower()
        if suffix in {".xml", ".uvprojx", ".ewp"}:
            report.method = "xml-elements"
            for index, item in enumerate(xml(path.read_bytes()).iter(), 1):
                if item.attrib or (item.text and item.text.strip()):
                    content = {"tag": tag(item), "attributes": item.attrib, "text": item.text}
                    report.add("xml_element", content, content, {"element": index, "tag": tag(item)})
            return
        text = read_text(path)
        if suffix == ".json":
            report.method = "json"
            data = json.loads(text, parse_constant=json_constant, parse_float=json_number)
            report.add("json_value", data, text, {"json_pointer": ""})
            return
        if suffix in {".yaml", ".yml"}:
            if self.capability(suffix) == "optional_tool":
                raise Unavailable("安装 PyYAML，或提供 JSON / TXT 导出。")
            import yaml
            report.method = "yaml-events"
            try:
                for event in yaml.parse(text, Loader=yaml.SafeLoader):
                    if isinstance(event, yaml.events.ScalarEvent):
                        start, end = event.start_mark, event.end_mark
                        report.add("yaml_scalar", event.value, text[start.index:end.index], {"line": start.line + 1, "column": start.column + 1})
            except yaml.YAMLError as exc:
                raise ValueError(f"YAML 语法错误: {exc}") from exc
            report.limitations.append("YAML 保留词法位置，不展开别名、执行标签或解释构建语义。")
            return
        report.method = "source-lines" if suffix in self.code else "utf8-lines"
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            if suffix in self.code:
                directive = re.match(r"^\s*#\s*(include|define)\s+(.+)$", line)
                if directive:
                    report.add("source_" + directive[1], directive[2], line, {"line": number}, confidence="medium")
                continue
            category = "heading" if line.lstrip().startswith("# ") else "text"
            report.add(category, line.strip(), line, {"line": number})
        if suffix in self.code:
            report.limitations.append("只读取源码行中的 include 和宏候选，预处理活动分支、寄存器及 ABI 需独立核对。")
            if not report.facts:
                report.partial("未发现可定位的 include 或宏。")


@dataclass
class Node:
    line: int
    values: list = field(default_factory=list)

    @property
    def name(self):
        return self.values[0] if self.values else ""

    def items(self, name):
        return (value for value in self.values if isinstance(value, Node) and value.name == name)

    def item(self, name):
        return next(self.items(name), None)

    def args(self):
        return [value for value in self.values[1:] if isinstance(value, str)]

    def first(self, name):
        item = self.item(name)
        return next(iter(item.args()), None) if item else None


SEXPR = re.compile(r'\s+|;[^\n]*|[()]|"(?:\\.|[^"\\])*"|[^()\s";]+', re.S)


def sexpr(text):
    head = Node(1)
    stack = [head]
    index, line = 0, 1
    for token in SEXPR.finditer(text):
        if token.start() != index:
            raise ValueError(f"第 {line} 行 S-expression 记号不完整")
        value = token[0]
        if value == "(":
            if len(stack) > 128:
                raise ExtractionLimit("S-expression 嵌套超过 128 层")
            node = Node(line)
            stack[-1].values.append(node)
            stack.append(node)
        elif value == ")":
            if len(stack) == 1:
                raise ValueError(f"第 {line} 行括号不匹配")
            stack.pop()
        elif not value.isspace() and not value.startswith(";"):
            stack[-1].values.append(re.sub(r'\\(["\\])', r'\1', value[1:-1]) if value.startswith('"') else value)
        line += value.count("\n")
        index = token.end()
    if index != len(text) or len(stack) != 1 or len(head.values) != 1 or not isinstance(head.values[0], Node):
        raise ValueError("S-expression 文件不完整")
    return head.values[0]


def properties(node):
    result = {}
    for item in node.items("property"):
        args = item.args()
        if len(args) >= 2:
            result[args[0]] = args[1]
    return result


class EdaParser(BaseParser):
    suffixes = {".kicad_sch", ".kicad_pcb", ".net", ".schdoc", ".pcbdoc", ".prjpcb"}
    fallback = "请导出 KiCad XML/S-expression 网表、Altium ASCII 记录、BOM CSV 或器件标注 PDF。"

    def recognizes(self, path):
        if super().recognizes(path):
            return True
        if path.suffix.lower() == ".xml":
            with path.open("rb") as handle:
                return bool(re.search(rb"<(?:\w+:)?export[\s>]", handle.read(8192)))
        return False

    def capability(self, suffix):
        return "ascii_or_export" if suffix in {".schdoc", ".pcbdoc"} else "builtin"

    def extract(self, path, report):
        suffix = path.suffix.lower()
        try:
            text = read_text(path)
        except (UnicodeError, Unavailable) as exc:
            raise Unavailable(self.fallback) from exc
        if suffix in {".schdoc", ".pcbdoc", ".prjpcb"}:
            report.method = "altium-text"
            for number, line in enumerate(text.splitlines(), 1):
                if line.startswith("|") and "=" in line:
                    fields = dict(term.split("=", 1) for term in line.split("|") if "=" in term)
                    report.add("eda_record", fields, line, {"line": number}, confidence="medium")
                elif suffix == ".prjpcb" and re.match(r"^\s*(\[[^]]+\]|\w+\s*=)", line):
                    report.add("project_setting", line.strip(), line, {"line": number})
            if not report.facts:
                raise Unavailable(self.fallback)
            report.partial("Altium 记录按明示字段读取。连接恢复需要独立网表。")
        elif text.lstrip().startswith("<"):
            report.method = "kicad-xml-netlist"
            self.net_xml(xml(path.read_bytes()), report)
        else:
            report.method = "kicad-sexpr"
            body = sexpr(text)
            if body.name == "export":
                self.net_sexpr(body, report)
            elif body.name in {"kicad_sch", "kicad_pcb"}:
                self.native(body, report)
            else:
                raise Unavailable(self.fallback)

    @staticmethod
    def net_xml(body, report):
        if tag(body) != "export":
            raise Unavailable(EdaParser.fallback)
        for index, node in enumerate(elements(body, "comp"), 1):
            content = {"ref": node.get("ref"), **{tag(item): item.text for item in node if tag(item) in {"value", "footprint"}}}
            report.add("component", content, content, {"element": "comp", "index": index, "ref": node.get("ref")})
        for index, net in enumerate(elements(body, "net"), 1):
            for number, node in enumerate(children(net, "node"), 1):
                content = {"net": net.get("name"), **node.attrib}
                report.add("net_connection", content, content, {"element": "net/node", "net": index, "node": number}, evidence="netlist")

    @staticmethod
    def net_sexpr(body, report):
        components, nets = body.item("components"), body.item("nets")
        if components:
            for node in components.items("comp"):
                content = {field: node.first(field) for field in ("ref", "value", "footprint")}
                report.add("component", content, content, {"line": node.line, "ref": content["ref"]})
        if nets:
            for net in nets.items("net"):
                for node in net.items("node"):
                    content = {"net": net.first("name"), **{field: node.first(field) for field in ("ref", "pin", "pinfunction", "pintype")}}
                    report.add("net_connection", content, content, {"line": node.line, "ref": content["ref"], "pin": content["pin"]}, evidence="netlist")

    @staticmethod
    def native(body, report):
        for index, node in enumerate((item for item in body.values if isinstance(item, Node)), 1):
            position = node.item("at")
            location = {"line": node.line, "index": index, "id": node.first("uuid") or node.first("tstamp"),
                        "at": position.args() if position else None}
            if node.name in {"symbol", "footprint"}:
                content = {"library": node.first("lib_id"), "properties": properties(node)}
                report.add("component", content, content, location, evidence="drawing_model")
                for number, pad in enumerate(node.items("pad"), 1):
                    net_record = pad.item("net")
                    if net_record:
                        content = {"pad": pad.args()[0] if pad.args() else None, "net": net_record.args(),
                                   "ref": properties(node).get("Reference")}
                        report.add("net_connection", content, content, {**location, "line": pad.line, "pad_index": number}, evidence="pcb_model")
            elif node.name in {"label", "global_label", "hierarchical_label"} and node.args():
                value = node.args()[0]
                category = label_category(value)
                report.add(category if category != "label" else "net_label", value, value, location,
                           confidence="medium", evidence="drawing_label")
            elif node.name == "wire" and (points := node.item("pts")):
                endpoints = [point.args() for point in points.items("xy")]
                report.add("wire_geometry", endpoints, endpoints, location, evidence="drawing_model")
        report.limitations.append("原生图面提供图元和图形位置。多层级网络、引脚库映射及实物连通需要独立验证。")
