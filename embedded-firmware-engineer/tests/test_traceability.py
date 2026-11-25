from support import ProjectCase


class TraceabilityTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")

    def test_complete_chain_outputs_json_and_markdown(self):
        self.make_trace()
        json_report = self.report("generate_traceability")
        self.assertFalse(json_report["gaps"])
        req = json_report["requirements"][0]
        self.assertEqual(req["links"][0]["design"], "design/driver.md")
        self.assertEqual(req["links"][0]["interface_path"], "src/driver.h")
        report = self.run_cli("generate_traceability", "--format", "md").stdout
        self.assertIn(r"返回状态 \| 成功", report)
        self.assertIn("T-READ", report)

    def test_additional_source_scope_detects_untracked_implementations(self):
        self.make_trace()
        self.put("src/unowned.cpp", "int forgotten() { return 42; }\n")
        self.put("third_party/code.cpp", "/* not in requested scope */\n")
        report = self.report("generate_traceability", "--scan-code", "src", code=1)
        self.assertEqual(report["gaps"], [{"kind": "code_without_requirement", "id": "src/unowned.cpp", "detail": None}])

    def test_missing_links_and_reverse_coverage(self):
        data = self.make_trace(status="Confirmed")
        data["requirements"][0]["links"] = []
        self.write_state("traceability", data)
        report = self.report("generate_traceability", code=1)
        self.assertEqual({gap["kind"] for gap in report["gaps"]},
                         {"missing_implementation_chain", "code_without_requirement", "test_without_requirement"})

    def test_accepted_requires_test_pass_and_acceptance_record(self):
        data = self.make_trace(status="Accepted")
        data["tests"][0]["status"] = "Failed"
        self.write_state("traceability", data)
        report = self.report("generate_traceability", code=1)
        self.assertEqual({gap["kind"] for gap in report["gaps"]}, {"verification_not_proven", "acceptance_not_proven"})
        self.put("evidence/acceptance.txt", "Acceptance approved for the simulation.")
        data["requirements"][0]["acceptance_evidence"] = "evidence/acceptance.txt"
        data["tests"][0]["status"] = "Passed"
        self.write_state("traceability", data)
        self.assertFalse(self.report("generate_traceability")["gaps"])

    def test_foreign_interface_and_duplicate_ids_are_reported(self):
        data = self.make_trace()
        data["requirements"][0]["links"][0]["interface"] = "IF-UNKNOWN"
        self.write_state("traceability", data)
        report = self.report("generate_traceability", code=1)
        self.assertIn("unknown_interface", {gap["kind"] for gap in report["gaps"]})
        data["requirements"].append(data["requirements"][0])
        self.write_state("traceability", data)
        self.run_cli("generate_traceability", code=2)

    def test_deferred_requirement_retains_decision(self):
        data = {"schema_version": 1, "modules": [], "tests": [], "requirements": [
            {"id": "REQ-2", "title": "功能延后", "priority": "P2", "status": "Deferred"}
        ]}
        self.write_state("traceability", data)
        result = self.report("generate_traceability", code=1)
        self.assertEqual(result["gaps"][0]["kind"], "inactive_without_decision")
        data["requirements"][0]["decision"] = "ADR-2"
        self.write_state("traceability", data)
        self.assertFalse(self.report("generate_traceability")["gaps"])
