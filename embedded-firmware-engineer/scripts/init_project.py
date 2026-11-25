"""为新建或已有嵌入式工程填补缺失的管理模板。"""

from pathlib import PurePosixPath

from project_data import (
    MODULE_FILES, STATE_FILES, TEMPLATES, cli_main, get_project, json_text, module_name,
    parser, read_json, require, state_file, write_new,
)


def initialize(project, mode, modules):
    files = [(source, PurePosixPath(source).name) for source in STATE_FILES]
    for module in dict.fromkeys(map(module_name, modules)):
        for source in MODULE_FILES:
            files.append((source, f"modules/{module}/{PurePosixPath(source).name}"))

    # 在写入前检查所有目标和模板，避免路径错误造成部分初始化。
    targets = [(source, destination, state_file(project, destination)) for source, destination in files]
    for source, _, path in targets:
        require((TEMPLATES / source).is_file(), f"缺少模板: {source}")
        require(not path.exists() or path.is_file(), f"目标存在但不是常规文件: {path}")
        for parent in path.parents:
            if parent == project[0]:
                break
            require(not parent.exists() or parent.is_dir(), f"目标父路径不是目录: {parent}")

    created, preserved = [], []
    for source, destination, path in targets:
        template = TEMPLATES / source
        if destination == "config.json":
            config = read_json(template)
            config["mode"] = mode
            content = json_text(config).encode("utf-8")
        else:
            content = template.read_bytes()
        try:
            write_new(path, content)
        except FileExistsError:
            preserved.append(destination)
        else:
            created.append(destination)
    return {"project": str(project[0]), "state_directory": str(project[1]),
            "created": created, "preserved": preserved}


def main(args):
    for module in args.module:
        module_name(module)
    project = get_project(args, create=True)
    print(json_text(initialize(project, args.mode, args.module)), end="")
    return 0


if __name__ == "__main__":
    cli = parser(__doc__, output=False)
    cli.add_argument("--mode", choices=("A", "B", "C"), default="B", help="新配置的工作模式，默认 B")
    cli.add_argument("--module", action="append", default=[], help="增建模块管理文件，可重复指定")
    raise SystemExit(cli_main(cli, main))
