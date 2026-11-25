from support import ProjectCase


class ValidationTests(ProjectCase):
    def test_missing_init_and_provisional_management_state(self):
        report = self.report("validate_project", code=1)
        missing = {item["detail"] for item in report["issues"] if item["code"] == "missing_management_file"}
        self.assertIn("PROJECT_BASELINE.md", missing)
        self.run_cli("init_project")
        report = self.report("validate_project")
        self.assertEqual(report["errors"], 0)
        self.assertGreater(report["warnings"], 0)
        self.report("validate_project", "--strict", code=1)

    def test_invalid_config_fields_report_errors(self):
        self.run_cli("init_project")
        config = self.read_state("config")
        config["architecture"]["layers"] = [{"prefix": "src", "layer": True}]
        self.write_state("config", config)
        report = self.report("validate_project", code=1)
        self.assertIn("invalid_architecture_config", {row["code"] for row in report["issues"]})
        self.put(".embedded/config.json", '{"schema_version":1,"mode":"B","mode":"C"}')
        self.assertIn("invalid_config", {row["code"] for row in self.report("validate_project", code=1)["issues"]})

    def test_active_hash_drift_and_missing_files(self):
        self.run_cli("init_project")
        row = self.prepare_document()
        self.put(row["path"], "Version: B\n")
        result = self.report("validate_project", "--check-hashes", code=1)
        self.assertIn("document_hash_changed", {row["code"] for row in result["issues"]})
        (self.root / row["path"]).unlink()
        result = self.report("validate_project", code=1)
        self.assertIn("missing_active_document", {row["code"] for row in result["issues"]})
        registry = self.read_state("documents")
        registry["documents"][0]["status"] = "Superseded"
        self.write_state("documents", registry)
        self.assertEqual(self.report("validate_project")["errors"], 0)

    def test_structured_fact_conflict_is_located_stable_and_scoped(self):
        self.run_cli("init_project")
        first = self.prepare_document("docs/a.md", "revision: A\nPulse pin: PIN-1\n")
        second = self.prepare_document("docs/b.md", "revision: B\nPulse pin: PIN-2\n")
        facts = {"schema_version": 1, "facts": [
            {"id": f"FACT-{number}", "category": "pin", "key": "pulse", "scope": scope, "value": value,
             "state": state, "severity": severity, "source": {"document": doc["id"], "locator": "line 2",
                                                              "excerpt": f"Pulse pin: {value}"}}
            for number, doc, value, scope, state, severity in (
                (1, first, "PIN-1", "Board-A", "Asserted", "P0"),
                (2, second, "PIN-2", "Board-A", "Asserted", "P1"),
                (3, second, "PIN-3", "Board-A", "Inferred", "P0"),
                (4, second, "PIN-4", "Board-B", "Asserted", "P0"),
            )
        ]}
        self.write_state("facts", facts)
        conflict, = self.report("validate_project", code=1)["fact_conflicts"]
        self.assertEqual(conflict["severity"], "P0")
        self.assertEqual([member["id"] for member in conflict["definitions"]], ["FACT-1", "FACT-2"])
        self.assertEqual(conflict["definitions"][0]["source"]["locator"], "line 2")
        facts["facts"].reverse()
        self.write_state("facts", facts)
        self.assertEqual(self.report("validate_project", code=1)["fact_conflicts"][0]["id"], conflict["id"])
        registry = self.read_state("documents")
        next(row for row in registry["documents"] if row["id"] == second["id"])["status"] = "Outdated"
        self.write_state("documents", registry)
        self.assertEqual(self.report("validate_project")["fact_conflicts"], [])

    def test_planned_gap_can_be_warning_and_verified_gap_is_error(self):
        self.run_cli("init_project")
        data = {"schema_version": 1, "modules": [], "tests": [], "requirements": [
            {"id": "REQ-1", "title": "Pending", "priority": "P1", "status": "Proposed"}
        ]}
        self.write_state("traceability", data)
        issues = self.report("validate_project")["issues"]
        self.assertEqual({row["severity"] for row in issues if row["code"] == "traceability_gap"}, {"warning"})
        data["requirements"][0]["status"] = "Verified"
        self.write_state("traceability", data)
        issues = self.report("validate_project", code=1)["issues"]
        self.assertEqual({row["severity"] for row in issues if row["code"] == "traceability_gap"}, {"error"})

    def test_unconfirmed_fact_scope_is_reported_without_assigning_a_board(self):
        self.run_cli("init_project")
        doc = self.prepare_document()
        self.write_state("facts", {"schema_version": 1, "facts": [
            {"id": "FACT-1", "category": "pin", "key": "SAMPLE_READY", "scope": None, "value": "SIM_IRQ_4",
             "severity": "P0", "state": "Asserted", "source": {"document": doc["id"], "locator": "行 4", "excerpt": "SIM_IRQ_4"}}
        ]})
        report = self.report("validate_project")
        self.assertEqual(report["fact_conflicts"], [])
        finding, = [item for item in report["issues"] if item["code"] == "unconfirmed_fact_scope"]
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(finding["detail"]["source"]["locator"], "行 4")
        self.report("validate_project", "--strict", code=1)
