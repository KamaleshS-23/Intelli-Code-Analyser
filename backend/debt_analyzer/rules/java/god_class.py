"""
God Class (a.k.a. Blob)
------------------------
A class that has accumulated far too many responsibilities: too many
methods AND too many fields. This is one of the most damaging smells
because it usually means the class violates the Single Responsibility
Principle in several different ways at once.
"""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class GodClassRule(BaseRule):
    name = "GodClass"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            method_count = len(cls.methods)
            field_count = len(cls.fields)

            too_many_methods = method_count > thresholds.GOD_CLASS_METHODS
            too_many_fields = field_count > thresholds.GOD_CLASS_FIELDS

            if too_many_methods and too_many_fields:
                severity = "critical"
            elif too_many_methods or too_many_fields:
                severity = "high"
            else:
                continue

            issues.append(
                DebtIssue(
                    rule=self.name,
                    severity=severity,
                    class_name=cls.fully_qualified_name,
                    file_path=cls.file_path,
                    line_number=0,
                    message=(
                        f"Class '{cls.name}' has {method_count} methods and "
                        f"{field_count} fields, suggesting it has taken on too "
                        f"many responsibilities."
                    ),
                    suggestion=(
                        "Split this class by responsibility - group related methods "
                        "and the fields they use into their own classes (Extract Class)."
                    ),
                    metric_value=method_count + field_count,
                    metric_threshold=thresholds.GOD_CLASS_METHODS
                    + thresholds.GOD_CLASS_FIELDS,
                )
            )
        return issues
