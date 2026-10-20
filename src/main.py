"""Print direct dependencies of a requested NuGet package version."""

import sys

from config import parse_config
from nuget import RepositoryError, format_dependency, get_dependencies

ERROR_EXIT = 2
SUCCESS_EXIT = 0


def main(argv=None):
    """Validate configuration, fetch dependencies and report CLI errors."""
    config = parse_config(argv)
    if config.test_mode:
        message = "Ошибка: тестовый репозиторий относится к этапу 3."
        print(message, file=sys.stderr)
        return ERROR_EXIT
    try:
        dependencies = get_dependencies(
            config.repository, config.package, config.version
        )
    except RepositoryError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return ERROR_EXIT
    if not dependencies:
        print("Прямых зависимостей нет.")
    for dependency in dependencies:
        print(format_dependency(dependency))
    return SUCCESS_EXIT


if __name__ == "__main__":
    sys.exit(main())
