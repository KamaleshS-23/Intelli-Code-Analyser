"""String concatenation with + inside loops."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class StringConcatenationInLoopRule(BaseRule):
    name = "StringConcatenationInLoop"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                line = method.string_concat_in_loop_line
                if not line:
                    continue
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=line,
                        message=(
                            f"String concatenation '+' used inside a loop "
                            f"at line {line}."
                        ),
                        suggestion=(
                            "Replace string concatenation with an explicit "
                            "StringBuilder instance initialized outside the loop."
                        ),
                        metric_value=1,
                        metric_threshold=0,
                    )
                )
        return issues
