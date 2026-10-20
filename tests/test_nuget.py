"""Verify NuGet manifests, version-specific requests and repository errors."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from test_cli import CliHarness, SUCCESS_EXIT

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nuget import (
    Dependency, RepositoryError, fetch_bytes, get_dependencies,
    normalized_version, parse_nuspec,
)


class ManifestTests(unittest.TestCase):
    """Cover NuGet XML layouts and URL version normalization."""

    def test_normalized_versions(self):
        """Use normalized, lowercase versions without build metadata."""
        cases = {
            "1": "1.0.0", "1.2": "1.2.0", "01.02.003.0": "1.2.3",
            "1.2.3.4": "1.2.3.4", "1.0.0-BETA.1+x": "1.0.0-beta.1",
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(normalized_version(original), expected)

    def test_framework_groups_and_ranges(self):
        """Preserve repeated names across different target frameworks."""
        content = b'''<package xmlns="urn:nuget"><metadata><dependencies>
          <group targetFramework="net8.0">
            <dependency id="B" version="[1.0,2.0)"/>
          </group><group targetFramework="net9.0">
            <dependency id="B" version="2.0"/>
            <dependency id="C"/>
          </group><group targetFramework="net10.0"/>
        </dependencies></metadata></package>'''
        self.assertEqual(parse_nuspec(content), [
            Dependency("B", "[1.0,2.0)", "net8.0"),
            Dependency("B", "2.0", "net9.0"),
            Dependency("C", "", "net9.0"),
        ])

    def test_flat_dependencies(self):
        """Read ungrouped dependencies with or without an XML namespace."""
        for namespace in ("", ' xmlns="urn:nuget"'):
            content = (
                f'<package{namespace}><metadata><dependencies>'
                '<dependency id="B" version="[1.0]"/>'
                '</dependencies></metadata></package>'
            )
            self.assertEqual(parse_nuspec(content), [
                Dependency("B", "[1.0]", "")
            ])

    def test_leaf_packages(self):
        """Treat missing dependencies and empty groups as empty lists."""
        for content in (
            '<package><metadata/></package>',
            '<package><metadata><dependencies/></metadata></package>',
            '<package><metadata><dependencies><group/>'
            '</dependencies></metadata></package>',
        ):
            self.assertEqual(parse_nuspec(content), [])

    def test_namespace_declared_only_on_metadata(self):
        """Accept older manifests whose root does not have a namespace."""
        leaf = b'''<package>
          <metadata xmlns="http://schemas.microsoft.com/packaging/2010/07/"
          /></package>'''
        self.assertEqual(parse_nuspec(leaf), [])
        content = b'''<package><metadata xmlns="urn:nuget"><dependencies>
          <dependency id="B" version="1"/>
          <group targetFramework="net8.0"><dependency id="C" version="2"/>
          </group></dependencies></metadata></package>'''
        self.assertEqual(parse_nuspec(content), [
            Dependency("B", "1", ""), Dependency("C", "2", "net8.0"),
        ])

    def test_invalid_manifests(self):
        """Reject invalid XML, missing metadata and invalid package names."""
        for content in (
            '<package', '<html/>', '<package/>',
            '<package><metadata><dependencies><dependency/>'
            '</dependencies></metadata></package>',
        ):
            with self.subTest(content=content):
                with self.assertRaises(RepositoryError):
                    parse_nuspec(content)

    def test_network_failures(self):
        """Translate connection failures and timeouts into domain errors."""
        for error in (URLError("unavailable"), TimeoutError("timeout")):
            with patch("nuget.urlopen", side_effect=error):
                with self.assertRaises(RepositoryError):
                    fetch_bytes("https://example.com/index.json")


class RepositoryTests(CliHarness, unittest.TestCase):
    """Exercise the real CLI against controlled NuGet HTTP responses."""

    def test_only_requested_version_and_direct_dependencies(self):
        """Build from exactly the root manifest and exclude matching edges."""
        path = "/content/newtonsoft.json/1.2.3/newtonsoft.json.nuspec"
        self.repository.routes[path] = (200, b'''<package><metadata>
          <dependencies><group targetFramework="net8.0">
          <dependency id="Microsoft.B" version="[2.0,3.0)"/>
          </group></dependencies></metadata></package>''')
        self.repository.requests.clear()
        result = self.run_cli({"--version": "01.02.003.0+build",
                               "--filter": "Microsoft."})
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout, "Newtonsoft.Json@1.2.3:\n")
        self.assertEqual(self.repository.requests, ["/v3/index.json", path])

    def test_direct_dependency_api_is_preserved(self):
        """Keep the stage-two fetch API available without traversing edges."""
        path = "/content/example/1.0.0/example.nuspec"
        self.repository.routes[path] = (200, b'''<package><metadata>
          <dependencies><dependency id="B" version="[2.0,3.0)"/>
          </dependencies></metadata></package>''')
        result = get_dependencies(
            self.repository.url + "/v3/index.json", "Example", "1"
        )
        self.assertEqual(result, [Dependency("B", "[2.0,3.0)", "")])

    def test_repository_errors(self):
        """Report missing resources and malformed index/manifest data."""
        path = "/content/newtonsoft.json/13.0.3/newtonsoft.json.nuspec"
        cases = [
            ("/v3/index.json", 503, b"unavailable", "HTTP 503"),
            ("/v3/index.json", 200, b"not json", "JSON"),
            ("/v3/index.json", 200, b"[]", "resources"),
            ("/v3/index.json", 200, b'{"resources": []}', "PackageBaseAddress"),
            (path, 404, b"missing", "404"),
            (path, 200, b"<broken", "XML"),
        ]
        for route, status, body, message in cases:
            with self.subTest(message=message):
                self.repository.set_index()
                self.repository.routes[path] = (
                    200, b"<package><metadata/></package>"
                )
                self.repository.routes[route] = (status, body)
                self.assert_cli_error(self.run_cli(), message)
        self.repository.set_index()
        self.repository.routes[path] = (200, b"<package><metadata/></package>")

    def test_invalid_resource_address(self):
        """Reject an absent or unsupported content resource URL."""
        for address in (None, "file:///tmp/private", "https://host:bad"):
            index = {"resources": [{"@type": "PackageBaseAddress/3.0.0",
                                     "@id": address}]}
            self.repository.routes["/v3/index.json"] = (
                200, json.dumps(index).encode()
            )
            self.assert_cli_error(self.run_cli(), "PackageBaseAddress")
        self.repository.set_index()


if __name__ == "__main__":
    unittest.main()
