"""Feature Envy - methods that mostly use another type's API."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class FeatureEnvyRule(BaseRule):
    name = "FeatureEnvy"

    def analyze(self, context):
        issues = []
        limit = thresholds.FEATURE_ENVY_ACCESSES
        for cls in context.project.classes:
            for method in cls.methods:
                accesses = method.parameter_type_accesses or {}
                if not accesses:
                    continue
                envied_type, count = max(accesses.items(), key=lambda item: item[1])
                if count <= limit:
                    continue
                simple = envied_type.split("<")[0].replace("[]", "")
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"Method '{method.name}' accesses '{simple}' data "
                            f"{count} times (threshold: {limit})."
                        ),
                        suggestion=(
                            f"Move this method directly into the '{simple}' class "
                            f"so data and behavior live together."
                        ),
                        metric_value=count,
                        metric_threshold=limit,
                    )
                )
        return issues
