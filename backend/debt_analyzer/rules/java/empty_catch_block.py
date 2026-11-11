"""Empty catch blocks that swallow exceptions."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class EmptyCatchBlockRule(BaseRule):
    name = "EmptyCatchBlock"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for line in method.empty_catch_lines:
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity="high",
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=line or method.line_number,
                            message=(
                                "Empty catch block hides potential runtime failures."
                            ),
                            suggestion=(
                                "Log the exception or rethrow it as a custom "
                                "application runtime exception."
                            ),
                            metric_value=1,
                            metric_threshold=0,
                        )
                    )
        return issues
