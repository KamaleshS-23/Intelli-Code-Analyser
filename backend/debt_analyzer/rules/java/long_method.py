"""
Long Method
-----------
A method that does too much is hard to read, test, and change safely.
This is deliberately the same category of finding a tool like PMD would
raise ("method X is too long") - the difference comes later, in how the
AI reasoning agent (Phase 5) explains *why* and suggests a split.
"""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class LongMethodRule(BaseRule):
    name = "LongMethod"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                if method.line_count > thresholds.LONG_METHOD_LINES:
                    severity = (
                        "critical"
                        if method.line_count > thresholds.LONG_METHOD_LINES * 2
                        else "high"
                    )
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity=severity,
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=method.line_number,
                            message=(
                                f"Method '{method.name}' is {method.line_count} lines long "
                                f"(threshold: {thresholds.LONG_METHOD_LINES})."
                            ),
                            suggestion=(
                                "Consider extracting cohesive blocks of this method into "
                                "smaller, well-named private methods (Extract Method)."
                            ),
                            metric_value=method.line_count,
                            metric_threshold=thresholds.LONG_METHOD_LINES,
                        )
                    )
        return issues
