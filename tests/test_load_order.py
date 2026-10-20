"""Verify dependency-first order, stable ties and cycle diagnostics."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from graph import Package, build_graph
from load_order import DependencyCycleError, dependency_order, format_load_order
from test_graph import DEEP_GRAPH_SIZE, MemoryRepository

DAG_SIZE = 20
DAG_CASES = 30
RANDOM_SEED = 17


class LoadOrderTests(unittest.TestCase):
    """Require every dependency to precede its consumer exactly once."""

    def order(self, mapping, excluded=""):
        """Build a reachable graph using the unchanged stage-three API."""
        graph = build_graph(Package("A"), MemoryRepository(mapping), excluded)
        return format_load_order(graph)

    def test_chain_diamond_duplicates_and_independent_branches(self):
        """Use DFS completion order and preserve declared sibling order."""
        cases = [
            ({"A": ["B"], "B": ["C"], "C": []}, ["C", "B", "A"]),
            ({"A": ["B", "C", "B"], "B": ["D"], "C": ["D"], "D": []},
             ["D", "B", "C", "A"]),
            ({"A": ["C", "B"], "B": [], "C": []}, ["C", "B", "A"]),
            ({"A": ["B", "C"], "B": [], "C": ["B"]}, ["B", "C", "A"]),
        ]
        for mapping, expected in cases:
            with self.subTest(mapping=mapping):
                self.assertEqual(self.order(mapping), expected)

    def test_leaf_and_unreachable_cycle(self):
        """Do not include or reject components outside the root graph."""
        self.assertEqual(self.order({"A": [], "X": ["X"]}), ["A"])

    def test_filter_removes_cycle_but_keeps_shared_descendant(self):
        """Apply stage-three exclusion before calculating the order."""
        mapping = {
            "A": ["B", "C"], "B": ["A", "D"], "C": ["D"], "D": [],
        }
        self.assertEqual(self.order(mapping, "B"), ["D", "C", "A"])
        self.assertEqual(dependency_order({}), [])
        self.assertIn("исключён фильтром", self.order(mapping, "A")[0])

    def test_cycles_report_only_the_actual_closed_path(self):
        """Reject self-loops and inner cycles after already completed leaves."""
        cases = [
            ({"A": ["A"]}, "A -> A"),
            ({"A": ["B"], "B": ["C"], "C": ["A"]},
             "A -> B -> C -> A"),
            ({"A": ["D", "B"], "D": [], "B": ["C"], "C": ["B"]},
             "B -> C -> B"),
        ]
        for mapping, path in cases:
            with self.subTest(mapping=mapping):
                with self.assertRaises(DependencyCycleError) as raised:
                    self.order(mapping)
                self.assertEqual(str(raised.exception), (
                    f"порядок загрузки невозможен: цикл {path}"
                ))

    def test_versions_identify_distinct_vertices(self):
        """Keep different concrete versions and their labels in the order."""
        root = Package("A", "1.0.0")
        first = Package("B", "1.0.0")
        second = Package("B", "2.0.0")
        graph = {root: [first, second], first: [], second: []}
        self.assertEqual(format_load_order(graph), [
            "B@1.0.0", "B@2.0.0", "A@1.0.0",
        ])

    def test_chain_beyond_recursion_limit(self):
        """Calculate the order without using Python's call stack."""
        packages = [Package(f"P{number}") for number in range(DEEP_GRAPH_SIZE)]
        graph = {item: [target] for item, target in zip(packages, packages[1:])}
        graph[packages[-1]] = []
        self.assertEqual(dependency_order(graph), list(reversed(packages)))

    def test_topological_invariant_for_generated_dags(self):
        """Check all edges across reproducible branching DAGs and key orders."""
        randomizer = random.Random(RANDOM_SEED)
        packages = [Package(f"P{number}") for number in range(DAG_SIZE)]
        for _ in range(DAG_CASES):
            keys = randomizer.sample(packages, len(packages))
            graph = {}
            for item in keys:
                index = packages.index(item)
                candidates = packages[index + 1:]
                count = randomizer.randrange(len(candidates) + 1)
                graph[item] = randomizer.sample(candidates, count)
            order = dependency_order(graph)
            positions = {item: index for index, item in enumerate(order)}
            self.assertEqual(set(order), set(graph))
            self.assertEqual(len(order), len(graph))
            for item, dependencies in graph.items():
                for target in dependencies:
                    self.assertLess(positions[target], positions[item])


if __name__ == "__main__":
    unittest.main()
