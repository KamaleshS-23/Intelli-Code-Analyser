"""Opened streams/connections that may never be closed."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class UnclosedResourceRule(BaseRule):
    name = "UnclosedResource"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for line in method.unclosed_resource_lines:
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity="critical",
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=line or method.line_number,
                            message=(
                                f"Resource opened at line {line} may never be closed."
                            ),
                            suggestion=(
                                "Wrap the stream in a try-with-resources statement "
                                "to prevent system resource leaks."
                            ),
                            metric_value=1,
                            metric_threshold=0,
                        )
                    )
        return issues
