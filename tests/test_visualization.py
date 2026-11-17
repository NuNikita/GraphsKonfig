"""Check PlantUML output, CLI SVG rendering and failure handling."""

import os
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from test_cli import CliHarness, OUTPUT, SUCCESS_EXIT


class VisualizationCliTests(CliHarness, unittest.TestCase):
    """Exercise visualization with local graph data and real PlantUML."""

    def run_diagram(self, content, **options):
        """Render the given repository and ask for the PlantUML source."""
        (self.workdir / "repository.txt").write_text(content, encoding="utf-8")
        return self.run_cli({
            "--package": "A", "--version": "1",
            "--repository": "repository.txt", **options,
        }, ["--test-mode", "--plantuml"])

    def test_versions_cycles_and_isolated_components(self):
        """Preserve both versions, a back edge and a self-loop in the SVG."""
        result = self.run_diagram("A@1: A@2\nA@2: A@1 A@2\nB@1:\n")
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "@startuml", "!pragma layout smetana", "left to right direction",
            'rectangle "A@1.0.0" as p0', 'rectangle "A@2.0.0" as p1',
            "p0 --> p1", "p1 --> p0", "p1 --> p1", "@enduml",
        ])
        root = ElementTree.parse(self.workdir / OUTPUT).getroot()
        labels = [element.text for element in root.findall(".//{*}text")]
        self.assertCountEqual(labels, ["A@1.0.0", "A@2.0.0"])

    def test_filtered_root_renders_empty_graph(self):
        """Render an explanatory note for the empty graph."""
        result = self.run_diagram("A@1: B@1\nB@1:\n", **{"--filter": "A"})
        self.assertEqual(result.returncode, SUCCESS_EXIT, result.stderr)
        self.assertNotIn("rectangle", result.stdout)
        svg = ElementTree.parse(self.workdir / OUTPUT)
        self.assertIn("Граф пуст", "".join(svg.getroot().itertext()))

    def test_render_failure_preserves_previous_file(self):
        """Keep the prior SVG and suppress stdout if PlantUML fails."""
        output = self.workdir / OUTPUT
        output.write_bytes(b"old image")
        with patch.dict(os.environ, {"PLANTUML_JAR": "missing.jar"}):
            result = self.run_diagram("A@1:\n")
        self.assert_cli_error(result, "PlantUML")
        self.assertEqual(output.read_bytes(), b"old image")

    def test_repository_cannot_be_overwritten(self):
        """Reject a destination that would replace the repository file."""
        repository = self.workdir / OUTPUT
        repository.write_text("A@1:\n", encoding="utf-8")
        result = self.run_cli({
            "--package": "A", "--version": "1", "--repository": OUTPUT,
        }, ["--test-mode"])
        self.assert_cli_error(result, "--output")
        self.assertEqual(repository.read_text(encoding="utf-8"), "A@1:\n")
