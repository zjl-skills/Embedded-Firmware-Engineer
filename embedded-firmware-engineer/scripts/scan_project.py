"""扫描工程结构、工具链、MCU 和 RTOS 线索。"""

from collections import Counter
import codecs
import re
import shutil

from project_data import CODE_SUFFIXES, cli_main, emit, get_project, load_config, parser, walk_files


BUILD_NAMES = {
    "makefile": "Make", "gnumakefile": "Make", "cmakelists.txt": "CMake", "cmakepresets.json": "CMake",
    "cmakeuserpresets.json": "CMake", "build.ninja": "Ninja", "compile_commands.json": "Compilation Database",
    "platformio.ini": "PlatformIO", ".project": "Eclipse", ".cproject": "Eclipse", "west.yml": "west",
    "meson.build": "Meson", "sconstruct": "SCons", "kconfig": "Kconfig", "sdkconfig": "ESP-IDF",
    "sdkconfig.defaults": "ESP-IDF",
}
BUILD_SUFFIXES = {
    ".uvproj": "Keil MDK", ".uvprojx": "Keil MDK", ".uvoptx": "Keil MDK", ".ewp": "IAR EWARM",
    ".eww": "IAR EWARM", ".ewd": "IAR EWARM", ".ioc": "STM32CubeMX", ".mex": "NXP Config Tools",
    ".mk": "Make", ".cmake": "CMake", ".ninja": "Ninja", ".sh": "Shell", ".bat": "Batch",
    ".cmd": "Batch", ".ps1": "PowerShell",
}
MCU_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:STM32[A-Z]\d{3,4}[A-Z0-9]*|(?:GD32|CH32|MM32|HC32)[A-Z0-9]*\d{3}[A-Z0-9]*"
    r"|(?:MIMXRT|LPC|MCX|R7F|RA[2468])[A-Z0-9]*\d[A-Z0-9]*|ESP32(?:-[A-Z0-9-]+)?)(?![a-z0-9])", re.I
)
RTOS_PATTERNS = {
    "FreeRTOS": re.compile(r"\b(freertos(?:config)?\.h|freertos|xTaskCreate|vTaskStartScheduler)\b", re.I),
    "RT-Thread": re.compile(r"\b(rtthread\.h|rt-thread|rt_thread_(?:create|init|startup))\b", re.I),
    "Zephyr": re.compile(r"\b(zephyr/(?:kernel|device)\.h|find_package\s*\(\s*Zephyr)\b", re.I),
    "ThreadX": re.compile(r"\b(tx_api\.h|tx_kernel_enter|threadx)\b", re.I),
    "CMSIS-RTOS API": re.compile(r"\b(cmsis_os2?\.h|osKernelStart)\b"),
}
TOOL_PATTERNS = {
    "arm-none-eabi-gcc": re.compile(r"\barm-none-eabi-(?:gcc|g\+\+)|\barm-none-eabi-", re.I),
    "ARMClang": re.compile(r"\barmclang\b|<uAC6>\s*1\s*</uAC6>", re.I),
    "ARMCC": re.compile(r"\barmcc\b|<uAC6>\s*0\s*</uAC6>", re.I),
    "IAR ICCARM": re.compile(r"\biccarm\b|\bIarBuild\b", re.I),
    "GCC": re.compile(r"(?<![-\w])(?:gcc|g\+\+)(?![\w-])", re.I),
    "STM32CubeIDE": re.compile(r"\bstm32cube\.ide\b|\bSTM32CubeIDE\b", re.I),
    "MCUXpresso": re.compile(r"\b(?:com\.nxp\.mcuxpresso|MCUXpresso)\b", re.I),
    "ESP-IDF": re.compile(r"\bIDF_PATH\b|\bidf_component_register\b", re.I),
}
SDK_PATTERNS = {
    "STM32 HAL": re.compile(r"\bstm32\w+_hal(?:_\w+)?\.h\b|\bHAL_Init\s*\(", re.I),
    "STM32 LL": re.compile(r"\bstm32\w+_ll(?:_\w+)?\.h\b", re.I),
    "GD32 firmware library": re.compile(r"\bgd32\w+(?:_libopt|_gpio|_rcu)\.h\b", re.I),
    "CMSIS": re.compile(r"\bcore_cm\d+\.h\b|\bCMSIS\b"),
}
CONTENT_LIMIT = 256 * 1024


