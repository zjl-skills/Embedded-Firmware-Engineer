import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

from support import ProjectCase, SCRIPTS

sys.path.insert(0, str(SCRIPTS))
from project_data import DataError, load_config, safe_path, walk_files


class PathProtectionTests(ProjectCase):
    def test_forged_windows_path_forms_are_rejected_without_writes(self):
        forms = ["../escape.json", "sub/../../escape.json", "C:/escape.json", "//server/share/item", "local/name:stream"]
        if os.name == "nt":
            forms.extend(["NUL.json", "visible./escape.json", "visible /escape.json"])
        for name in forms:
            with self.subTest(name=name):
                self.run_cli("scan_project", "--output", name, code=2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_redirected_resolution_is_rejected_without_link_privilege(self):
        candidate = self.root / "alias" / "out.json"
        escaped = self.root.parent / "external" / "out.json"
        native = Path.resolve

        def resolve(path, *args, **kwargs):
            return escaped if path == candidate else native(path, *args, **kwargs)

        with patch.object(type(candidate), "resolve", resolve), self.assertRaisesRegex(DataError, "超出项目范围"):
            safe_path(self.root, "alias/out.json")
        self.assertFalse(escaped.exists())

    def test_tree_scan_skips_windows_reparse_attribute_without_link_privilege(self):
        self.put("redirected/canary.md", "should not be read")
        actual = self.put("direct.md", "regular file")
        redirected = self.root / "redirected"
        project = self.root, self.state
        config = load_config(project, optional=True)
        native = Path.lstat

        def lstat(path):
            if path == redirected:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return native(path)

        with patch.object(type(redirected), "lstat", lstat):
            self.assertEqual(list(walk_files(project, config)), [actual])
