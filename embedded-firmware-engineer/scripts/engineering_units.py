"""工程单位与数值区间。比较使用精确有理数。"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import re

from project_data import DataError, object_at, require, string_at


NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
UNIT = r"[A-Za-zΩΩµμ°℃℉/]+"
INTERVAL = re.compile(rf"({NUMBER})\s*(?:\.\.|[–—~～]|\s-\s)\s*({NUMBER})\s*({UNIT})")
TOLERANCE = re.compile(rf"({NUMBER})\s*({UNIT})?\s*(?:±|\+/-)\s*({NUMBER})\s*({UNIT}|%)?")
SINGLE = re.compile(rf"(<=|>=|[<>≤≥])?\s*({NUMBER})\s*({UNIT})")
SI = {"p": -12, "n": -9, "u": -6, "µ": -6, "m": -3, "c": -2, "d": -1, "": 0,
      "k": 3, "M": 6, "G": 9, "T": 12}
BASE = {"V": "voltage", "A": "current", "Ω": "resistance", "F": "capacitance", "Hz": "frequency",
        "s": "time", "m": "length", "bit/s": "data_rate", "B": "storage"}


def build_units():
    units = {}
    for base, dimension in BASE.items():
        aliases = {"Ω": ("Ω", "ohm", "Ohm"), "bit/s": ("bit/s", "bps")}.get(base, (base,))
        for prefix, power in SI.items():
            for alias in aliases:
                units[prefix + alias] = (dimension, base, Fraction(10) ** power, Fraction(0))
        if base == "bit/s":
            for prefix in ("", "k", "M", "G", "T"):
                units[prefix + "B/s"] = (dimension, base, 8 * Fraction(10) ** SI[prefix], Fraction(0))
    units.update({
        "°C": ("temperature", "°C", Fraction(1), Fraction(0)),
        "°F": ("temperature", "°C", Fraction(5, 9), Fraction(-160, 9)),
        "K": ("temperature", "°C", Fraction(1), Fraction(-27315, 100)),
        "in": ("length", "m", Fraction(254, 10000), Fraction(0)),
        "min": ("time", "s", Fraction(60), Fraction(0)),
        "h": ("time", "s", Fraction(3600), Fraction(0)),
        "bit": ("storage", "B", Fraction(1, 8), Fraction(0)),
        "KB": ("storage", "B", Fraction(1000), Fraction(0)),
    })
    for index, prefix in enumerate(("Ki", "Mi", "Gi", "Ti"), 1):
        units[prefix + "B"] = ("storage", "B", Fraction(1024 ** index), Fraction(0))
    return units


UNITS = build_units()


def unit_key(unit):
    return unit.replace("μ", "µ").replace("Ω", "Ω").replace("℃", "°C").replace("℉", "°F")


def number(value):
    require(type(value) in (int, float, str), f"无效工程数值: {value!r}")
    text = str(value).strip()
    require(len(text) <= 80, "工程数值表示过长")
    try:
        exact = Decimal(text)
    except InvalidOperation as exc:
        raise DataError(f"无效工程数值: {value!r}") from exc
    require(exact.is_finite() and abs(exact.adjusted()) <= 100 and abs(exact.as_tuple().exponent) <= 100,
            f"工程数值超出可比较尺度: {value!r}")
    return Fraction(exact)


def display(value):
    if value is None:
        return None
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return str(value)
    with localcontext() as precision:
        precision.prec = 400
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


@dataclass(frozen=True)
class Quantity:
    dimension: str
    unit: str
    lower: Fraction | None
    upper: Fraction | None
    lower_inclusive: bool
    upper_inclusive: bool
    nominal: Fraction | None
    original: object
    original_unit: str

    def as_dict(self):
        return {"dimension": self.dimension, "unit": self.unit, "lower": display(self.lower), "upper": display(self.upper),
                "lower_inclusive": self.lower_inclusive, "upper_inclusive": self.upper_inclusive,
                "nominal": display(self.nominal), "original": self.original, "original_unit": self.original_unit}


def quantify(value, explicit=None):
    """结构化字段支持上下界和容差，文本只识别保守的独立数值模式。"""
    if explicit is not None:
        fields = object_at(explicit, "quantity")
    else:
        text = value.strip().replace("−", "-")
        if match := INTERVAL.fullmatch(text):
            fields = {"min": match[1], "max": match[2], "unit": match[3]}
        elif (match := TOLERANCE.fullmatch(text)) and (match[2] or match[4] and match[4] != "%"):
            unit = match[2] or match[4]
            fields = {"nominal": match[1], "tolerance": match[3], "unit": unit, "tolerance_unit": match[4] or unit}
        elif match := SINGLE.fullmatch(text):
            relation, amount, unit = match.groups()
            prefix = "min" if relation and relation.startswith((">", "≥")) else "max"
            fields = {"unit": unit, prefix: amount, prefix + "_inclusive": relation not in ("<", ">")} if relation else {"unit": unit, "nominal": amount}
        else:
            return None
    unit = string_at(fields.get("unit"), "quantity.unit")
    spec = UNITS.get(unit_key(unit))
    if spec is None and explicit is None:
        return None
    require(spec is not None, f"不支持的工程单位: {unit}")
    dimension, base, scale, offset = spec
    nominal = number(fields["nominal"]) if "nominal" in fields else None
    low = number(fields["min"]) if "min" in fields else None
    high = number(fields["max"]) if "max" in fields else None
    li, hi = fields.get("min_inclusive", True), fields.get("max_inclusive", True)
    require(type(li) is bool and type(hi) is bool, "区间端点包含状态需要布尔值")
    require(any(item is not None for item in (low, high, nominal)), "工程量缺名义值或界限")
    if "tolerance" in fields:
        require(nominal is not None and low is None and high is None, "容差需要名义值，并与显式上下限分开提供")
        amount = number(fields["tolerance"])
        require(amount >= 0, "容差必须非负")
        tolerance_unit = string_at(fields.get("tolerance_unit", unit), "quantity.tolerance_unit")
        if tolerance_unit == "%":
            delta = abs(nominal) * amount / 100
        else:
            other = UNITS.get(unit_key(tolerance_unit))
            require(other is not None and other[0] == dimension, "容差单位维度和名义值不同")
            delta = amount * other[2] / scale
        low, high = nominal - delta, nominal + delta
    elif low is None and high is None:
        low = high = nominal
    require(low is None or high is None or low < high or low == high and li and hi, "工程数值区间为空或倒置")
    if nominal is not None:
        require((low is None or low < nominal or low == nominal and li)
                and (high is None or nominal < high or nominal == high and hi), "名义值不在工程区间内")
    converted = [item * scale + offset if item is not None else None for item in (low, high, nominal)]
    return Quantity(dimension, base, converted[0], converted[1], li, hi, converted[2], fields if explicit is not None else value, unit)


def interval_relation(a, b):
    bounds_a = a.lower, a.upper, a.lower_inclusive if a.lower is not None else True, a.upper_inclusive if a.upper is not None else True
    bounds_b = b.lower, b.upper, b.lower_inclusive if b.lower is not None else True, b.upper_inclusive if b.upper is not None else True
    if bounds_a == bounds_b:
        return "equal"
    for left, right in ((a, b), (b, a)):
        if left.upper is not None and right.lower is not None:
            if left.upper < right.lower or left.upper == right.lower and not (left.upper_inclusive and right.lower_inclusive):
                return "disjoint"
    return "overlap"
