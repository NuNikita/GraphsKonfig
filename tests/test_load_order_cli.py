"""Demonstrate stage-four output with file and NuGet HTTP repositories."""

import unittest

from test_cli import CliHarness, OUTPUT, SUCCESS_EXIT
from test_graph_cli import HttpGraphHarness


class FileLoadOrderCliTests(CliHarness, unittest.TestCase):
    """Check the explicit mode, filtering and atomic cycle failure via CLI."""

    def run_order(self, content, excluded="", name="A"):
        """Write a UTF-8 repository and request its dependency-first order."""
        (self.workdir / "repository.txt").write_text(content, encoding="utf-8")
        return self.run_cli({
            "--package": name, "--repository": "repository.txt",
            "--filter": excluded,
        }, ["--test-mode", "--load-order"])

    def test_chain_diamond_leaf_and_unreachable_cycle(self):
        """Show valid orders without creating the stage-five output file."""
        cases = [
            ("A: B C\nB: C\nC:\n", "C\nB\nA\n"),
            ("A: B C B\nB: D\nC: D\nD:\nX: X\n", "D\nB\nC\nA\n"),
            ("A:\n", "A\n"),
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
        content = "A: B C\nB: D\nC: D\nD:\n"
        result = self.run_order(content, "B")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "D\nC\nA\n")
        result = self.run_order(content, "A")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, (
            "Порядок загрузки пуст: исходный пакет исключён фильтром.\n"
        ))

    def test_cycles_never_print_a_partial_order(self):
        """Reject a self-loop and a cycle found after finishing a valid leaf."""
        cases = [
            ("A: A\n", "A -> A"),
            ("A: D B\nD:\nB: C\nC: B\n", "B -> C -> B"),
        ]
        output = self.workdir / OUTPUT
        output.write_text("existing image", encoding="utf-8")
        for content, path in cases:
            with self.subTest(content=content):
                self.assert_cli_error(self.run_order(content), path)
                self.assertEqual(output.read_text(), "existing image")

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
