"""Exercise successful configuration and errors through the real CLI."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "src" / "main.py"
ERROR_EXIT = 2
SUCCESS_EXIT = 0
OUTPUT = "graph.svg"


class CliTests(unittest.TestCase):
    """Check observable behavior without contacting real repositories."""

    def setUp(self):
        """Create an isolated working directory and a test repository."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workdir = Path(directory.name)
        (self.workdir / "repository.txt").write_text("A: B\nB:\n")
        self.options = {
            "--package": "Newtonsoft.Json",
            "--repository": "https://api.nuget.org/v3/index.json",
            "--version": "13.0.3",
            "--output": OUTPUT,
            "--filter": "",
        }

    def run_cli(self, changes=None, extra=()):
        """Run the application with controlled arguments and working dir."""
        options = self.options | (changes or {})
        arguments = []
        for name, value in options.items():
            if value is not None:
                arguments.extend([name, value])
        return subprocess.run(
            [sys.executable, str(CLI), *arguments, *extra],
            cwd=self.workdir,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_cli_error(self, result, option):
        """Require a useful CLI error without traceback or partial output."""
        self.assertEqual(result.returncode, ERROR_EXIT, result.stderr)
        self.assertIn(option, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_prints_all_six_parameters(self):
        """Print all values, including defaults, without creating an image."""
        result = self.run_cli({"--filter": None})
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), [
            "package=Newtonsoft.Json",
            "repository=https://api.nuget.org/v3/index.json",
            "test_mode=False",
            "version=13.0.3",
            "output=graph.svg",
            "filter=",
        ])
        self.assertFalse((self.workdir / OUTPUT).exists())

    def test_accepts_test_mode(self):
        """Accept a readable local repository and an uppercase package."""
        result = self.run_cli(
            {"--package": "A", "--repository": "repository.txt"},
            ["--test-mode"],
        )
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertIn("test_mode=True\n", result.stdout)

    def test_required_parameters(self):
        """Report every missing mandatory parameter."""
        for option in ("--package", "--repository", "--version", "--output"):
            with self.subTest(option=option):
                self.assert_cli_error(self.run_cli({option: None}), option)

    def test_invalid_packages(self):
        """Reject empty names, whitespace, punctuation and control input."""
        for value in ("", " ", "bad name", "a/b", ".", "имя", "A\nB"):
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.run_cli({"--package": value}), "--package"
                )

    def test_invalid_versions(self):
        """Reject missing numeric versions and malformed version suffixes."""
        for value in ("", "latest", "1..2", "1.2.3.4.5", "1-", "1 a"):
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.run_cli({"--version": value}), "--version"
                )

    def test_valid_versions_and_filter(self):
        """Accept version forms and return the selected filtering substring."""
        for value in ("1", "1.2", "1.2.3", "1.2.3.4", "1.0-beta.1+build"):
            with self.subTest(value=value):
                result = self.run_cli({
                    "--version": value, "--filter": "Microsoft."
                })
                self.assertEqual(
                    result.returncode, SUCCESS_EXIT, result.stderr
                )
                self.assertIn("filter=Microsoft.\n", result.stdout)

    def test_invalid_repository_urls(self):
        """Reject local paths, unsafe URL forms and malformed ports."""
        values = (
            "", "repository.txt", "ftp://host/path", "https://",
            "https://a b", "https://host:bad", "https://host:70000",
            "https://host:0", "https://host/#fragment",
            "https://user:password@host", "https://[bad",
        )
        for value in values:
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.run_cli({"--repository": value}), "--repository"
                )

    def test_invalid_test_repositories(self):
        """Reject absent files, empty paths, directories and remote URLs."""
        for value in ("missing.txt", "", ".", "https://example.com"):
            with self.subTest(value=value):
                result = self.run_cli(
                    {"--package": "A", "--repository": value},
                    ["--test-mode"],
                )
                self.assert_cli_error(result, "--repository")

    def test_invalid_test_mode_package(self):
        """Require uppercase Latin package names for test repositories."""
        result = self.run_cli(
            {"--repository": "repository.txt"}, ["--test-mode"]
        )
        self.assert_cli_error(result, "--package")

    def test_invalid_boolean_values(self):
        """Reject an explicit boolean value attached to a flag."""
        for value in ("false", "true", "maybe"):
            with self.subTest(value=value):
                result = self.run_cli(extra=[f"--test-mode={value}"])
                self.assert_cli_error(result, "--test-mode")

    def test_invalid_outputs(self):
        """Reject wrong extensions, directories and nonexistent parents."""
        (self.workdir / "directory.svg").mkdir()
        for value in ("", "graph.png", "absent/g.svg", "directory.svg"):
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.run_cli({"--output": value}), "--output"
                )

    def test_existing_output_is_preserved(self):
        """Check the configuration stage never overwrites an existing file."""
        output = self.workdir / OUTPUT
        output.write_text("existing content", encoding="utf-8")
        result = self.run_cli()
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing content")

    def test_invalid_filters(self):
        """Reject blank filters and control characters in filters."""
        for value in (" ", "\n", "A\tB", "A\x7fB", "A\u2028B"):
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.run_cli({"--filter": value}), "--filter"
                )

    def test_unknown_option(self):
        """Report unsupported arguments instead of ignoring them."""
        result = self.run_cli(extra=["--unknown"])
        self.assert_cli_error(result, "--unknown")

    def test_help(self):
        """Document every configuration option in the built-in help."""
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, SUCCESS_EXIT)
        for option in (*self.options, "--test-mode"):
            self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
