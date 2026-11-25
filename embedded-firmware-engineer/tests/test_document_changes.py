import os

from support import ProjectCase


class DocumentChangeTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")

    def test_active_change_gate_and_metadata_only(self):
        doc = self.prepare_document()
        path = self.root / doc["path"]
        stamps = path.stat()
        os.utime(path, ns=(stamps.st_atime_ns, stamps.st_mtime_ns + 2_000_000_000))
        result = self.report("check_document_changes", "--fail-on-change")
        self.assertEqual(result["counts"]["metadata_only"], 1)
        self.assertEqual(result["active_changes"], 0)
        self.assertEqual(result["records"][0]["current"]["sha256"], doc["fingerprint"]["sha256"])

    def test_text_diff_version_delta_and_explicit_acceptance(self):
        doc = self.prepare_document(text="Revision: A\nUART baud = 9600\n")
        self.put(doc["path"], "Revision: B\nUART baud = 19200\n")
        result = self.report("check_document_changes", "--fail-on-change", code=1)
        row = result["records"][0]
        self.assertEqual(row["kind"], "content_changed")
        self.assertEqual(row["version_comparison"], {"baseline": "A", "current": "B", "state": "changed"})
        self.assertIn("-UART baud = 9600", row["text_difference"]["lines"])
        self.assertIn("+UART baud = 19200", row["text_difference"]["lines"])
        self.run_cli("inventory_documents", "--update-registry", "--accept",
                     f"{doc['id']}={doc['fingerprint']['sha256']}", code=2)
        self.assertEqual(self.read_state("documents")["documents"][0], doc)
        receipt = self.report("inventory_documents", "--update-registry", "--capture-text", "--accept",
                              f"{doc['id']}={row['current']['sha256']}")
        self.assertEqual(receipt["refreshed"], [doc["id"]])
        baseline = self.read_state("documents")["documents"][0]
        self.assertIsNone(baseline["version"])
        self.assertEqual(baseline["status"], "Pending Confirmation")
        self.assertEqual(self.report("check_document_changes", "--fail-on-change")["active_changes"], 0)

    def test_move_is_only_a_candidate_and_original_id_is_preserved(self):
        doc = self.prepare_document()
        (self.root / doc["path"]).rename(self.root / "docs/moved.md")
        result = self.report("check_document_changes", "--fail-on-change", code=1)
        records = {row["kind"]: row for row in result["records"]}
        self.assertEqual(records["missing"]["possible_moves_or_copies"], ["docs/moved.md"])
        self.assertEqual(records["missing"]["id"], doc["id"])
        self.assertEqual(records["added"]["path"], "docs/moved.md")
        self.assertEqual(self.read_state("documents")["documents"][0]["path"], doc["path"])

    def test_binary_difference_and_unbaselined_active_file(self):
        doc = self.prepare_document("docs/circuit.pdf", b"%PDF-1.4\x00")
        pending = self.prepare_document("docs/unbaselined.md", "new\n")
        registry = self.read_state("documents")
        next(row for row in registry["documents"] if row["id"] == pending["id"])["fingerprint"] = None
        self.write_state("documents", registry)
        self.put(doc["path"], b"%PDF-1.4\xff")
        result = self.report("check_document_changes")
        changes = {row["kind"]: row for row in result["records"]}
        self.assertEqual(changes["content_changed"]["text_difference"]["state"], "unavailable")
        self.assertEqual(changes["unbaselined"]["id"], pending["id"])

    def test_impact_walks_document_relations_and_module_consumers(self):
        config = self.read_state("config")
        config["document_roots"] = ["docs"]
        self.write_state("config", config)
        trace = self.make_trace()
        schematic = self.prepare_document("docs/board.txt", "Version: A\nFixture signal A\n")
        registry = self.read_state("documents")
        by_path = {row["path"]: row for row in registry["documents"]}
        requirement_doc, board_doc = by_path["docs/req.md"], by_path["docs/board.txt"]
        requirement_doc["related_documents"] = [board_doc["id"]]
        board_doc["impact"] = "P0"
        self.write_state("documents", registry)
        trace["modules"].append({"id": "MOD-APP", "design": "design/app.md", "interfaces": [],
                                 "code": ["src/app.c"], "depends_on": ["MOD-DRV"]})
        self.write_state("traceability", trace)
        self.put(schematic["path"], "Version: B\nFixture signal B\n")
        records = self.report("check_document_changes")["records"]
        impact = records[0]["impact"]
        self.assertEqual(impact["related_documents"], [requirement_doc["id"]])
        self.assertEqual(impact["requirements"], ["REQ-1"])
        self.assertEqual(impact["modules"], ["MOD-APP", "MOD-DRV"])
        self.assertEqual(impact["design"], ["design/app.md", "design/driver.md"])
        self.assertEqual(impact["interfaces"], ["src/driver.h"])
        self.assertEqual(impact["code"], ["src/app.c", "src/driver.c"])
        self.assertEqual(impact["tests"], ["T-READ"])
        self.assertEqual(impact["priority_hint"], "P0")

    def test_markdown_report_walks_facts_through_delivery_without_mutating_inputs(self):
        config = self.read_state("config")
        config["document_roots"] = ["docs"]
        self.write_state("config", config)
        trace = self.make_trace()
        doc = self.prepare_document("docs/component.md", "Version: A\nInput 5 V\n")
        self.put("delivery/guide.md", "old delivery\n")
        trace["requirements"][0]["deliverables"] = ["delivery/guide.md"]
        self.write_state("traceability", trace)
        self.write_state("facts", {"schema_version": 1, "facts": [{"id": "F-1", "key": "VIN",
                          "source": {"document": doc["id"], "locator": "行 2"}, "requirements": ["REQ-1"]}]})
        old_registry = (self.state / "documents.json").read_bytes()
        self.put(doc["path"], "Version: B\nInput 3 V\n")
        self.run_cli("check_document_changes", "--format", "md", "--output", ".embedded/reports/DOCUMENT_IMPACT.md",
                     "--fail-on-change", code=1)
        report = (self.state / "reports/DOCUMENT_IMPACT.md").read_text(encoding="utf-8")
        for term in ("F-1", "REQ-1", "src/driver.c", "T-READ", "delivery/guide.md", "待确认", "+Input 3 V"):
            self.assertIn(term, report)
        self.assertEqual((self.state / "documents.json").read_bytes(), old_registry)
        self.assertEqual((self.root / "delivery/guide.md").read_bytes(), b"old delivery\n")
