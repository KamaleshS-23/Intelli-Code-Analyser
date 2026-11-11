from debt_analyzer.models import DebtIssue
from debt_analyzer.rules.base_rule import BaseRule


class PythonBaseRule(BaseRule):
    def _issue(self, class_name, method_name, line_number, message, suggestion, severity="medium", metric_value=None, metric_threshold=None):
        return DebtIssue(
            rule=self.name,
            severity=severity,
            class_name=class_name,
            method_name=method_name,
            line_number=line_number,
            message=message,
            suggestion=suggestion,
            metric_value=metric_value,
            metric_threshold=metric_threshold,
        )


class PythonLongMethodRule(PythonBaseRule):
    name = "LongMethod"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.line_count >= 25:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.line_number,
                        f"Method '{method.name}' is too long ({method.line_count} lines).",
                        "Refactor into smaller helper methods or split responsibilities.",
                        severity="medium" if method.line_count < 40 else "high",
                        metric_value=method.line_count,
                        metric_threshold=25,
                    ))
        return issues


class PythonHighCyclomaticComplexityRule(PythonBaseRule):
    name = "HighCyclomaticComplexity"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.cyclomatic_complexity >= 8:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.line_number,
                        f"Method '{method.name}' has cyclomatic complexity {method.cyclomatic_complexity}.",
                        "Reduce branching and extract decision logic into dedicated functions.",
                        severity="high" if method.cyclomatic_complexity >= 12 else "medium",
                        metric_value=method.cyclomatic_complexity,
                        metric_threshold=8,
                    ))
        return issues


class PythonDeepNestingRule(PythonBaseRule):
    name = "DeepNesting"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.max_nesting_depth >= 4:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.line_number,
                        f"Method '{method.name}' nests logic too deeply ({method.max_nesting_depth}).",
                        "Flatten conditionals and extract nested branches into helper methods.",
                        severity="medium" if method.max_nesting_depth < 6 else "high",
                        metric_value=method.max_nesting_depth,
                        metric_threshold=4,
                    ))
        return issues


class PythonMagicNumberRule(PythonBaseRule):
    name = "MagicNumber"
    ALLOWED_VALUES = {0, 1, -1, 2, 100}

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for entry in method.magic_numbers:
                    if entry.get("value") in self.ALLOWED_VALUES:
                        continue
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        entry.get("line", 0),
                        f"Magic number {entry.get('value')} used in method '{method.name}'.",
                        "Replace numeric literals with named constants or enums.",
                        severity="low",
                        metric_value=entry.get("value"),
                        metric_threshold=0,
                    ))
        return issues


class PythonUnusedVariableRule(PythonBaseRule):
    name = "UnusedVariable"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for entry in method.unused_local_vars:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        entry.get("line", 0),
                        f"Variable '{entry.get('name')}' is assigned but never used in '{method.name}'.",
                        "Remove the unused variable or use it to simplify the logic.",
                        severity="low",
                    ))
        return issues


class PythonHardcodedCredentialsRule(PythonBaseRule):
    name = "HardcodedCredentials"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for entry in method.hardcoded_credential_lines:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        entry.get("line", 0),
                        "Hardcoded credential or secret detected.",
                        "Move configuration to environment variables or a secure configuration provider.",
                        severity="critical",
                        metric_value=1,
                        metric_threshold=0,
                    ))
        return issues


class PythonGenericExceptionHandlingRule(PythonBaseRule):
    name = "GenericExceptionHandling"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.empty_catch_lines:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.line_number,
                        f"Method '{method.name}' handles generic exceptions without meaningful recovery.",
                        "Catch specific exceptions and log actionable context.",
                        severity="medium",
                    ))
        return issues


class PythonStringConcatenationInLoopRule(PythonBaseRule):
    name = "StringConcatenationInLoop"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.string_concat_in_loop_line:
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.string_concat_in_loop_line,
                        f"String concatenation inside a loop detected in '{method.name}'.",
                        "Use list accumulation or join() to avoid quadratic string growth.",
                        severity="medium",
                    ))
        return issues


class PythonCircularDependencyRule(PythonBaseRule):
    name = "CircularDependency"

    def analyze(self, context):
        issues = []
        graph = {}
        for edge in context.project.dependencies:
            graph.setdefault(edge.get("from"), []).append(edge.get("to"))

        seen = set()
        stack = []

        def dfs(node):
            seen.add(node)
            stack.append(node)
            for neighbor in graph.get(node, []):
                if neighbor in stack:
                    cycle = stack[stack.index(neighbor):] + [neighbor]
                    for item in cycle[:-1]:
                        if item not in seen:
                            seen.add(item)
                    return cycle
                if neighbor not in seen:
                    result = dfs(neighbor)
                    if result:
                        return result
            stack.pop()
            return None

        for node in sorted(graph):
            if node not in seen:
                cycle = dfs(node)
                if cycle:
                    issues.append(self._issue(
                        cycle[0],
                        None,
                        0,
                        f"Circular dependency detected: {' -> '.join(cycle)}.",
                        "Break the dependency cycle by extracting shared interfaces or responsibilities.",
                        severity="high",
                    ))
        return issues


class PythonDeadMethodRule(PythonBaseRule):
    name = "DeadMethod"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.name.startswith("unused_") or method.name.startswith("legacy_"):
                    issues.append(self._issue(
                        cls.fully_qualified_name,
                        method.name,
                        method.line_number,
                        f"Method '{method.name}' appears to be dead or legacy code.",
                        "Remove the method or replace it with a tested path.",
                        severity="low",
                    ))
        return issues


class PythonPossibleRefactorIssueRule(PythonBaseRule):
    name = "PossibleRefactorIssue"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                reasons = []
                if method.line_count >= 30:
                    reasons.append(f"long method ({method.line_count} lines)")
                if method.cyclomatic_complexity >= 10:
                    reasons.append(f"high complexity ({method.cyclomatic_complexity})")
                if len(getattr(method, "parameters", [])) >= 5:
                    reasons.append(f"too many parameters ({len(method.parameters)})")
                if method.max_nesting_depth >= 5:
                    reasons.append(f"deep nesting ({method.max_nesting_depth})")

                if not reasons:
                    continue

                issues.append(self._issue(
                    cls.fully_qualified_name,
                    method.name,
                    method.line_number,
                    f"Method '{method.name}' is a likely refactoring candidate: {', '.join(reasons)}.",
                    "Extract helper methods, reduce branching, and split responsibilities to make the logic easier to maintain.",
                    severity="medium" if len(reasons) <= 2 else "high",
                    metric_value=max(
                        getattr(method, "line_count", 0),
                        getattr(method, "cyclomatic_complexity", 0),
                        len(getattr(method, "parameters", [])),
                    ),
                    metric_threshold=10,
                ))
        return issues
