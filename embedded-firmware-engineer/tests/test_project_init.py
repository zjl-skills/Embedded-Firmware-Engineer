import os
import subprocess

from support import ProjectCase


class ProjectInitTests(ProjectCase):
    def test_new_root_can_be_initialized(self):
        self.root = self.root / "new-board"
        self.state = self.root / ".embedded"
        report = self.report("init_project", "--mode", "A", "--module", "MOD-ADC")
        self.assertEqual(self.read_state("config")["mode"], "A")
        self.assertIn("modules/MOD-ADC/HANDOFF.md", report["created"])
        self.assertEqual(len(report["created"]), 20)

    def test_existing_context_source_and_mode_are_preserved(self):
        source = self.put("main.c", "int main(void) { return 0; }\n")
        existing = self.put(".embedded/PROJECT_CONTEXT.md", "现有文档\n")
        old_text = existing.read_bytes()
        first = self.report("init_project", "--mode", "C")
        self.assertEqual(first["preserved"], ["PROJECT_CONTEXT.md"])
        second = self.report("init_project", "--mode", "A")
        self.assertEqual(second["created"], [])
        self.assertEqual(existing.read_bytes(), old_text)
        self.assertEqual(self.read_state("config")["mode"], "C")
        self.assertTrue(source.is_file())

    def test_custom_management_directory_is_used_by_all_state_checks(self):
        self.report("init_project", "--state-dir", "management/firmware", "--module", "UART")
        self.assertTrue((self.root / "management/firmware/modules/UART/INTERFACE.md").is_file())
        report = self.report("validate_project", "--state-dir", "management/firmware")
        self.assertEqual(report["errors"], 0)
        self.assertFalse(self.state.exists())

    def test_invalid_state_or_module_path_does_not_create_templates(self):
        for options in (("--state-dir", "../outside"), ("--state-dir", ".GIT"), ("--module", "../outside"), ("--module", "NUL")):
            with self.subTest(options=options):
                self.run_cli("init_project", *options, code=2)
                self.assertEqual(list(self.root.iterdir()), [])

    def test_destination_directory_where_file_is_expected_reports_error(self):
        (self.state / "ISSUES.md").mkdir(parents=True)
        self.run_cli("init_project", code=2)
        self.assertEqual(list(self.state.iterdir()), [self.state / "ISSUES.md"])

    def test_redirected_state_is_rejected(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        try:
            self.state.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"当前账户不能创建符号链接: {exc.errno}")
            command = "New-Item -ItemType Junction -Path $env:EFW_TEST_LINK -Target $env:EFW_TEST_DESTINATION -ErrorAction Stop | Out-Null"
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                    env={**os.environ, "EFW_TEST_LINK": str(self.state), "EFW_TEST_DESTINATION": str(outside)},
                                    capture_output=True, timeout=15)
            if result.returncode:
                self.skipTest("当前账户不能创建符号链接或 junction")
        self.run_cli("init_project", code=2)
        self.assertEqual(list(outside.iterdir()), [])
