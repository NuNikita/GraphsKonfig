"""Exercise graph construction through the CLI with file and HTTP sources."""

import json
import unittest

from test_cli import CliHarness, OUTPUT, SUCCESS_EXIT


class FileGraphCliTests(CliHarness, unittest.TestCase):
    """Demonstrate test-file branches, cycles, exclusion and useful errors."""

    def run_graph(self, content, excluded="", name="A"):
        """Write one repository fixture and run it through the actual CLI."""
        (self.workdir / "repository.txt").write_text(content, encoding="utf-8")
        return self.run_cli({
            "--package": name, "--repository": "repository.txt",
            "--filter": excluded,
        }, ["--test-mode"])

    def test_diamond_cycle_self_loop_and_leaf(self):
        """Show full graph edges rather than just a spanning tree."""
        cases = [
            ("A: B C\nB: D\nC: D\nD:\nX:\n",
             "A: B C\nB: D\nD:\nC: D\n"),
            ("A: B\nB: C\nC: A\n", "A: B\nB: C\nC: A\n"),
            ("A: A\n", "A: A\n"),
            ("A:\n", "A:\n"),
        ]
        for content, expected in cases:
            with self.subTest(content=content):
                result = self.run_graph(content)
                self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertFalse((self.workdir / OUTPUT).exists())

    def test_filter_prunes_transitive_branch(self):
        """Remove B and D, whose only reachable path passes through B."""
        result = self.run_graph("A: B C\nB: D\nC:\nD:\n", "B")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "A: C\nC:\n")

    def test_excluded_root(self):
        """Print an explicit empty-graph result for an excluded root."""
        result = self.run_graph("A: B\nB:\n", "A")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(
            result.stdout, "Граф пуст: исходный пакет исключён фильтром.\n"
        )

    def test_file_format_errors(self):
        """Reject invalid text, empty repositories and missing roots."""
        cases = [
            ("", "не найден"), ("B:\n", "не найден"),
            ("A: B\n", "не описаны"), ("A:\nA:\n", "повторное"),
            ("A: bad\n", "строка 1"), ("A B\n", "строка 1"),
        ]
        for content, message in cases:
            with self.subTest(content=content):
                self.assert_cli_error(self.run_graph(content), message)

    def test_invalid_utf8(self):
        """Report invalid encoding without a traceback or partial graph."""
        (self.workdir / "repository.txt").write_bytes(b"\xff")
        result = self.run_cli(
            {"--package": "A", "--repository": "repository.txt"},
            ["--test-mode"],
        )
        self.assert_cli_error(result, "не удалось прочитать")

    def test_utf8_bom(self):
        """Accept text files saved by editors with a UTF-8 byte-order mark."""
        result = self.run_graph("\ufeffA:\n")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "A:\n")


class HttpGraphHarness(CliHarness):
    """Share real-format NuGet fixtures for graph and loading-order tests."""

    def setUp(self):
        """Reset the HTTP fixture and request a small root package."""
        super().setUp()
        self.repository.routes.clear()
        self.repository.requests.clear()
        self.repository.set_index()
        self.options.update({"--package": "A", "--version": "1"})

    def add_package(self, name, version="1.0.0", dependencies=()):
        """Serve a .nuspec with explicit direct dependency constraints."""
        elements = "".join(
            f'<dependency id="{target}" version="{constraint}"/>'
            for target, constraint in dependencies
        )
        body = (
            f"<package><metadata><dependencies>{elements}"
            "</dependencies></metadata></package>"
        )
        name = name.lower()
        path = f"/content/{name}/{version}/{name}.nuspec"
        self.repository.routes[path] = (200, body.encode())
        return path

    def add_versions(self, name, versions):
        """Expose available versions in intentionally unsorted order."""
        path = f"/content/{name.lower()}/index.json"
        self.repository.routes[path] = (
            200, json.dumps({"versions": versions}).encode()
        )


