"""Circular class dependencies within the scanned project."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class CircularDependencyRule(BaseRule):
    name = "CircularDependency"

    def analyze(self, context):
        graph = {}
        for edge in context.project.dependencies:
            source = edge.get("from")
            target = edge.get("to")
            if not source or not target:
                continue
            graph.setdefault(source, set()).add(target)

        classes_by_fqn = {c.fully_qualified_name: c for c in context.project.classes}
        cycles = []
        path = []
        visiting = set()
        visited = set()

        def dfs(node):
            if node in visiting:
                if node in path:
                    cycle = path[path.index(node):] + [node]
                    if len(cycle) >= 3:
                        cycles.append(cycle)
                return
            if node in visited:
                return
            visiting.add(node)
            path.append(node)
            for neighbor in graph.get(node, ()):
                dfs(neighbor)
            path.pop()
            visiting.remove(node)
            visited.add(node)

        for fqn in list(graph.keys()):
            dfs(fqn)

        # Deduplicate cycles that are rotations of each other.
        unique = []
        seen = set()
        for cycle in cycles:
            core = cycle[:-1]
            rotations = []
            for i in range(len(core)):
                rotated = tuple(core[i:] + core[:i])
                rotations.append(rotated)
                rotations.append(tuple(reversed(rotated)))
            key = min(rotations)
            if key in seen:
                continue
            seen.add(key)
            unique.append(cycle)

        issues = []
        for cycle in unique:
            start = cycle[0]
            cls = classes_by_fqn.get(start)
            if cls is None:
                continue
            display = " -> ".join(name.split(".")[-1] for name in cycle)
            issues.append(
                DebtIssue(
                    rule=self.name,
                    severity="high",
                    class_name=start,
                    file_path=cls.file_path,
                    method_name=None,
                    line_number=1,
                    message=f"Circular dependency detected: {display}.",
                    suggestion=(
                        "Break the loop by introducing a shared interface or "
                        "event publisher pattern."
                    ),
                    metric_value=1,
                    metric_threshold=0,
                )
            )
        return issues
