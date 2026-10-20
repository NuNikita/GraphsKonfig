"""Read uppercase package adjacency lists from a local UTF-8 text file."""

import re
from pathlib import Path

from config import TEST_PACKAGE_PATTERN
from graph import Package
from nuget import Dependency, RepositoryError


def parse_line(line, number):
    """Read one 'A: B C' declaration and report its source line on errors."""
    name, separator, targets = line.partition(":")
    name = name.strip()
    dependencies = targets.split()
    names = [name, *dependencies]
    valid = all(re.fullmatch(TEST_PACKAGE_PATTERN, item) for item in names)
    if not separator or not valid:
        raise RepositoryError(
            f"строка {number}: ожидается 'A: B C', имена из букв A-Z"
        )
    return name, list(dict.fromkeys(dependencies))


def parse_repository(content):
    """Validate declarations, duplicate vertices and undeclared references."""
    graph = {}
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        name, targets = parse_line(line, number)
        if name in graph:
            raise RepositoryError(f"строка {number}: повторное описание {name}")
        graph[name] = targets
    missing = {target for targets in graph.values() for target in targets}
    missing.difference_update(graph)
    if missing:
        names = ", ".join(sorted(missing))
        raise RepositoryError(f"не описаны пакеты: {names}")
    return graph


class TestRepository:
    """Adapt a validated test graph to the same interface as NuGet data."""

    def __init__(self, path):
        """Read the whole file, translating I/O and encoding failures."""
        try:
            content = Path(path).expanduser().read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise RepositoryError(f"не удалось прочитать {path}: {error}")
        self.graph = parse_repository(content)

    def root(self, name, version):
        """Require an existing root; test vertices do not have versions."""
        if name not in self.graph:
            message = f"пакет {name} не найден в тестовом репозитории"
            raise RepositoryError(message)
        return Package(name)

    def dependencies(self, package):
        """Return the declared edges in their original order."""
        return [Dependency(name, "", "") for name in self.graph[package.name]]

    def resolve(self, dependency):
        """Map an unversioned test edge to its uppercase vertex."""
        return Package(dependency.name)
