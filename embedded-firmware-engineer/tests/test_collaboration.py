import hashlib
import subprocess

from support import ProjectCase


class CollaborationTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.run_cli("init_project", "--module", "MOD-UART")
        header = self.put("include/link.h", "int link(void);\n")
        self.plan = {"schema_version": 1, "interfaces": [{"id": "IF-LINK", "path": "include/link.h", "version": "1",
                     "approved_by": "Coordinator", "sha256": hashlib.sha256(header.read_bytes()).hexdigest()}], "tasks": [
            {"id": "A", "module": "MOD-UART", "role": "Driver Developer", "interfaces": ["IF-LINK"], "writes": ["src/driver/**"]},
            {"id": "B", "module": "MOD-APP", "role": "Firmware Developer", "interfaces": ["IF-LINK"], "writes": ["src/app.c"]}
        ]}

    def inspect(self, *, code=0):
        self.write_state("collaboration", self.plan)
        return self.report("check_collaboration", code=code)

    def test_claims_conflict_until_ownership_has_explicit_order(self):
        self.assertEqual(self.inspect()["findings"], [])
        self.plan["tasks"][1]["writes"] = ["src/driver/device.c"]
        self.assertEqual(self.inspect(code=1)["findings"][0]["kind"], "overlapping_ownership")
        self.plan["tasks"][1]["depends_on"] = ["A"]
        self.assertEqual(self.inspect()["findings"], [])
        self.plan["tasks"][0]["depends_on"] = ["B"]
        self.assertEqual(self.inspect(code=1)["findings"][0]["kind"], "task_dependency_cycle")

    def test_locked_interface_is_checked_against_all_claims_and_file_content(self):
        self.plan["tasks"][1]["writes"] = ["include/**"]
        self.put("include/link.h", "int drift(int v);\n")
        result = self.inspect(code=1)
        self.assertEqual({row["kind"] for row in result["findings"]}, {"locked_interface_drift", "locked_interface_ownership"})

    def test_git_resume_and_actual_outside_write(self):
        self.inspect()
        self.put("src/driver/impl.c", "int old(void) { return 0; }\n")

        def git(*args):
            command = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "core.hooksPath=.git/no-hooks", *args]
            return subprocess.check_output(command, cwd=self.root, encoding="utf-8", stderr=subprocess.PIPE).strip()

        git("init", "-q", "-b", "fixture")
        git("add", "--", ".")
        git("commit", "-q", "--no-gpg-sign", "-m", "fixture")
        sha = git("rev-parse", "HEAD")
        self.put("src/driver/impl.c", "int old(void) { return 1; }\n")
        result = self.report("check_collaboration", "--task", "A", "--base", sha, "--resume")
        self.assertEqual(result["git"]["changes"], ["src/driver/impl.c"])
        self.assertEqual(result["git"]["branch"], "fixture")
        self.assertEqual(len(result["records"]), 4)
        self.put("src/app.c", "int unexpected(void) { return 0; }\n")
        result = self.report("check_collaboration", "--task", "A", "--base", sha, code=1)
        self.assertIn({"kind": "outside_ownership", "paths": ["src/app.c"]}, result["findings"])
