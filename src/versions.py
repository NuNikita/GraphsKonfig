"""Select concrete NuGet dependency versions without external libraries."""

from dataclasses import dataclass

from config import package_version
from nuget import MAX_VERSION_COMPONENTS, RepositoryError, normalized_version


def version_key(value):
    """Compare four numeric components and case-insensitive prerelease parts."""
    value = normalized_version(package_version(value))
    release, separator, suffix = value.partition("-")
    numbers = [int(part) for part in release.split(".")]
    numbers.extend([0] * (MAX_VERSION_COMPONENTS - len(numbers)))
    labels = tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in suffix.split(".")
    ) if separator else ()
    return tuple(numbers), not separator, labels


@dataclass(frozen=True)
class VersionRange:
    """Keep normalized bounds, inclusivity and prerelease eligibility."""

    lower: str
    upper: str
    include_lower: bool
    include_upper: bool

    def accepts(self, version):
        """Check both bounds and omit unrequested prerelease versions."""
        if "-" in version and "-" not in self.lower + self.upper:
            return False
        key = version_key(version)
        if not self.accepts_lower(key):
            return False
        if not self.accepts_upper(key):
            return False
        return True

    def accepts_lower(self, key):
        """Test the lower boundary with its inclusive or exclusive endpoint."""
        if not self.lower:
            return True
        bound = version_key(self.lower)
        return key > bound or (key == bound and self.include_lower)

    def accepts_upper(self, key):
        """Test the upper boundary with its inclusive or exclusive endpoint."""
        if not self.upper:
            return True
        bound = version_key(self.upper)
        return key < bound or (key == bound and self.include_upper)


def validate_open_bounds(value, lower, upper):
    """Require parentheses for absent lower and upper interval endpoints."""
    if not lower and value[0] != "(":
        raise ValueError("отсутствующая нижняя граница должна быть открытой")
    if not upper and value[-1] != ")":
        raise ValueError("отсутствующая верхняя граница должна быть открытой")


def interval_bounds(value):
    """Split an interval or exact bracketed version, rejecting invalid forms."""
    if value[0] not in "[(" or value[-1] not in "])":
        raise ValueError("неверные границы диапазона")
    body = value[1:-1].strip()
    if "," not in body:
        if value[0] != "[" or value[-1] != "]" or not body:
            raise ValueError("точная версия записывается как [1.0]")
        return body, body
    lower, upper = (part.strip() for part in body.split(","))
    validate_open_bounds(value, lower, upper)
    return lower, upper


def parse_range(value):
    """Parse bare minimum versions, exact versions and NuGet intervals."""
    value = value.strip()
    if not value:
        return VersionRange("", "", False, False)
    if value[0] not in "[(":
        lower = normalized_version(package_version(value))
        return VersionRange(lower, "", True, False)
    lower, upper = interval_bounds(value)
    lower = normalized_version(package_version(lower)) if lower else ""
    upper = normalized_version(package_version(upper)) if upper else ""
    result = VersionRange(lower, upper, value[0] == "[", value[-1] == "]")
    if lower and upper:
        ordered = version_key(lower) < version_key(upper)
        equal = version_key(lower) == version_key(upper)
        if not ordered and not (equal and result.accepts(lower)):
            raise ValueError("диапазон не содержит версий")
    return result


def select_version(versions, constraint):
    """Choose the lowest available matching version for one dependency edge."""
    try:
        allowed = parse_range(constraint)
        candidates = [
            version for version in versions if allowed.accepts(version)
        ]
        if candidates:
            return min(candidates, key=version_key)
    except ValueError as error:
        raise RepositoryError(f"некорректный диапазон {constraint!r}: {error}")
    raise RepositoryError(f"нет версии для ограничения {constraint!r}")
