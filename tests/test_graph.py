"""Verify iterative DFS, exclusion, cycles and strict test-file parsing."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from graph import Package, build_graph, format_graph
from nuget import Dependency, RepositoryError
from test_repository import parse_repository

DEEP_GRAPH_SIZE = 1500


class MemoryRepository:
    """Record data requests while serving a small in-memory adjacency map."""

    def __init__(self, graph):
        """Keep the graph and requests for assertions about traversal."""
        self.graph = graph
        self.requests = []

    def dependencies(self, package):
        """Record each visit before exposing its declared outgoing edges."""
        self.requests.append(package.name)
        return [Dependency(name, "", "") for name in self.graph[package.name]]

    def resolve(self, dependency):
        """Create unversioned vertices from dependency names."""
        return Package(dependency.name)


class GraphTests(unittest.TestCase):
    """Require depth-first traversal without losing non-tree graph edges."""

    def test_depth_first_shared_nodes_and_disconnected_component(self):
        """Explore B's full branch before C, fetching shared D only once."""
        source = MemoryRepository({
            "A": ["B", "C", "B"], "B": ["D"], "C": ["D"],
            "D": [], "X": ["Y"], "Y": [],
        })
        graph = build_graph(Package("A"), source)
        self.assertEqual(source.requests, ["A", "B", "D", "C"])
        self.assertEqual(list(format_graph(graph)), [
            "A: B C", "B: D", "D:", "C: D",
        ])

    def test_self_loop_and_cycle(self):
        """Retain back edges, including a loop at the starting package."""
        source = MemoryRepository({"A": ["A", "B"], "B": ["C"], "C": ["A"]})
        graph = build_graph(Package("A"), source)
        self.assertEqual(source.requests, ["A", "B", "C"])
        self.assertEqual(list(format_graph(graph)), ["A: A B", "B: C", "C: A"])

    def test_filter_prunes_branch_but_retains_other_paths(self):
        """Exclude names containing the substring before data retrieval."""
        source = MemoryRepository({
            "A": ["XB", "C"], "XB": ["D", "E"], "C": ["D"],
            "D": [], "E": [],
        })
        graph = build_graph(Package("A"), source, "B")
        self.assertEqual(source.requests, ["A", "C", "D"])
        self.assertEqual(list(format_graph(graph)), ["A: C", "C: D", "D:"])

    def test_excluded_root_never_fetches_data(self):
        """Treat exclusion of the root as an empty reachable graph."""
        source = MemoryRepository({"ABC": ["D"], "D": []})
        graph = build_graph(Package("ABC"), source, "B")
        self.assertEqual(graph, {})
        self.assertEqual(source.requests, [])
        self.assertIn("Граф пуст", next(format_graph(graph)))

    def test_filter_is_literal_and_case_sensitive(self):
        """Use a plain substring, without patterns or case conversion."""
        source = MemoryRepository({"A": ["B"], "B": []})
        graph = build_graph(Package("A"), source, "b")
        self.assertEqual(list(format_graph(graph)), ["A: B", "B:"])

    def test_deep_graph_does_not_use_python_recursion(self):
        """Traverse a chain deeper than Python's normal recursion limit."""
        names = [f"P{number}" for number in range(DEEP_GRAPH_SIZE)]
        mapping = {name: [target] for name, target in zip(names, names[1:])}
        mapping[names[-1]] = []
        source = MemoryRepository(mapping)
        graph = build_graph(Package(names[0]), source)
        self.assertEqual(len(graph), DEEP_GRAPH_SIZE)
        self.assertEqual(source.requests, names)


class TestFileParserTests(unittest.TestCase):
    """Validate the complete test repository, including unused components."""

    def test_whitespace_duplicates_and_forward_references(self):
        """Allow blank lines, multi-letter names and deduplicate edges."""
        self.assertEqual(parse_repository("\n A : BB C BB\nBB:\nC: A\n"), {
            "A": ["BB", "C"], "BB": [], "C": ["A"],
        })

    def test_invalid_format_and_names(self):
        """Reject missing separators, lowercase, digits and punctuation."""
        for content in ("A B", ": A", "a:", "A: b", "A1:", "A: B:C"):
            with self.subTest(content=content):
                with self.assertRaisesRegex(RepositoryError, "строка 1"):
                    parse_repository(content)

    def test_duplicate_declaration(self):
        """Report the conflicting declaration with its line number."""
        with self.assertRaisesRegex(RepositoryError, "строка 2.*повторное"):
            parse_repository("A:\nA:\n")

    def test_undeclared_package(self):
        """Require explicit declarations even for leaf packages."""
        with self.assertRaisesRegex(RepositoryError, "не описаны пакеты: B"):
            parse_repository("A: B\n")


if __name__ == "__main__":
    unittest.main()
