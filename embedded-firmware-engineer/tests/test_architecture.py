from support import ProjectCase


class ArchitectureTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")
        self.config = self.read_state("config")

    def configure(self, *layers, include_dirs=None, **options):
        self.config["architecture"].update(layers=[{"prefix": p, "layer": level, "module": m} for p, level, m in layers],
                                           include_dirs=include_dirs or [], **options)
        self.write_state("config", self.config)

    def test_only_downward_edges_and_ordered_include_paths(self):
        self.put("src/bsp/board.h", "/* BSP */\n")
        self.put("src/app/board.h", "/* same name, not searched for angle include */\n")
        self.put("src/app/main.c", "#include <board.h>\n")
        self.configure(("src/bsp", 2, "BSP"), ("src/app", 6, "APP"), include_dirs=["src/bsp", "src/app"])
        report = self.report("check_architecture")
        self.assertEqual(report["coverage"], "checked")
        self.assertEqual(report["include_module_edges"], [
            {"from_module": "APP", "to_module": "BSP", "source": "src/app/main.c", "line": 1, "target": "src/bsp/board.h"}
        ])

    def test_upward_include_and_cycles_have_evidence(self):
        self.put("src/low/base.h", '# include "../high/top.h" /* upward */\n')
        self.put("src/high/top.h", '#include "../low/base.h"\n')
        self.configure(("src/low", 2, "BASE"), ("src/high", 6, "TOP"))
        report = self.report("check_architecture", code=1)
        self.assertEqual(report["violations"], [
            {"rule": "upward_include", "source": "src/low/base.h", "line": 1, "target": "src/high/top.h",
             "source_layer": 2, "target_layer": 6},
            {"rule": "module_cycle", "modules": ["BASE", "TOP"]},
        ])

    def test_application_restrictions_ignore_comments_and_strings(self):
        self.put("src/app/main.cpp", '''/*
#include "stm32_board.h"
HAL_Fake(); */
const char *description = R"note(
#include "stm32_fake.h"
GPIOA
)note";
const char *value = "HAL_Ignored";
#include \\
    "vendor/stm32_board.h"
HAL_Start();
auto port = GPIOA;
auto nearby = GPIOAB;
''')
        self.configure(("src/app", 6, "APP"), application_forbidden_includes=["stm32_"],
                       application_forbidden_symbols=["HAL_*", "GPIOA"])
        report = self.report("check_architecture", code=1)
        self.assertEqual([(row["line"], row["target"]) for row in report["violations"]],
                         [(9, "vendor/stm32_board.h"), (11, "HAL_Start"), (12, "GPIOA")])

    def test_declared_cycles_distinguish_acyclic_dependents(self):
        self.put("src/app.c", "int app(void) { return 0; }\n")
        self.configure(("src", 6, "APP"))
        self.write_state("traceability", {"schema_version": 1, "requirements": [], "tests": [], "modules": [
            {"id": name, "interfaces": [], "depends_on": dependencies}
            for name, dependencies in (("APP", ["A"]), ("A", ["B"]), ("B", ["A", "C"]), ("C", []), ("D", ["D"]))
        ]})
        result = self.report("check_architecture", code=1)
        self.assertEqual([row["modules"] for row in result["violations"]], [["A", "B"], ["D"]])

    def test_exact_exception_preserves_precise_rule_and_decision(self):
        self.put("src/api/ref.h", "/* Interface */\n")
        self.put("src/low/one.c", '#include "../api/ref.h"\n')
        self.put("src/low/two.c", '#include "../api/ref.h"\n')
        self.configure(("src", 2, "BASE"), ("src/api/ref.h", 4, "PORT"), exceptions=[
            {"rule": "upward_include", "source": "src/low/one.c", "target": "src/api/ref.h",
             "decision": "ADR-1", "rationale": "Approved bridge during migration"}
        ])
        report = self.report("check_architecture", code=1)
        self.assertEqual(report["exceptions_applied"][0]["decision"], "ADR-1")
        self.assertEqual([row["source"] for row in report["violations"]], ["src/low/two.c"])

    def test_coverage_and_unresolved_inputs_are_visible(self):
        self.put("src/app.c", '#include HEADER_MACRO\n#include <stdint.h>\n')
        self.put("other.c", "/* not mapped */\n")
        self.assertEqual(self.report("check_architecture", code=1)["coverage"], "not_configured")
        self.configure(("src", 6, "APP"))
        report = self.report("check_architecture")
        self.assertEqual(report["unmapped_code_files"], ["other.c"])
        self.assertEqual({item["reason"] for item in report["unresolved_includes"]}, {"nonliteral", "not_on_scan_paths"})
        self.put("src/legacy.c", b"\xc0\xff")
        self.assertEqual(self.report("check_architecture", code=1)["coverage"], "partial")
