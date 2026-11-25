import sys
import unittest

from support import ProjectCase, SCRIPTS

sys.path.insert(0, str(SCRIPTS))
from engineering_units import interval_relation, quantify


class UnitsTests(unittest.TestCase):
    def test_dimensions_and_conversions(self):
        pairs = [("3.3V", "3300mV"), ("10ms", "0.01s"), ("2mA", "2000µA"), ("4.7kΩ", "4700ohm"),
                 ("1000nF", "1μF"), ("2MHz", "2000kHz"), ("68°F", "293.15K"), ("1in", "25.4mm"),
                 ("1MB/s", "8Mbps"), ("4KiB", "4096B")]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                first, second = quantify(a), quantify(b)
                self.assertEqual(first.dimension, second.dimension)
                self.assertEqual(interval_relation(first, second), "equal")
                self.assertEqual(first.as_dict()["original"], a)

    def test_tolerance_open_boundary_and_overlap(self):
        value = quantify("3.3 V ± 100 mV")
        self.assertEqual((value.as_dict()["lower"], value.as_dict()["upper"]), ("3.2", "3.4"))
        self.assertEqual(interval_relation(value, quantify("3.35–3.5V")), "overlap")
        self.assertEqual(interval_relation(value, quantify(">3.4V")), "disjoint")
        self.assertEqual(interval_relation(quantify("10V ± 5%"), quantify("9.5..10.5 V")), "equal")
        self.assertEqual(interval_relation(quantify("68°F ± 1.8°F"), quantify("20°C ± 1°C")), "equal")
        with self.assertRaisesRegex(ValueError, "倒置"):
            quantify("display", {"min": "7", "max": "2", "unit": "V"})


class FactComparisonTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")
        self.first = self.prepare_document("docs/a.md")
        self.second = self.prepare_document("docs/b.md")

    def fact(self, ident, doc, value, app=None):
        row = {"id": ident, "category": "electrical", "key": "VDD", "scope": "R1" if app is None else None,
               "value": value, "state": "Asserted", "severity": "P0",
               "source": {"document": doc["id"], "locator": "表 1", "excerpt": value}}
        if app is not None:
            row["applicability"] = app
        return row

    def compare(self, a, b, code=0):
        self.write_state("facts", {"schema_version": 1, "facts": [a, b]})
        return self.report("validate_project", code=code)

    def test_equivalent_values_maintain_original_definition(self):
        result = self.compare(self.fact("F1", self.first, "3.3V"), self.fact("F2", self.second, "3300mV"))
        self.assertFalse(result["fact_conflicts"])
        pair, = result["fact_comparisons"]
        self.assertEqual(pair["value_relation"], "equal")
        self.assertEqual(pair["normalized"][1]["original_unit"], "mV")
        self.assertEqual(pair["normalized"][1]["lower"], "3.3")

    def test_revision_variants_and_ranges_are_checked(self):
        a = self.fact("F1", self.first, "2.7–3.3 V", {"product": "X", "variant": "A", "versions": {"min": "1.0", "max": "2.0"}})
        b = self.fact("F2", self.second, "4.5–5.0V", {"product": "X", "variant": "B", "versions": {"min": "1.5"}})
        self.assertEqual(self.compare(a, b)["fact_comparisons"][0]["scope_relation"], "disjoint")
        b["applicability"]["variant"] = "A"
        b["applicability"]["versions"]["min"] = "2.1"
        self.assertEqual(self.compare(a, b)["fact_comparisons"][0]["scope_relation"], "disjoint")
        b["applicability"]["versions"]["min"] = "1.5"
        conflict, = self.compare(a, b, code=1)["fact_conflicts"]
        self.assertEqual(conflict["severity"], "P0")
        self.assertEqual(conflict["dependent_work"], "blocked_pending_confirmation")
        self.assertEqual(conflict["differences"][0]["scope_relation"], "overlap")
        b["value"] = "3.0–3.5V"
        self.assertEqual(self.compare(a, b)["fact_comparisons"][0]["value_relation"], "overlap")
