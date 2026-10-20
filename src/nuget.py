"""Fetch direct NuGet dependencies using only the standard library."""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import urlopen
from xml.etree import ElementTree

from config import check_text, package_name, repository_url

REQUEST_TIMEOUT = 20
NOT_FOUND = 404
VERSION_COMPONENTS = 3
MAX_VERSION_COMPONENTS = 4


class RepositoryError(Exception):
    """Describe a repository or package manifest failure for the CLI."""


@dataclass(frozen=True)
class Dependency:
    """Keep a direct dependency's name, version constraint and framework."""

    name: str
    version: str
    framework: str


def normalized_version(value):
    """Normalize the numeric version and omit build metadata for NuGet URLs."""
    release, separator, suffix = value.split("+", 1)[0].partition("-")
    parts = [str(int(part)) for part in release.split(".")]
    while len(parts) < VERSION_COMPONENTS:
        parts.append("0")
    if len(parts) == MAX_VERSION_COMPONENTS and parts[-1] == "0":
        parts.pop()
    return ".".join(parts) + (separator + suffix.lower() if separator else "")


def fetch_bytes(url):
    """Read an HTTP resource with a timeout and readable network errors."""
    try:
        repository_url(url)
        with urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except HTTPError as error:
        if error.code == NOT_FOUND:
            message = "ресурс, пакет или версия не найдены (HTTP 404)"
        else:
            message = f"ошибка HTTP {error.code}"
        raise RepositoryError(f"{message}: {url}") from error
    except (URLError, OSError, ValueError) as error:
        raise RepositoryError(f"не удалось прочитать {url}: {error}") from error


def package_base_address(repository):
    """Discover PackageBaseAddress/3.0.0 in the supplied V3 service index."""
    try:
        index = json.loads(fetch_bytes(repository))
    except (ValueError, UnicodeError) as error:
        message = "индекс NuGet содержит некорректный JSON"
        raise RepositoryError(message) from error
    resources = index.get("resources") if isinstance(index, dict) else None
    if not isinstance(resources, list):
        raise RepositoryError("в индексе NuGet отсутствует список resources")
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        if resource.get("@type") == "PackageBaseAddress/3.0.0":
            address = resource.get("@id")
            try:
                if not isinstance(address, str):
                    raise ValueError("адрес должен быть строкой")
                return repository_url(address).rstrip("/") + "/"
            except ValueError as error:
                message = "некорректный PackageBaseAddress"
                raise RepositoryError(message) from error
    raise RepositoryError("индекс не содержит PackageBaseAddress/3.0.0")


def read_dependency(element, framework):
    """Validate one dependency while preserving its NuGet version range."""
    try:
        name = package_name(element.get("id", ""))
        version = check_text(element.get("version", "").strip())
        check_text(framework)
    except ValueError as error:
        raise RepositoryError(f"некорректная зависимость: {error}") from error
    return Dependency(name, version, framework)


def parse_nuspec(content):
    """Extract only direct dependencies, including all framework groups."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        message = "манифест .nuspec содержит некорректный XML"
        raise RepositoryError(message) from error
    namespace = root.tag.partition("}")[0] + "}" if "}" in root.tag else ""
    if root.tag != namespace + "package":
        raise RepositoryError("ожидается корневой элемент package в .nuspec")
    metadata = root.find("{*}metadata")
    if metadata is None:
        raise RepositoryError("в .nuspec отсутствует metadata")
    dependencies = metadata.find("{*}dependencies")
    if dependencies is None:
        return []
    result = []
    for element in dependencies:
        if element.tag.rpartition("}")[-1] == "dependency":
            result.append(read_dependency(element, ""))
        elif element.tag.rpartition("}")[-1] == "group":
            framework = element.get("targetFramework", "")
            for dependency in element.findall("{*}dependency"):
                result.append(read_dependency(dependency, framework))
    return result


def get_dependencies(repository, package, version):
    """Fetch one version's manifest without visiting dependency packages."""
    base_address = package_base_address(repository)
    name = package.lower()
    release = normalized_version(version)
    manifest_url = urljoin(base_address, f"{name}/{release}/{name}.nuspec")
    return parse_nuspec(fetch_bytes(manifest_url))


def format_dependency(dependency):
    """Format a dependency with its original constraint and target group."""
    version = dependency.version or "любая версия"
    framework = dependency.framework or "без указания платформы"
    return f"{dependency.name}\t{version}\t{framework}"
