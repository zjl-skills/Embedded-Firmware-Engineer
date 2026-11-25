from support import ProjectCase


class ProjectScanTests(ProjectCase):
    def test_keil_mcu_sdk_and_rtos_receive_locatable_evidence(self):
        self.put("board.uvprojx", "<Project>\n<Device>STM32F407VGT6</Device>\n<uAC6>1</uAC6>\n</Project>")
        self.put("src/startup_stm32f407xx.s", "/* start */\n")
        self.put("src/main.c", '#include "FreeRTOS.h"\n#include "stm32f4xx_hal.h"\n')
        self.put("src/main.h", "/* Header */\n")
        self.put("board.ld", "/* Linker */\n")
        project = self.report("scan_project")
        evidence = {(row["candidate"], row["path"]): row for row in project["evidence"]}
        self.assertEqual(evidence["STM32F407VGT6", "board.uvprojx"]["confidence"], "high")
        self.assertEqual(evidence["STM32F407VGT6", "board.uvprojx"]["line"], 2)
        self.assertEqual(evidence["STM32F407XX", "src/startup_stm32f407xx.s"]["confidence"], "low")
        self.assertIn(("FreeRTOS", "src/main.c"), evidence)
        self.assertIn(("STM32 HAL", "src/main.c"), evidence)
        self.assertIn(("ARMClang", "board.uvprojx"), evidence)
        for role in ("source", "header", "startup", "linker"):
            self.assertEqual(project["file_counts"][role], 1)

    def test_scan_detects_build_configuration_and_ignores_excluded_content(self):
        self.run_cli("init_project")
        config = self.read_state("config")
        config["exclude_dirs"].append("external")
        self.write_state("config", config)
        self.put("CMakeLists.txt", "set(CMAKE_C_COMPILER arm-none-eabi-gcc)\n")
        self.put("iar.ewp", "<option>iccarm</option>".encode("utf-16"))
        self.put("application/main.cpp", '#include <rtthread.h>\n')
        self.put("build/bad.c", "STM32F407VGT6")
        self.put("external/test.c", "ESP32-S3")
        result = self.report("scan_project")
        paths = {row["path"] for row in result["files"]}
        self.assertEqual(paths, {"CMakeLists.txt", "iar.ewp", "application/main.cpp"})
        self.assertEqual({row["candidate"] for row in result["evidence"]},
                         {"CMake", "arm-none-eabi-gcc", "IAR EWARM", "IAR ICCARM", "RT-Thread"})

    def test_limit_and_unsupported_encoding_are_reported(self):
        self.put("big.h", b" " * (256 * 1024 + 1))
        self.put("encoded.c", b"\xc0\xff")
        report = self.report("scan_project")
        self.assertEqual({row["reason"] for row in report["content_skipped_or_limited"]},
                         {"content_size_limit", "unsupported_text_encoding"})

    def test_reports_never_overwrite_a_file(self):
        existing = self.put("output.json", "original")
        self.run_cli("scan_project", "--output", "output.json", code=2)
        self.assertEqual(existing.read_bytes(), b"original")
        self.run_cli("scan_project", "--output", "../outside.json", code=2)
        self.assertFalse((self.root.parent / "outside.json").exists())
