"""
Large Class
-----------
Simple line-count based smell, complementary to GodClass (which looks at
method/field counts). A file can be long without necessarily having too
many methods (e.g. one enormous method), so both checks are useful.
"""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class LargeClassRule(BaseRule):
    name = "LargeClass"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            if cls.line_count > thresholds.LARGE_CLASS_LINES:
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        line_number=0,
                        message=(
                            f"File containing '{cls.name}' is {cls.line_count} lines "
                            f"(threshold: {thresholds.LARGE_CLASS_LINES})."
                        ),
                        suggestion=(
                            "Consider splitting this file's responsibilities across "
                            "smaller, more focused classes."
                        ),
                        metric_value=cls.line_count,
                        metric_threshold=thresholds.LARGE_CLASS_LINES,
                    )
                )
        return issues
