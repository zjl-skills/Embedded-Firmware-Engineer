"""PDF、栅格图像、SVG 和流程图适配器。"""

import base64
import csv
import importlib.util
import io
import re
import shutil
import subprocess
from urllib.parse import unquote
import zlib

from .base import MAX_PART, BaseParser, ExtractionLimit, Package, Unavailable, attribute, elements, xml


def run_tool(command):
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError(exc.stderr.decode("utf-8", "replace").strip()[:500] or f"工具退出 {exc.returncode}") from exc
    except subprocess.TimeoutExpired as exc:
        raise Unavailable("解析工具 30 秒内未完成") from exc
    if len(result.stdout) > MAX_PART:
        raise ExtractionLimit("解析工具输出超过 8 MiB")
    return result.stdout.decode("utf-8")


class PdfParser(BaseParser):
    suffixes = {".pdf"}
    fallback = "安装 pdfplumber 或 Poppler pdftotext。扫描版可用 OCR/视觉工具并提供标注页码的文本。"

    def capability(self, suffix):
        if importlib.util.find_spec("pdfplumber"):
            return "pdfplumber"
        return "pdftotext" if shutil.which("pdftotext") else "optional_tool"

    def extract(self, path, report):
        report.method = self.capability(".pdf")
        if report.method == "optional_tool":
            raise Unavailable(self.fallback)
        if report.method == "pdftotext":
            text = run_tool([shutil.which("pdftotext"), "-enc", "UTF-8", "-layout", str(path), "-"])
            pages = text.split("\f")
            if pages and not pages[-1]:
                pages.pop()
            for number, page in enumerate(pages, 1):
                self.page_text(report, number, page)
            report.partial("Poppler 文本模式缺少表格几何和图像位置。可用 pdfplumber 继续检查。")
            return
        try:
            import pdfplumber
        except ImportError as exc:
            raise Unavailable(self.fallback) from exc
        try:
            with pdfplumber.open(path) as document:
                for page in document.pages:
                    number = page.page_number
                    self.page_text(report, number, page.extract_text() or "")
                    for index, table in enumerate(page.find_tables(), 1):
                        values = table.extract()
                        report.add("table", values, values, {"page": number, "table": index, "bbox": list(table.bbox)},
                                   confidence="medium")
                    for index, image in enumerate(page.images, 1):
                        bbox = [float(image[key]) for key in ("x0", "top", "x1", "bottom")]
                        name = str(image.get("name", ""))
                        report.add("image", {"name": name, "bbox": bbox}, name, {"page": number, "image": index, "bbox": bbox})
                    page.close()
        except (ExtractionLimit, Unavailable):
            raise
        except Exception as exc:
            raise ValueError(f"PDF 读取失败: {exc}") from exc
        report.limitations.append("图像记录提供页面坐标。复杂表格和图像内容需要复核。")

    @staticmethod
    def page_text(report, number, page):
        if page.strip():
            report.add("page_text", page, page, {"page": number})
        else:
            report.partial("存在无可读文本的页面，请用 OCR 或视觉检查。")


LABEL_TERMS = (
    ("mcu", r"\b(?:STM32|GD32|CH32|ESP32|NXP)[\w-]*|\bmcu\b"),
    ("power", r"\b(?:vdd\w*|vcc\w*|vbat|gnd|ground|power)\b"),
    ("clock", r"\b(?:osc\w*|clock|xtal\w*|mco\w*)\b"),
    ("reset", r"\b(?:n?rst|reset|nreset)\b"),
    ("interface", r"\b(?:uart\w*|usart\w*|i2c\w*|spi\w*|can\w*|usb\w*)\b"),
    ("pin", r"\b(?:p[a-z]\d+|gpio\w*|pin\w*|sim_pad\w*|sim_irq\w*)\b"),
)


def label_category(text, identifier=""):
    candidate = identifier.replace("-", " ") + " " + text
    if identifier in {"board-pad", "pin-label"}:
        return "pin"
    if identifier == "signal-label":
        return "net_label"
    for category, pattern in LABEL_TERMS:
        if re.search(pattern, candidate, re.I):
            return category
    return "label"


