"""按资料格式选择实际可用的提取适配器。"""

from dataclasses import asdict
import binascii
import csv
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile
import zlib

from .base import MAX_FILE, ExtractionLimit, Result, Unavailable
from .engineering import EdaParser, SourceCodeParser
from .office import OfficeParser, PresentationParser, SpreadsheetParser
from .visual import DiagramParser, ImageParser, PdfParser


ADAPTERS = (PdfParser(), ImageParser(), OfficeParser(), SpreadsheetParser(), PresentationParser(),
            DiagramParser(), EdaParser(), SourceCodeParser())


def capabilities():
    return [{"adapter": type(adapter).__name__, "formats": {ext: adapter.capability(ext) for ext in sorted(adapter.suffixes)},
             "fallback": adapter.fallback} for adapter in ADAPTERS]


def extract(path, relative, *, document_id=None, version=None, scope=None):
    result = Result(relative, document_id, version, scope, None)
    try:
        if not path.is_file():
            raise OSError("源文件不存在或不可读")
        if path.stat().st_size > MAX_FILE:
            raise ExtractionLimit("输入超过 32 MiB，请提供分卷或受控导出")
        adapter = next((adapter for adapter in ADAPTERS if adapter.recognizes(path)), None)
        if adapter is None:
            result.status = "unsupported"
            result.error = "没有此格式的适配器，请提供可读导出。"
        else:
            result.adapter = type(adapter).__name__
            adapter.extract(path, result)
            if not result.facts and result.status == "parsed":
                result.partial("未发现可定位的内容。")
    except Unavailable as exc:
        result.status, result.error = "unavailable", str(exc)
    except ExtractionLimit as exc:
        result.partial(str(exc))
    except (ValueError, OSError, StopIteration, RecursionError, BadZipFile, ParseError, csv.Error, binascii.Error, zlib.error) as exc:
        result.status, result.error = "error", str(exc) or type(exc).__name__
    return asdict(result)
