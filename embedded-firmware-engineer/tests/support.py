"""在独立临时目录通过公开 CLI 创建测试工程。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class ProjectCase(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="embedded-firmware-test-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve() / "固件 project"
        self.root.mkdir()
        self.state = self.root / ".embedded"

    def run_cli(self, tool, *options, code=0):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / (tool + ".py")), str(self.root), *options],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, code, msg=f"{tool}\n{result.stderr}\n{result.stdout}")
        return result

    def report(self, tool, *options, code=0):
        return json.loads(self.run_cli(tool, *options, code=code).stdout)

    def put(self, path, text):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return path

    def write_state(self, key, value):
        self.put(f".embedded/{key}.json", json.dumps(value, ensure_ascii=False))

    def read_state(self, key):
        return json.loads((self.state / f"{key}.json").read_text(encoding="utf-8"))

    def prepare_document(self, path="docs/req.md", text="Version: A\n需求内容\n"):
        self.put(path, text)
        self.run_cli("inventory_documents", "--update-registry", "--capture-text")
        return next(row for row in self.read_state("documents")["documents"] if row["path"] == path)

    def make_trace(self, status="Verified"):
        doc = self.prepare_document()
        self.put("src/driver.c", "int driver_read(void) { return 0; }\n")
        self.put("src/driver.h", "int driver_read(void);\n")
        self.put("design/driver.md", "# Design\n")
        self.put("tests/read_test.c", "/* Test fixture */\n")
        self.put("evidence/pass.log", "observed 0, expected 0\n")
        data = {"schema_version": 1, "requirements": [
            {"id": "REQ-1", "title": "返回状态 | 成功", "priority": "P1", "status": status,
             "source": {"document": doc["id"], "locator": "第一节"}, "acceptance": "读取返回 0",
             "links": [{"module": "MOD-DRV", "interface": "IF-READ", "code": ["src/driver.c"], "tests": ["T-READ"]}]}
        ], "modules": [
            {"id": "MOD-DRV", "design": "design/driver.md", "interfaces": [{"id": "IF-READ", "path": "src/driver.h"}],
             "code": ["src/driver.c"], "depends_on": []}
        ], "tests": [
            {"id": "T-READ", "path": "tests/read_test.c", "status": "Passed", "evidence": "evidence/pass.log"}
        ]}
        self.write_state("traceability", data)
        return data
