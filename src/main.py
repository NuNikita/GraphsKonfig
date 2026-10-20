"""Build and print the reachable NuGet or test-repository dependency graph."""

import sys

from config import parse_config
from graph import build_graph, format_graph
from nuget import RepositoryError
from nuget_repository import NugetRepository
from test_repository import TestRepository

ERROR_EXIT = 2
SUCCESS_EXIT = 0


def main(argv=None):
    """Validate configuration, build the graph and report repository errors."""
    config = parse_config(argv)
    try:
        source = TestRepository if config.test_mode else NugetRepository
        repository = source(config.repository)
        root = repository.root(config.package, config.version)
        graph = build_graph(root, repository, config.filter)
    except RepositoryError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return ERROR_EXIT
    for line in format_graph(graph):
        print(line)
    return SUCCESS_EXIT


if __name__ == "__main__":
    sys.exit(main())
