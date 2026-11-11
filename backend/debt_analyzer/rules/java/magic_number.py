"""Hardcoded numeric literals that should be named constants."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class MagicNumberRule(BaseRule):
    name = "MagicNumber"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                seen = set()
                for entry in method.magic_numbers:
                    value = entry.get("value")
                    line = entry.get("line", method.line_number)
                    key = (value, line)
                    if key in seen:
                        continue
                    seen.add(key)
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity="low",
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=line,
                            message=f"Magic number '{value}' detected.",
                            suggestion=(
                                f"Extract '{value}' into a static final constant "
                                f"with a descriptive name."
                            ),
                            metric_value=value,
                            metric_threshold=0,
                        )
                    )
        return issues
