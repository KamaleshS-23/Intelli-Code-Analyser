"""Hardcoded passwords, API keys, and similar credentials."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue


class HardcodedCredentialsRule(BaseRule):
    name = "HardcodedCredentials"

    def analyze(self, context):
        issues = []
        for cls in context.project.classes:
            for method in cls.methods:
                for entry in method.hardcoded_credential_lines:
                    issues.append(
                        DebtIssue(
                            rule=self.name,
                            severity="critical",
                            class_name=cls.fully_qualified_name,
                            file_path=cls.file_path,
                            method_name=method.name,
                            line_number=entry.get("line", method.line_number),
                            message=(
                                f"Possible hardcoded password found assigned to "
                                f"variable '{entry.get('name', '?')}'."
                            ),
                            suggestion=(
                                "Move sensitive credentials to external environment "
                                "variables or a secret vault."
                            ),
                            metric_value=1,
                            metric_threshold=0,
                        )
                    )
        return issues
