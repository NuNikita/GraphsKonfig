"""Provide cached NuGet manifests and resolve versions for graph traversal."""

import json
from urllib.parse import urljoin

from config import package_version
from graph import Package
from nuget import (
    RepositoryError, fetch_bytes, normalized_version, package_base_address,
    parse_nuspec,
)
from versions import select_version


def parse_versions(content):
    """Require a JSON object containing valid version strings in versions."""
    try:
        index = json.loads(content)
        versions = index.get("versions") if isinstance(index, dict) else None
        if not isinstance(versions, list):
            raise ValueError("ожидается список versions")
        if any(not isinstance(version, str) for version in versions):
            raise ValueError("версии должны быть строками")
        return [
            normalized_version(package_version(version)) for version in versions
        ]
    except (ValueError, UnicodeError) as error:
        raise RepositoryError(f"некорректный список версий: {error}") from error


class NugetRepository:
    """Reuse one service index and canonicalize case-insensitive vertices."""

    def __init__(self, repository):
        """Defer all HTTP requests until an allowed vertex is visited."""
        self.repository = repository
        self.base_address = None
        self.packages = {}
        self.versions = {}
        self.resolved = {}

    def content_url(self, path):
        """Discover the flat container once and construct its resource URL."""
        if self.base_address is None:
            self.base_address = package_base_address(self.repository)
        return urljoin(self.base_address, path)

    def root(self, name, version):
        """Canonicalize identity while preserving the first name spelling."""
        version = normalized_version(version)
        key = name.lower(), version
        if key not in self.packages:
            self.packages[key] = Package(name, version)
        return self.packages[key]

    def dependencies(self, package):
        """Read one concrete manifest; DFS calls this once for each vertex."""
        name = package.name.lower()
        path = f"{name}/{package.version}/{name}.nuspec"
        return parse_nuspec(fetch_bytes(self.content_url(path)))

    def available_versions(self, name):
        """Cache and validate the flat-container version list for a package."""
        name = name.lower()
        if name not in self.versions:
            content = fetch_bytes(self.content_url(f"{name}/index.json"))
            self.versions[name] = parse_versions(content)
        return self.versions[name]

    def resolve(self, dependency):
        """Choose a version before visiting an allowed dependency's manifest."""
        key = dependency.name.lower(), dependency.version
        if key not in self.resolved:
            try:
                version = select_version(
                    self.available_versions(dependency.name),
                    dependency.version,
                )
            except RepositoryError as error:
                message = f"пакет {dependency.name}: {error}"
                raise RepositoryError(message) from error
            self.resolved[key] = self.root(dependency.name, version)
        return self.resolved[key]
