"""Deeply nested control structures."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class DeepNestingRule(BaseRule):
    name = "DeepNesting"

    def analyze(self, context):
        issues = []
        limit = thresholds.DEEP_NESTING
        for cls in context.project.classes:
            for method in cls.methods:
                depth = method.max_nesting_depth
                if depth <= limit:
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
                            f"Control structure is nested {depth} levels deep "
                            f"(threshold: {limit})."
                        ),
                        suggestion=(
                            "Use guard clauses (early returns) to flatten nested "
                            "conditional logic."
                        ),
                        metric_value=depth,
                        metric_threshold=limit,
                    )
                )
        return issues
