"""Render the reachable dependency graph or print its dependency-first order."""

import sys

from config import parse_config
from graph import build_graph, format_graph
from load_order import DependencyCycleError, format_load_order
from nuget import RepositoryError
from nuget_repository import NugetRepository
from test_repository import TestRepository
from visualization import VisualizationError, format_plantuml, save_svg

ERROR_EXIT = 2
SUCCESS_EXIT = 0


def main(argv=None):
    """Build the graph and report processing errors before printing output."""
    config = parse_config(argv)
    try:
        source = TestRepository if config.test_mode else NugetRepository
        repository = source(config.repository)
        root = repository.root(config.package, config.version)
        graph = build_graph(root, repository, config.filter)
        if config.load_order:
            lines = format_load_order(graph)
        else:
            diagram = format_plantuml(graph)
            save_svg(diagram, config.output)
            if config.plantuml:
                lines = (diagram.rstrip("\n"),)
            else:
                lines = format_graph(graph, test_mode=config.test_mode)
    except (RepositoryError, DependencyCycleError, VisualizationError) as err:
        print(f"Ошибка: {err}", file=sys.stderr)
        return ERROR_EXIT
    for line in lines:
        print(line)
    return SUCCESS_EXIT


if __name__ == "__main__":
    sys.exit(main())
