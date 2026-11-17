"""Build a dependency graph using an explicit DFS stack, without recursion."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Package:
    """Identify a graph vertex by its package name and concrete version."""

    name: str
    version: str = ""

    def label(self):
        """Display a package name together with its version when provided."""
        return f"{self.name}@{self.version}" if self.version else self.name

    def display_label(self):
        """Display the version in parentheses for test-repository output."""
        return f"{self.name} ({self.version})" if self.version else self.name


def children(package, repository, excluded):
    """Resolve allowed edges lazily so DFS visits each branch immediately."""
    for dependency in repository.dependencies(package):
        if excluded and excluded in dependency.name:
            continue
        yield repository.resolve(dependency)


def build_graph(root, repository, excluded=""):
    """Visit reachable vertices once, retaining shared edges and cycles."""
    graph = {}
    if excluded and excluded in root.name:
        return graph
    graph[root] = []
    stack = [(root, children(root, repository, excluded))]
    while stack:
        package, pending = stack[-1]
        dependency = next(pending, None)
        if dependency is None:
            stack.pop()
            continue
        if dependency not in graph[package]:
            graph[package].append(dependency)
        if dependency not in graph:
            graph[dependency] = []
            stack.append((
                dependency, children(dependency, repository, excluded)
            ))
    return graph


def format_graph(graph, *, test_mode=False):
    """Yield adjacency lists in discovery order, including empty vertices."""
    if not graph:
        yield "Граф пуст: исходный пакет исключён фильтром."
    label = Package.display_label if test_mode else Package.label
    separator = ", " if test_mode else " "
    delimiter = " →" if test_mode else ":"
    for package, dependencies in graph.items():
        targets = separator.join(label(target) for target in dependencies)
        yield f"{label(package)}{delimiter} {targets}".rstrip()
