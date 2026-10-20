"""Compute a dependency-first loading order using iterative DFS."""


class DependencyCycleError(ValueError):
    """Report a cycle that prevents a dependency-first loading order."""


def dependency_order(graph):
    """Return each vertex once after its dependencies; reject cycles."""
    ordered = []
    finished = set()
    active = {}
    for root in graph:
        if root in finished:
            continue
        stack = [(root, iter(graph[root]))]
        active[root] = len(active)
        while stack:
            package, pending = stack[-1]
            dependency = next(pending, None)
            if dependency is None:
                stack.pop()
                del active[package]
                finished.add(package)
                ordered.append(package)
            elif dependency in active:
                cycle = [item for item, _ in stack[active[dependency]:]]
                labels = [item.label() for item in [*cycle, dependency]]
                path = " -> ".join(labels)
                raise DependencyCycleError(
                    f"порядок загрузки невозможен: цикл {path}"
                )
            elif dependency not in finished:
                active[dependency] = len(stack)
                stack.append((dependency, iter(graph[dependency])))
    return ordered


def format_load_order(graph):
    """Prepare the complete output before printing, avoiding partial orders."""
    if not graph:
        return ["Порядок загрузки пуст: исходный пакет исключён фильтром."]
    return [package.label() for package in dependency_order(graph)]