class ImageParser(BaseParser):
    suffixes = {".png", ".jpg", ".jpeg", ".svg", ".bmp", ".tif", ".tiff", ".webp"}
    fallback = "提供清晰图面与对应网表。文本可用 Tesseract，连接关系需要经批准资料复核。"

    def capability(self, suffix):
        if suffix == ".svg":
            return "svg-xml"
        if shutil.which("tesseract"):
            return "tesseract"
        return "pillow-metadata" if importlib.util.find_spec("PIL") else "visual_review"

    def extract(self, path, report):
        report.method = self.capability(path.suffix.lower())
        if report.method == "svg-xml":
            body = xml(path.read_bytes())
            count = 0
            for number, node in enumerate(elements(body, "text"), 1):
                if not (value := "".join(node.itertext()).strip()):
                    continue
                identifier = node.get("id", "")
                report.add(label_category(value, identifier), value, value,
                           {"element": "text", "index": number, "id": identifier or None, "x": node.get("x"), "y": node.get("y")},
                           confidence="medium", evidence="drawing_label")
                count += 1
            if not count:
                report.partial("SVG 未发现可读 text 标签，需视觉查看。")
            report.limitations.append("SVG 结果来自图面标签。几何线条、图层与实际硬件连接需独立确认。")
        elif report.method == "tesseract":
            result = run_tool([shutil.which("tesseract"), str(path), "stdout", "tsv"])
            for row in csv.DictReader(io.StringIO(result), delimiter="\t"):
                if row.get("text", "").strip():
                    value = row["text"]
                    box = [int(row[key]) for key in ("left", "top", "width", "height")]
                    report.add(label_category(value), value, value, {"page": int(row["page_num"]), "pixels_xywh": box},
                               confidence="medium" if float(row["conf"]) >= 80 else "low", evidence="ocr")
            report.partial("OCR 为图面候选。字符、网络连接和缺失符号需对照原图或网表。")
        elif report.method == "pillow-metadata":
            from PIL import Image
            with Image.open(path) as image:
                dimensions = {"width": image.width, "height": image.height, "format": image.format}
                report.add("image_metadata", dimensions, dimensions, {"image": 1})
            report.partial(self.fallback)
        else:
            raise Unavailable(self.fallback)


class DiagramParser(BaseParser):
    suffixes = {".drawio", ".dio", ".vsd", ".vsdx"}
    fallback = "旧 Visio 请导出 VSDX、SVG 或带页码的 PDF。"

    def capability(self, suffix):
        return "export" if suffix == ".vsd" else "builtin"

    def extract(self, path, report):
        suffix = path.suffix.lower()
        if suffix == ".vsd":
            raise Unavailable(self.fallback)
        if suffix == ".vsdx":
            report.method = "visio-package"
            with Package(path) as package:
                pages = "visio/pages/pages.xml"
                links = package.relationships(pages)
                for number, page in enumerate(elements(package.part(pages), "Page"), 1):
                    rel = next(elements(page, "Rel"), None)
                    part = links.get(attribute(rel, "id")) if rel is not None else None
                    if not part:
                        report.partial(f"Visio 第 {number} 页没有内部部件关系")
                        continue
                    body = package.part(part)
                    for name, category in (("Shape", "diagram_shape"), ("Connect", "diagram_edge")):
                        for index, item in enumerate(elements(body, name), 1):
                            data = dict(item.attrib)
                            text = next(elements(item, "Text"), None) if name == "Shape" else None
                            if text is not None:
                                data["text"] = "".join(text.itertext()).strip()
                            report.add(category, data, data, {"page": number, "part": part, "index": index, "id": item.get("ID")})
        else:
            report.method = "drawio-xml"
            root = xml(path.read_bytes())
            pages = list(elements(root, "diagram")) or [root]
            for number, page in enumerate(pages, 1):
                models = list(elements(page, "mxGraphModel"))
                if not models and page.text and page.text.strip():
                    blob = base64.b64decode("".join(page.text.split()), validate=True)
                    extractor = zlib.decompressobj(-15)
                    data = extractor.decompress(blob, MAX_PART + 1)
                    if len(data) > MAX_PART or extractor.unconsumed_tail:
                        raise ExtractionLimit("Draw.io 解压内容超过 8 MiB")
                    if not extractor.eof:
                        raise ValueError("Draw.io 压缩页不完整")
                    models = [xml(unquote(data.decode("ascii"), errors="strict").encode("utf-8"))]
                if not models:
                    report.partial(f"Draw.io 第 {number} 页没有可读图模型")
                for model in models:
                    for index, item in enumerate(elements(model, "mxCell"), 1):
                        if not (item.get("vertex") == "1" or item.get("edge") == "1" or item.get("value")):
                            continue
                        data = {key: item.get(key) for key in ("value", "source", "target")}
                        report.add("diagram_edge" if item.get("edge") == "1" else "diagram_shape", data, dict(item.attrib),
                                   {"page": number, "index": index, "id": item.get("id")})
        report.limitations.append("图元与连线来自工程文件。实物线路、可读文字和渲染结果需另外核对。")
