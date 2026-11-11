"""Catching generic Exception / Throwable instead of specific types."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class GenericExceptionHandlingRule(BaseRule):
    name = "GenericExceptionHandling"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                line = method.catches_generic_exception_line
                if not line:
                    continue
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="low",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=line,
                        message=(
                            f"Method catches generic 'Exception' instead of "
                            f"domain-specific exceptions."
                        ),
                        suggestion=(
                            "Catch specific exceptions to allow targeted recovery."
                        ),
                        metric_value=1,
                        metric_threshold=0,
                    )
                )
        return issues