def classify(path):
    name, suffix = path.name.lower(), path.suffix.lower()
    build = BUILD_NAMES.get(name) or BUILD_SUFFIXES.get(suffix)
    if build:
        return "build", build
    if name.startswith(("startup", "reset_handler")) and suffix in CODE_SUFFIXES | {".s", ".asm"}:
        return "startup", None
    if suffix in {".ld", ".lds", ".icf", ".sct", ".ldscript", ".xcl"}:
        return "linker", None
    if suffix in {".s", ".asm"} or suffix in CODE_SUFFIXES and not suffix.startswith((".h", ".i")):
        return "source", None
    if suffix in CODE_SUFFIXES:
        return "header", None
    if suffix in {".json", ".yml", ".yaml", ".ini", ".xml", ".cfg", ".conf", ".toml"}:
        return "configuration", None
    if suffix in {".a", ".lib"}:
        return "library", None
    return "other", None


def scan(project, config):
    root, state = project
    files, evidence, skipped = [], [], []
    for path in walk_files(project, config):
        relative = path.relative_to(root).as_posix()
        kind, build = classify(path)
        files.append({"path": relative, "role": kind})
        seen = set()

        def add(category, value, confidence, line=None, matched=None):
            key = category, value
            if key not in seen:
                seen.add(key)
                evidence.append({"category": category, "candidate": value, "confidence": confidence,
                                 "path": relative, "line": line, "matched": matched})

        if build:
            add("build_system", build, "medium", matched=path.name)
        if kind == "other" or kind == "library":
            continue
        with path.open("rb") as handle:
            raw = handle.read(CONTENT_LIMIT + 1)
        truncated = len(raw) > CONTENT_LIMIT
        if truncated:
            skipped.append({"path": relative, "reason": "content_size_limit"})
        sample = raw[:CONTENT_LIMIT]
        encoding = "utf-16" if sample.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            body = codecs.getincrementaldecoder(encoding)().decode(sample, final=not truncated)
        except UnicodeDecodeError:
            skipped.append({"path": relative, "reason": "unsupported_text_encoding"})
            body = ""
        if "\x00" in body:
            skipped.append({"path": relative, "reason": "binary_content"})
            body = ""
        for number, line in enumerate(body.splitlines(), 1):
            for match in MCU_PATTERN.finditer(line):
                strong = kind == "build" and bool(re.search(r"<Device>|\b(?:MCU|CONFIG_IDF_TARGET)\s*[:?+]?=", line, re.I))
                add("mcu", match[0].upper(), "high" if strong else "medium", number, match[0])
            for category, patterns in (("rtos", RTOS_PATTERNS), ("toolchain", TOOL_PATTERNS), ("sdk", SDK_PATTERNS)):
                for candidate, pattern in patterns.items():
                    match = pattern.search(line)
                    if match:
                        add(category, candidate, "medium", number, match[0])
        for match in MCU_PATTERN.finditer(path.name):
            add("mcu", match[0].upper(), "low", matched=match[0])
        for candidate, pattern in RTOS_PATTERNS.items():
            match = pattern.search(relative)
            if match:
                add("rtos", candidate, "low", matched=match[0])

    tools = ("cc", "gcc", "arm-none-eabi-gcc", "armclang", "armcc", "UV4", "IarBuild", "cmake", "make", "ninja",
             "STM32CubeIDE", "mcuxpressoide", "west", "idf.py")
    return {"project": str(root), "has_git_marker": (root / ".git").exists(), "has_management_config":
            (state / "config.json").is_file(), "file_counts": dict(Counter(row["role"] for row in files)),
            "files": files, "evidence": evidence, "commands_found_on_path": {name: shutil.which(name) for name in tools},
            "content_skipped_or_limited": skipped,
            "limitations": ["候选来自文件类型、配置或文本。需核对活动目标、预处理和实际构建。", "工具 PATH 命中未执行。"]}


def main(args):
    project = get_project(args)
    emit(args, project, scan(project, load_config(project, optional=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main(parser(__doc__), main))