class HttpGraphCliTests(HttpGraphHarness, unittest.TestCase):
    """Visit real-format NuGet manifests transitively without live services."""

    def test_transitive_dfs_cycle_and_case_insensitive_identity(self):
        """Visit A-B-D before C, preserve cycles and cache shared requests."""
        root = self.add_package("A", dependencies=[("B", "1.1"), ("C", "[1]")])
        branch = self.add_package("B", "1.2.0", [("D", "[1]")])
        leaf = self.add_package("D", dependencies=[("a", "[1]")])
        sibling = self.add_package(
            "C", dependencies=[("d", "1"), ("b", "[1.2]")]
        )
        for name in ("A", "C", "D"):
            self.add_versions(name, ["1.0.0"])
        self.add_versions("B", ["2.0.0", "1.2.0", "1.0.0"])
        result = self.run_cli()
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, (
            "A@1.0.0: B@1.2.0 C@1.0.0\n"
            "B@1.2.0: D@1.0.0\nD@1.0.0: A@1.0.0\n"
            "C@1.0.0: D@1.0.0 B@1.2.0\n"
        ))
        self.assertEqual(self.repository.requests, [
            "/v3/index.json", root, "/content/b/index.json", branch,
            "/content/d/index.json", leaf, "/content/a/index.json",
            "/content/c/index.json", sibling,
        ])

    def test_distinct_versions_and_platform_groups(self):
        """Retain two versions of a package and merge duplicate group edges."""
        root = self.add_package("A")
        self.repository.routes[root] = (200, b'''<package><metadata>
          <dependencies><group targetFramework="net8.0">
          <dependency id="B" version="[1]"/></group>
          <group targetFramework="net9.0"><dependency id="b" version="[2]"/>
          <dependency id="B" version="[1]"/></group>
          </dependencies></metadata></package>''')
        first = self.add_package("B")
        second = self.add_package("B", "2.0.0")
        self.add_versions("B", ["2.0.0", "1.0.0"])
        result = self.run_cli()
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, (
            "A@1.0.0: B@1.0.0 b@2.0.0\nB@1.0.0:\nb@2.0.0:\n"
        ))
        self.assertEqual(self.repository.requests, [
            "/v3/index.json", root, "/content/b/index.json", first, second,
        ])

    def test_filter_before_version_resolution(self):
        """Never request an excluded edge, even if its range is invalid."""
        root = self.add_package("A", dependencies=[("Skip.B", "bad")])
        result = self.run_cli({"--filter": "Skip."})
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "A@1.0.0:\n")
        self.assertEqual(self.repository.requests, ["/v3/index.json", root])

    def test_filter_root_does_not_request_service_index(self):
        """Return an empty graph before any request for an excluded root."""
        result = self.run_cli({"--filter": "A"})
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertIn("Граф пуст", result.stdout)
        self.assertEqual(self.repository.requests, [])

    def test_transitive_errors_do_not_print_partial_graph(self):
        """Report bad descendants or ranges through the normal CLI channel."""
        self.add_package("A", dependencies=[("B", "[1]")])
        self.add_versions("B", ["2.0.0"])
        self.assert_cli_error(self.run_cli(), "нет версии")
        self.add_versions("B", ["1.0.0"])
        self.assert_cli_error(self.run_cli(), "404")
        child = self.add_package("B")
        self.repository.routes[child] = (200, b"broken")
        self.assert_cli_error(self.run_cli(), "XML")
        self.add_package("A", dependencies=[("B", "bad")])
        self.assert_cli_error(self.run_cli(), "диапазон")

    def test_invalid_version_index(self):
        """Translate malformed version lists into useful package errors."""
        self.add_package("A", dependencies=[("B", "1")])
        for content in (b"broken", b"[]", b'{"versions": [null]}'):
            with self.subTest(content=content):
                self.repository.routes["/content/b/index.json"] = (200, content)
                self.assert_cli_error(self.run_cli(), "список версий")


if __name__ == "__main__":
    unittest.main()
