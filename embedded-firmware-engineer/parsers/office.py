"""Office Open XML 与 CSV 中的文字、表格、单元格及嵌入图像位置。"""

import csv
import io

from .base import BaseParser, Package, Unavailable, attribute, children, elements, read_text, tag


def text_in(node):
    return "".join(item.text or "" for item in elements(node, "t"))


def images(package, part, body, report, location):
    found = list(elements(body, "blip"))
    if not found:
        return
    rels = package.relationships(part)
    for index, image in enumerate(found, 1):
        rel = attribute(image, "embed") or attribute(image, "link")
        asset = rels.get(rel)
        if asset and asset in package.namelist():
            report.add("image", {"package_part": asset}, rel, {**location, "image": index})
        else:
            report.partial("发现外链或缺失的图像关系，未访问外部资源。")


class OfficeParser(BaseParser):
    suffixes = {".doc", ".docx"}
    fallback = "旧 DOC 请导出 DOCX 或 PDF。"

    def capability(self, suffix):
        return "builtin" if suffix == ".docx" else "export"

    def extract(self, path, report):
        if self.capability(path.suffix.lower()) == "export":
            raise Unavailable(self.fallback)
        report.method = "ooxml-word"
        part = "word/document.xml"
        with Package(path) as package:
            body = next(elements(package.part(part), "body"))
            for index, block in enumerate(body, 1):
                location = {"part": part, "block": index}
                if tag(block) == "p" and (text := text_in(block)):
                    style = next(elements(block, "pStyle"), None)
                    style_name = attribute(style, "val") if style is not None else None
                    report.add("paragraph", {"text": text, "style": style_name}, text, location)
                elif tag(block) == "tbl":
                    for number, row in enumerate(children(block, "tr"), 1):
                        values = [text_in(cell) for cell in children(row, "tc")]
                        report.add("table_row", values, values, {**location, "row": number})
                images(package, part, block, report, location)
        report.limitations.append("段落及表按文档 XML 定位。分页、文本框、版面与图像像素需要渲染或视觉核对。")


class SpreadsheetParser(BaseParser):
    suffixes = {".xls", ".xlsx", ".csv", ".tsv"}
    fallback = "旧 XLS 请导出 XLSX。CSV 适合只需要显示值的情况。"

    def capability(self, suffix):
        return "export" if suffix == ".xls" else "builtin"

    def extract(self, path, report):
        suffix = path.suffix.lower()
        if suffix == ".xls":
            raise Unavailable(self.fallback)
        if suffix in {".csv", ".tsv"}:
            report.method = "csv"
            reader = csv.reader(io.StringIO(read_text(path), newline=""), delimiter="\t" if suffix == ".tsv" else ",", strict=True)
            start = 1
            for number, values in enumerate(reader, 1):
                report.add("table_header" if number == 1 else "table_row", values, values,
                           {"row": number, "line": start, "line_end": reader.line_num}, confidence="medium" if number == 1 else "high")
                start = reader.line_num + 1
            return
        report.method = "ooxml-spreadsheet"
        with Package(path) as package:
            part = "xl/workbook.xml"
            links = package.relationships(part)
            sheets = package.part(part)
            shared = [text_in(item) for item in elements(package.part("xl/sharedStrings.xml"), "si")] if "xl/sharedStrings.xml" in package.namelist() else []
            for sheet in elements(sheets, "sheet"):
                name = sheet.get("name")
                sheet_part = links.get(attribute(sheet, "id"))
                if not sheet_part:
                    report.partial(f"跳过无内部关系的工作表 {name}")
                    continue
                first = True
                for row in elements(package.part(sheet_part), "row"):
                    if not children(row, "c"):
                        continue
                    for cell in children(row, "c"):
                        self.cell(cell, shared, report, {"sheet": name, "cell": cell.get("r"), "part": sheet_part}, first)
                    first = False
        report.limitations.append("首个非空行仅为表头候选。原始值按 XML 类型保存，公式只读取已有缓存，日期和格式未计算。")

    def cell(self, cell, shared, report, location, header):
        if not location["cell"]:
            report.partial("有单元格缺少原始坐标")
            return
        value = next(elements(cell, "v"), None)
        formula = next(elements(cell, "f"), None)
        raw = value.text if value is not None else None
        kind = cell.get("t", "n")
        resolved = raw
        if kind == "s" and raw is not None:
            index = int(raw)
            if not 0 <= index < len(shared):
                raise ValueError("共享字符串索引越界")
            resolved = shared[index]
        elif kind == "inlineStr":
            resolved = raw = text_in(cell)
        elif kind == "b" and raw in ("0", "1"):
            resolved = raw == "1"
        if raw is None and formula is None:
            return
        source = {"value": raw, "formula": formula.text if formula is not None else None}
        result = {"value": resolved, "type": kind, "header_candidate": header, "style": cell.get("s")}
        if formula is not None:
            result.update(formula=formula.text, formula_attributes=formula.attrib, cached_value=resolved)
        report.add("table_cell", result, source, location)


class PresentationParser(BaseParser):
    suffixes = {".ppt", ".pptx"}
    fallback = "旧 PPT 请导出 PPTX 或保留页序的 PDF。"

    def capability(self, suffix):
        return "builtin" if suffix == ".pptx" else "export"

    def extract(self, path, report):
        if self.capability(path.suffix.lower()) == "export":
            raise Unavailable(self.fallback)
        report.method = "ooxml-presentation"
        with Package(path) as package:
            main = "ppt/presentation.xml"
            links = package.relationships(main)
            for number, slide in enumerate(elements(package.part(main), "sldId"), 1):
                part = links.get(next((value for key, value in slide.attrib.items() if key.endswith("}id")), None))
                if not part:
                    report.partial(f"第 {number} 页缺少内部幻灯片关系")
                    continue
                body = package.part(part)
                location = {"slide": number, "part": part}
                for index, paragraph in enumerate(elements(body, "p"), 1):
                    if text := text_in(paragraph):
                        report.add("slide_text", text, text, {**location, "paragraph": index})
                for index, row in enumerate(elements(body, "tr"), 1):
                    values = [text_in(cell) for cell in children(row, "tc")]
                    report.add("table_row", values, values, {**location, "row": index})
                images(package, part, body, report, location)
        report.limitations.append("位置取自幻灯片部件，图形遮挡、图像内容和演讲者备注需另行核对。")
