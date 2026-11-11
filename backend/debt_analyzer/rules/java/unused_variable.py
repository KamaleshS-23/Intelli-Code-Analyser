"""Unused local variables assigned but never read."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class UnusedVariableRule(BaseRule):
    name = "UnusedVariable"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for var in method.unused_local_vars:
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity="low",
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=var.get("line", method.line_number),
                            message=(
                                f"Variable '{var['name']}' is assigned but its value "
                                f"is never read."
                            ),
                            suggestion=(
                                "Remove the unused variable to improve readability "
                                "and reduce memory overhead."
                            ),
                            metric_value=1,
                            metric_threshold=0,
                        )
                    )
        return issues
