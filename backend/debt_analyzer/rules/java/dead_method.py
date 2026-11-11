"""Private methods that are never called anywhere in the project."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class DeadMethodRule(BaseRule):
    name = "DeadMethod"

    def analyze(self, context):
        called = set()
        for cls in context.project.classes:
            for method in cls.methods:
                called.update(method.method_calls)

        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.is_constructor:
                    continue
                if "private" not in method.modifiers:
                    continue
                if method.name in called:
                    continue
                # Ignore common lifecycle / framework hooks that may be reflective.
                if method.name in ("main", "readObject", "writeObject"):
                    continue
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"Private method '{method.name}' is never called "
                            f"anywhere in the project."
                        ),
                        suggestion="Safely delete this unreferenced method.",
                        metric_value=0,
                        metric_threshold=1,
                    )
                )
        return issues
