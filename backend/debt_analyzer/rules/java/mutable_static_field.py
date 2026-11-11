"""Non-final static fields that are unsafe for concurrent access."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class MutableStaticFieldRule(BaseRule):
    name = "MutableStaticField"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for field in cls.mutable_static_fields:
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="high",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=None,
                        line_number=field.get("line", 0),
                        message=(
                            f"Non-final static field '{field.get('name')}' "
                            f"may be modified across multiple threads."
                        ),
                        suggestion=(
                            "Use ConcurrentHashMap / Atomic* types, or make the "
                            "field immutable and update it via synchronized access."
                        ),
                        metric_value=1,
                        metric_threshold=0,
                    )
                )
        return issues
