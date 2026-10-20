"""Check NuGet version precedence and concrete interval selection."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nuget import RepositoryError
from nuget_repository import parse_versions
from versions import select_version, version_key


class VersionTests(unittest.TestCase):
    """Cover bounds, numeric sorting, prereleases and malformed responses."""

    def test_intervals_and_minimum_versions(self):
        """Use the lowest available version that actually meets the range."""
        available = ["3.0.0", "1.10.0", "2.0.0", "1.2.0", "1.0.0"]
        cases = {
            "": "1.0.0", "1.1": "1.2.0", "[1.2]": "1.2.0",
            "[1,2)": "1.0.0", "(1,2)": "1.2.0", "(1,2]": "1.2.0",
            "[2,3]": "2.0.0", "(2,)": "3.0.0", "[2,)": "2.0.0",
            "(,1]": "1.0.0", "(,1.2)": "1.0.0", "[1,1]": "1.0.0",
        }
        for constraint, expected in cases.items():
            with self.subTest(constraint=constraint):
                self.assertEqual(
                    select_version(available, constraint), expected
                )

    def test_numeric_and_prerelease_precedence(self):
        """Compare numeric parts numerically and stable after prerelease."""
        versions = [
            "1.0.0-alpha", "1.0.0-alpha.2", "1.0.0-alpha.10",
            "1.0.0-beta", "1.0.0", "1.0.0.1", "1.2.0", "1.10.0",
        ]
        self.assertEqual(sorted(reversed(versions), key=version_key), versions)
        self.assertEqual(version_key("01.0+build"), version_key("1.0.0.0"))
        self.assertEqual(version_key("1-BETA"), version_key("1-beta"))

    def test_prerelease_requires_explicit_constraint(self):
        """Admit prereleases only if a bound explicitly requests them."""
        versions = ["1.0.0-beta.2", "1.0.0-beta.10", "1.0.0", "2.0.0-beta"]
        self.assertEqual(select_version(versions, ""), "1.0.0")
        self.assertEqual(
            select_version(versions, "[1-beta.3,1)"), "1.0.0-beta.10"
        )
        self.assertEqual(select_version(versions, "[1-beta.2]"), "1.0.0-beta.2")

    def test_invalid_or_unsatisfiable_ranges(self):
        """Reject broken intervals, empty intervals and absent matches."""
        for constraint in (
            "(1)", "[1,2", "[2,1]", "(1,1)", "(1,1]", "[1,1)",
            "[,1]", "[1,]", "[1,2,3]", "latest", "*", "[9]", "[1,2)",
        ):
            with self.subTest(constraint=constraint):
                with self.assertRaises(RepositoryError):
                    select_version(["2.0.0"], constraint)

    def test_empty_version_list(self):
        """Report that the package has no suitable version."""
        with self.assertRaisesRegex(RepositoryError, "нет версии"):
            select_version([], "")

    def test_version_index_validation(self):
        """Validate JSON structure and every version element."""
        for content in (
            b"broken", b"[]", b"{}", b'{"versions": "1"}',
            b'{"versions": [null]}', b'{"versions": [{}]}',
            b'{"versions": ["bad"]}', b"\xff",
        ):
            with self.subTest(content=content):
                with self.assertRaises(RepositoryError):
                    parse_versions(content)
        self.assertEqual(parse_versions(b'{"versions": ["01.2+build"]}'), [
            "1.2.0"
        ])


if __name__ == "__main__":
    unittest.main()
