"""
Deep Inheritance Tree
----------------------
A class buried under many levels of inheritance is hard to understand
(you have to read every ancestor to know what it actually does) and
fragile (a change to any ancestor can silently change this class's
behaviour - the "fragile base class" problem).
"""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class DeepInheritanceRule(BaseRule):
    name = "DeepInheritance"

    def analyze(self, context):
        issues = []
        classes_by_fqn = {c.fully_qualified_name: c for c in context.project.classes}

        for fqn, depth in context.inheritance_depth.items():
            if depth > thresholds.DEEP_INHERITANCE:
                cls = classes_by_fqn.get(fqn)
                if cls is None:
                    continue
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="medium",
                        class_name=fqn,
                        file_path=cls.file_path,
                        message=(
                            f"'{cls.name}' sits {depth} levels deep in the inheritance "
                            f"tree (threshold: {thresholds.DEEP_INHERITANCE})."
                        ),
                        suggestion=(
                            "Favor composition over inheritance where possible; "
                            "flatten the hierarchy or extract shared behaviour into "
                            "smaller, composable helper classes."
                        ),
                        metric_value=depth,
                        metric_threshold=thresholds.DEEP_INHERITANCE,
                    )
                )
        return issues
