"""Print the reachable dependency graph or its dependency-first order."""

import sys

from config import parse_config
from graph import build_graph, format_graph
from load_order import DependencyCycleError, format_load_order
from nuget import RepositoryError
from nuget_repository import NugetRepository
from test_repository import TestRepository

ERROR_EXIT = 2
SUCCESS_EXIT = 0


def main(argv=None):
    """Build the graph, select output and report repository or cycle errors."""
    config = parse_config(argv)
    try:
        source = TestRepository if config.test_mode else NugetRepository
        repository = source(config.repository)
        root = repository.root(config.package, config.version)
        graph = build_graph(root, repository, config.filter)
        formatter = format_load_order if config.load_order else format_graph
        lines = formatter(graph)
    except (RepositoryError, DependencyCycleError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return ERROR_EXIT
    for line in lines:
        print(line)
    return SUCCESS_EXIT


if __name__ == "__main__":
    sys.exit(main())
