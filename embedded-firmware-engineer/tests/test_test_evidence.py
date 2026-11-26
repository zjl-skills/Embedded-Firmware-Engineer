import hashlib
import json
import sys

from support import ProjectCase


class EvidenceTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")
        self.trace = self.make_trace()
        self.manifest = "evidence/run.json"
        self.log = "evidence/exec.json"

    def record(self, *, requirement="REQ-1", script="print('PASS CONTRACT')", code=0):
        return self.report("record_test_evidence", "--test-id", "T-READ", "--requirement-id", requirement,
                           "--kind", "Host Unit Test", "--toolchain-version", sys.version.split()[0],
                           "--command-json", json.dumps([sys.executable, "-c", script]), "--stdout-contains", "PASS CONTRACT",
                           "--input", "tests/read_test.c", "--input", "src/driver.c", "--output", self.manifest,
                           "--log", self.log, code=code)

    def strict(self, *, kind="Host Unit Test"):
        self.trace.update(evidence_policy="structured")
        self.trace["tests"][0]["evidence"] = self.manifest
        self.trace["requirements"][0]["verification_kinds"] = [kind]
        self.write_state("traceability", self.trace)

    def test_actual_execution_and_bound_log_verified_in_both_commands(self):
        record = self.record()
        self.strict()
        self.assertEqual(record["sha256"], hashlib.sha256((self.root / self.log).read_bytes()).hexdigest())
        self.assertEqual(record["status"], "Passed")
        self.assertEqual(self.report("generate_traceability")["gaps"], [])
        self.assertEqual(self.report("validate_project")["errors"], 0)
        self.put("src/driver.c", "int changed(void) { return 1; }\n")
        result = self.report("generate_traceability", code=1)
        self.assertTrue(any(gap["kind"] == "invalid_test_evidence" and "输入 SHA-256" in gap["detail"] for gap in result["gaps"]))

    def test_modified_log_cannot_support_verified(self):
        self.record()
        self.strict()
        self.put(self.log, (self.root / self.log).read_bytes() + b"\n")
        result = self.report("generate_traceability", code=1)
        self.assertTrue(any("日志 SHA-256" in str(gap["detail"]) for gap in result["gaps"]))

    def test_wrong_requirement_or_verification_kind_cannot_be_promoted(self):
        self.record(requirement="REQ-OTHER")
        self.strict(kind="Hardware Test")
        result = self.report("generate_traceability", code=1)
        self.assertEqual({gap["kind"] for gap in result["gaps"]}, {"verification_not_proven", "verification_kind_missing"})

    def test_failed_execution_records_failure_and_does_not_pass(self):
        record = self.record(script="print('PASS CONTRACT'); raise SystemExit(9)", code=1)
        self.strict()
        self.assertEqual(record["actual"]["exit_code"], 9)
        self.assertEqual(record["status"], "Failed")
        self.assertIn("invalid_test_evidence", {gap["kind"] for gap in self.report("generate_traceability", code=1)["gaps"]})

    def test_legacy_records_are_readable_but_strict_requires_retest(self):
        result = self.report("generate_traceability")
        self.assertEqual(result["requirements"][0]["evidence_assurance"], "legacy_unconfirmed")
        self.assertEqual(result["legacy_test_evidence"], ["T-READ"])
        self.assertIn("invalid_test_evidence", {gap["kind"] for gap in self.report("generate_traceability", "--require-structured-evidence", code=1)["gaps"]})

    def test_acceptance_binds_authority_and_exact_evidence(self):
        self.record()
        self.strict()
        requirement = self.trace["requirements"][0]
        requirement.update(status="Accepted", acceptance_evidence="evidence/acceptance.json")
        self.write_state("traceability", self.trace)
        self.put("evidence/acceptance.json", "{}")
        self.report("generate_traceability", code=1)
        authority = self.put("evidence/approval.md", "模拟责任人批准 REQ-1。\n")
        record = {"schema_version": 1, "evidence_type": "acceptance", "requirement_id": "REQ-1", "decision": "Accepted",
                  "approved_by": "Simulation Coordinator", "approved_at": "2026-11-25T00:00:00+00:00",
                  "authorization": {"path": "evidence/approval.md", "sha256": hashlib.sha256(authority.read_bytes()).hexdigest()},
                  "test_evidence_sha256": {"T-READ": hashlib.sha256((self.root / self.manifest).read_bytes()).hexdigest()}}
        self.put("evidence/acceptance.json", json.dumps(record))
        self.assertEqual(self.report("generate_traceability")["gaps"], [])
        self.put("evidence/approval.md", "模拟责任人未批准。\n")
        self.assertEqual(self.report("generate_traceability", code=1)["gaps"][0]["kind"], "acceptance_not_proven")
