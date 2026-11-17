"""Read versioned package adjacency lists from a local UTF-8 text file."""

import re
from pathlib import Path

from config import TEST_PACKAGE_PATTERN, package_version
from graph import Package
from nuget import Dependency, RepositoryError, normalized_version


def parse_package(value):
    """Parse an uppercase package name and a concrete, normalized version."""
    name, separator, version = value.partition("@")
    if not separator or not re.fullmatch(TEST_PACKAGE_PATTERN, name):
        raise ValueError(f"ожидается имя из букв A-Z и версия: {value!r}")
    return Package(name, normalized_version(package_version(version)))


def parse_line(line, number):
    """Read a versioned declaration and report errors with its line number."""
    source, separator, targets = line.partition(":")
    try:
        if not separator:
            raise ValueError("ожидается строка вида A@1.0.0: B@2.0.0")
        package = parse_package(source.strip())
        dependencies = [parse_package(target) for target in targets.split()]
    except ValueError as error:
        raise RepositoryError(f"строка {number}: {error}") from error
    return package, list(dict.fromkeys(dependencies))


def parse_repository(content):
    """Validate declarations, duplicate vertices and undeclared references."""
    graph = {}
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        package, targets = parse_line(line, number)
        if package in graph:
            message = f"строка {number}: повторное описание {package.label()}"
            raise RepositoryError(message)
        graph[package] = targets
    missing = {target for targets in graph.values() for target in targets}
    missing.difference_update(graph)
    if missing:
        names = ", ".join(sorted(package.label() for package in missing))
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
        """Look up the exact requested package version in the local file."""
        try:
            package = parse_package(f"{name}@{version}")
        except ValueError as error:
            raise RepositoryError(str(error)) from error
        if package not in self.graph:
            label = package.label()
            message = f"пакет {label} не найден в тестовом репозитории"
            raise RepositoryError(message)
        return package

    def dependencies(self, package):
        """Return the declared edges in their original order."""
        return [
            Dependency(target.name, target.version, "")
            for target in self.graph[package]
        ]

    def resolve(self, dependency):
        """Return the exact version named in a validated dependency edge."""
        return Package(dependency.name, dependency.version)
