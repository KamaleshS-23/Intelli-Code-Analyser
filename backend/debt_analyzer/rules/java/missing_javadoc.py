"""Public API methods missing Javadoc."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class MissingJavadocRule(BaseRule):
    name = "MissingJavadoc"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.is_constructor:
                    continue
                if "public" not in method.modifiers:
                    continue
                if method.has_javadoc:
                    continue
                # Skip trivial accessors.
                if method.name.startswith(("get", "set", "is")) and method.line_count <= 3:
                    continue
                if method.non_blank_lines <= 2:
                    continue
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="low",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"Public API method '{method.name}' lacks Javadoc comments."
                        ),
                        suggestion=(
                            "Add documentation specifying parameter invariants, "
                            "return values, and thrown exceptions."
                        ),
                        metric_value=0,
                        metric_threshold=1,
                    )
                )
        return issues
