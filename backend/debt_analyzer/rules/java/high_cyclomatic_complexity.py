"""High cyclomatic complexity methods."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class HighCyclomaticComplexityRule(BaseRule):
    name = "HighCyclomaticComplexity"

    def analyze(self, context):
        issues = []
        limit = thresholds.CYCLOMATIC_COMPLEXITY
        for cls in context.project.classes:
            for method in cls.methods:
                complexity = method.cyclomatic_complexity
                if complexity <= limit:
                    continue
                severity = "critical" if complexity > limit * 1.5 else "high"
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity=severity,
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"Method '{method.name}' has a Cyclomatic Complexity "
                            f"of {complexity} (threshold: {limit})."
                        ),
                        suggestion=(
                            "Refactor by breaking down complex branch structures "
                            "using polymorphism or early returns."
                        ),
                        metric_value=complexity,
                        metric_threshold=limit,
                    )
                )
        return issues
