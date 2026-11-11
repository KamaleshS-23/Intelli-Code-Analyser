"""Methods with too many parameters (DTO / Parameter Object candidate)."""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class ExcessiveParameterListRule(BaseRule):
    name = "ExcessiveParameterList"

    def analyze(self, context):
        issues = []
        limit = thresholds.EXCESSIVE_PARAMETER_LIST
        for cls in context.project.classes:
            for method in cls.methods:
                count = len(method.parameters)
                if count <= limit:
                    continue
                param_names = ", ".join(p.name for p in method.parameters)
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"Method '{method.name}' takes {count} parameters "
                            f"({param_names}); threshold is {limit}."
                        ),
                        suggestion=(
                            "Introduce a Data Transfer Object (DTO) or Parameter "
                            "Object to encapsulate these arguments."
                        ),
                        metric_value=count,
                        metric_threshold=limit,
                    )
                )
        return issues
