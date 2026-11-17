"""Demonstrate stage-four output with file and NuGet HTTP repositories."""

import unittest

from test_cli import CliHarness, OUTPUT, SUCCESS_EXIT
from test_graph_cli import HttpGraphHarness


class FileLoadOrderCliTests(CliHarness, unittest.TestCase):
    """Check the explicit mode, filtering and atomic cycle failure via CLI."""

    def run_order(self, content, excluded="", name="A", version="1"):
        """Write a UTF-8 repository and request its dependency-first order."""
        (self.workdir / "repository.txt").write_text(content, encoding="utf-8")
        return self.run_cli({
            "--package": name, "--repository": "repository.txt",
            "--filter": excluded, "--version": version,
        }, ["--test-mode", "--load-order"])

    def test_chain_diamond_leaf_and_unreachable_cycle(self):
        """Show valid orders without creating an SVG in load-order mode."""
        cases = [
            ("A@1: B@1 C@1\nB@1: C@1\nC@1:\n",
             "C@1.0.0\nB@1.0.0\nA@1.0.0\n"),
            ("A@1: B@1 C@1 B@1\nB@1: D@2\nC@1: D@2\nD@2:\nX@1: X@1\n",
             "D@2.0.0\nB@1.0.0\nC@1.0.0\nA@1.0.0\n"),
            ("A@1:\n", "A@1.0.0\n"),
        ]
        for content, expected in cases:
            with self.subTest(content=content):
                result = self.run_order(content)
                self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")
                self.assertFalse((self.workdir / OUTPUT).exists())

    def test_filter_and_excluded_root(self):
        """Retain reachable shared leaves and explain an excluded root."""
        content = "A@1: B@2 C@1\nB@2: D@3\nC@1: D@3\nD@3:\n"
        result = self.run_order(content, "B")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "D@3.0.0\nC@1.0.0\nA@1.0.0\n")
        result = self.run_order(content, "A")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, (
            "Порядок загрузки пуст: исходный пакет исключён фильтром.\n"
        ))

    def test_cycles_never_print_a_partial_order(self):
        """Reject a self-loop and a cycle found after finishing a valid leaf."""
        cases = [
            ("A@1: A@1\n", "A@1.0.0 -> A@1.0.0"),
            ("A@1: D@1 B@2\nD@1:\nB@2: C@3\nC@3: B@2\n",
             "B@2.0.0 -> C@3.0.0 -> B@2.0.0"),
        ]
        output = self.workdir / OUTPUT
        output.write_text("existing image", encoding="utf-8")
        for content, path in cases:
            with self.subTest(content=content):
                self.assert_cli_error(self.run_order(content), path)
                self.assertEqual(output.read_text(), "existing image")

    def test_selects_root_version_and_rejects_missing_version(self):
        """Use the requested version's edges when computing the order."""
        content = "A@1: B@1\nA@2: C@2\nB@1:\nC@2:\n"
        first = self.run_order(content, version="1.0.0")
        second = self.run_order(content, version="2")
        self.assertEqual(first.returncode, SUCCESS_EXIT, first.stderr)
        self.assertEqual(second.returncode, SUCCESS_EXIT, second.stderr)
        self.assertEqual(first.stdout, "B@1.0.0\nA@1.0.0\n")
        self.assertEqual(second.stdout, "C@2.0.0\nA@2.0.0\n")
        self.assert_cli_error(
            self.run_order(content, version="3"), "пакет A@3.0.0 не найден"
        )

    def test_distinguishes_versions_of_one_dependency(self):
        """An edge between two versions of one package is not a cycle."""
        content = "A@1: B@1 B@2\nB@1: B@2\nB@2:\n"
        result = self.run_order(content)
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "B@2.0.0\nB@1.0.0\nA@1.0.0\n")

    def test_load_order_flag_rejects_boolean_values(self):
        """Handle explicit values as normal argument errors."""
        for value in ("true", "false"):
            with self.subTest(value=value):
                result = self.run_cli(extra=[f"--load-order={value}"])
                self.assert_cli_error(result, "--load-order")


class HttpLoadOrderCliTests(HttpGraphHarness, unittest.TestCase):
    """Use real NuGet data formats without invoking a package manager."""

    def test_transitive_order_with_concrete_versions(self):
        """Order a NuGet diamond and fetch each shared manifest once."""
        root = self.add_package("A", dependencies=[("B", "[1]"), ("C", "[1]")])
        branch = self.add_package("B", dependencies=[("D", "[1]")])
        leaf = self.add_package("D")
        sibling = self.add_package("C", dependencies=[("D", "[1]")])
        for name in ("B", "C", "D"):
            self.add_versions(name, ["1.0.0"])
        result = self.run_cli(extra=["--load-order"])
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, (
            "D@1.0.0\nB@1.0.0\nC@1.0.0\nA@1.0.0\n"
        ))
        self.assertEqual(self.repository.requests, [
            "/v3/index.json", root, "/content/b/index.json", branch,
            "/content/d/index.json", leaf, "/content/c/index.json", sibling,
        ])

    def test_nuget_cycle_contains_versions(self):
        """Explain that a NuGet cycle prevents dependency-first loading."""
        self.add_package("A", dependencies=[("B", "[1]")])
        self.add_package("B", dependencies=[("A", "[1]")])
        for name in ("A", "B"):
            self.add_versions(name, ["1.0.0"])
        self.assert_cli_error(self.run_cli(extra=["--load-order"]),
                              "A@1.0.0 -> B@1.0.0 -> A@1.0.0")

    def test_filter_prevents_requests_in_order_mode(self):
        """Exclude dependencies and roots before fetching their metadata."""
        root = self.add_package("A", dependencies=[("Skip.B", "bad")])
        result = self.run_cli({"--filter": "Skip."}, ["--load-order"])
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "A@1.0.0\n")
        self.assertEqual(self.repository.requests, ["/v3/index.json", root])
        self.repository.requests.clear()
        result = self.run_cli({"--filter": "A"}, ["--load-order"])
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertIn("Порядок загрузки пуст", result.stdout)
        self.assertEqual(self.repository.requests, [])

    def test_transitive_failure_has_no_partial_order(self):
        """Report missing descendant manifests before printing any packages."""
        self.add_package("A", dependencies=[("B", "[1]")])
        self.add_versions("B", ["1.0.0"])
        self.assert_cli_error(self.run_cli(extra=["--load-order"]), "404")


if __name__ == "__main__":
    unittest.main()
