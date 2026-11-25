"""适用范围和工程量比较，保留事实来源及旧冲突编号。"""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
import hashlib
import json
import re

from document_data import PRIORITIES
from engineering_units import interval_relation, quantify
from project_data import object_at, require, string_at, strings_at


DIMENSIONS = ("product", "variant", "board", "board_revision")


@dataclass(frozen=True)
class VersionRange:
    lower: tuple | None
    upper: tuple | None
    lower_inclusive: bool = True
    upper_inclusive: bool = True


def version(value):
    value = string_at(value, "applicability.versions")
    require(re.fullmatch(r"\d{1,8}(?:\.\d{1,8}){0,7}", value), f"版本范围需要数字点分版本: {value}")
    parts = tuple(map(int, value.split(".")))
    return parts + (0,) * (8 - len(parts))


def applicability(data):
    if data is None:
        return None
    data = object_at(data, "applicability")
    require(set(data) <= {*DIMENSIONS, "versions"}, "applicability 包含未支持的维度")
    require(bool(data), "applicability 至少需要一个适用维度")
    dimensions = {}
    for field in DIMENSIONS:
        if field in data:
            if isinstance(data[field], str):
                values = [string_at(data[field], field)]
            else:
                values = strings_at(data[field], field)
            require(values, f"applicability.{field} 范围不能为空")
            dimensions[field] = set(values)
    bounds = object_at(data.get("versions", {}), "applicability.versions")
    require(set(bounds) <= {"min", "max", "min_inclusive", "max_inclusive"}, "版本边界字段无效")
    low, high = (version(bounds[key]) if key in bounds else None for key in ("min", "max"))
    li, hi = bounds.get("min_inclusive", True), bounds.get("max_inclusive", True)
    require(type(li) is bool and type(hi) is bool, "版本边界包含状态需要布尔值")
    require(low is None or high is None or low < high or low == high and li and hi, "版本范围为空或倒置")
    require(dimensions or low is not None or high is not None, "版本范围至少需要一个边界")
    return dimensions, VersionRange(low, high, li, hi)


def scope_relation(first, second):
    a, b = first["applicability_data"], second["applicability_data"]
    if a is None and b is None:
        return "equal" if first["scope"] == second["scope"] else "distinct_legacy_scopes"
    if a is None or b is None:
        return "requires_mapping"
    dimensions_a, versions_a = a
    dimensions_b, versions_b = b
    if any(not dimensions_a[key] & dimensions_b[key] for key in dimensions_a.keys() & dimensions_b.keys()):
        return "disjoint"
    relation = interval_relation(versions_a, versions_b)
    return "overlap" if relation == "equal" and dimensions_a != dimensions_b else relation


def value_relation(first, second):
    a, b = first["quantity_data"], second["quantity_data"]
    if a is None and b is None:
        return "equal" if first["value"] == second["value"] else "different_text"
    if a is None or b is None:
        return "requires_review"
    if a.dimension != b.dimension:
        return "different_dimension"
    return interval_relation(a, b)


def pair_reports(groups):
    conflicts, overlaps, comparisons = [], [], []
    for (category, key), members in sorted(groups.items()):
        conflict_members = defaultdict(set)
        conflict_pairs = defaultdict(list)
        authorities = defaultdict(set)
        for a, b in combinations(members, 2):
            scope = scope_relation(a, b)
            value = value_relation(a, b)
            legacy = a["applicability_data"] is None and b["applicability_data"] is None
            pair = {"facts": sorted([a["id"], b["id"]]), "scope_relation": scope, "value_relation": value,
                    "category": category, "key": key, "scopes": [a["scope"], b["scope"]],
                    "applicability": [a.get("applicability"), b.get("applicability")],
                    "normalized": [a.get("normalized"), b.get("normalized")]}
            if not legacy or any(pair["normalized"]):
                comparisons.append(pair)
            if scope not in ("equal", "overlap"):
                continue
            anchor = a["scope"] if legacy else " / ".join(pair["facts"])
            if value in ("disjoint", "different_text", "different_dimension"):
                conflict_members[anchor].update(pair["facts"])
                conflict_pairs[anchor].append(pair)
            if a["authority"] == b["authority"] == "Authoritative":
                authorities[anchor].update([a["source"]["document"], b["source"]["document"]])
        for anchor, identifiers in sorted(conflict_members.items()):
            definitions = [{k: v for k, v in row.items() if k not in {"applicability_data", "quantity_data"}}
                           for row in members if row["id"] in identifiers]
            token = json.dumps([category, key, anchor], ensure_ascii=False).encode("utf-8")
            priority = min((row["severity"] for row in definitions), key=PRIORITIES.index)
            conflicts.append({"id": "CF-" + hashlib.sha256(token).hexdigest()[:12].upper(), "category": category,
                              "key": key, "scope": anchor, "severity": priority, "definitions": definitions,
                              "differences": conflict_pairs[anchor], "confirmation": "Pending Confirmation",
                              "technical_impact": f"需重新核对依赖工程事实 {key} 的设计、实现和验证。",
                              "recommendation": "按同一适用范围核对原始资料、容差与批准依据，由责任人确认。",
                              "dependent_work": "blocked_pending_confirmation" if priority == "P0" else "review"})
        for anchor, documents in sorted(authorities.items()):
            if len(documents) > 1:
                overlaps.append({"category": category, "key": key, "scope": anchor, "documents": sorted(documents)})
    return conflicts, overlaps, comparisons


def annotate(row, definition, scope):
    app = applicability(row.get("applicability"))
    quantity = quantify(row["value"], row.get("quantity"))
    result = {**definition, "scope": scope, "applicability_data": app, "quantity_data": quantity}
    if app is not None:
        result["applicability"] = row["applicability"]
    if quantity is not None:
        result["normalized"] = quantity.as_dict()
    return result
