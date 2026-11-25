import hashlib
import sys

from support import ProjectCase, SCRIPTS

sys.path.insert(0, str(SCRIPTS))
from document_data import save_registry  # noqa: E402
from project_data import DataError  # noqa: E402


class DocumentRegistryTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project")

    def test_preview_is_read_only_and_new_rows_have_stable_ids(self):
        path = self.put("需求.md", "版本：V1\n正文\n")
        before = (self.state / "documents.json").read_bytes()
        row = self.report("inventory_documents", "--capture-text")["documents"][0]
        self.assertEqual(row["fingerprint"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(row["fingerprint"]["observed_version"], "V1")
        self.assertEqual(row["status"], "Pending Confirmation")
        self.assertEqual(row["authority"], "Unreviewed")
        self.assertIsNone(row["version"])
        self.assertEqual((self.state / "documents.json").read_bytes(), before)
        result = self.report("inventory_documents", "--update-registry", "--capture-text")
        self.assertEqual(result["added"], [row["id"]])
        self.assertIn("正文", self.read_state("documents")["documents"][0]["fingerprint"]["text_snapshot"])

    def test_registry_merge_preserves_reviewed_fields_and_accepted_hash(self):
        row = self.prepare_document()
        row.update(status="Valid", authority="Authoritative", version="A", scope="BOARD-A", impact="P0")
        self.write_state("documents", {"schema_version": 1, "documents": [row]})
        self.put("docs/req.md", "Version: B\n")
        self.put("docs/board.svg", "<svg/>\n")
        result = self.report("inventory_documents", "--update-registry", "--capture-text")
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(self.read_state("documents")["documents"][0], row)

    def test_format_limit_and_root_overlap(self):
        config = self.read_state("config")
        config["document_roots"] = ["docs", "docs/board"]
        self.write_state("config", config)
        self.put("docs/board/circuit.pdf", b"%PDF\n")
        self.put("docs/board/legacy.doc", b"\xd0\xcf\x11\xe0")
        self.put("docs/board/board.kicad_sch", "(kicad_sch (version 20250114))")
        self.put("docs/board/big.txt", b"A" * (32 * 1024 + 1))
        self.put("docs/board/legacy.txt", b"\xff\xff")
        self.put("ignored.md", "Outside the document root")
        rows = self.report("inventory_documents", "--capture-text")["documents"]
        self.assertEqual(len(rows), 5)
        compare = {row["name"]: row["fingerprint"]["comparison"] for row in rows}
        self.assertEqual(compare["circuit.pdf"], "hash_only")
        self.assertEqual(compare["legacy.doc"], "hash_only")
        self.assertEqual(compare["big.txt"], "hash_only")
        self.assertEqual(compare["legacy.txt"], "unsupported_text_encoding")
        self.assertEqual(compare["board.kicad_sch"], "utf8_text")

    def test_stale_writer_keeps_newer_content_and_releases_lock(self):
        path = self.state / "documents.json"
        original = path.read_bytes()
        replacement = original + b"\n"
        path.write_bytes(replacement)
        with self.assertRaises(DataError):
            save_registry((self.root, self.state), {"schema_version": 1, "documents": []}, original)
        self.assertEqual(path.read_bytes(), replacement)
        self.assertFalse((self.state / "documents.json.lock").exists())

    def test_another_writer_lock_is_not_removed(self):
        lock = self.put(".embedded/documents.json.lock", "pid=other\n")
        self.put("docs/input.md", "text\n")
        self.run_cli("inventory_documents", "--update-registry", code=2)
        self.assertEqual(lock.read_bytes(), b"pid=other\n")
        self.assertEqual(self.read_state("documents")["documents"], [])
