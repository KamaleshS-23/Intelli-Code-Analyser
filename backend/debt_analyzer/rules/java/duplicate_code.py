"""
Duplicate Code
--------------
Groups methods project-wide by their normalized body hash (computed in
scanner/java_parser/java_ast_parser.py). Any group with more than one
method is an exact-clone (Type-1) duplicate: identical logic, possibly
different variable names aren't accounted for here - only whitespace/
comments are ignored.

Trivial short methods (getters/setters) are excluded by default via
MIN_DUPLICATE_LINES, since flagging `getName(){return name;}` as
"duplicated" across every class in the project isn't useful signal.
"""

from collections import defaultdict

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class DuplicateCodeRule(BaseRule):
    name = "DuplicateCode"

    def analyze(self, context):
        issues = []
        groups = defaultdict(list)

        for cls in context.project.classes:
            for method in cls.methods:
                if not method.body_hash:
                    continue
                if method.non_blank_lines < thresholds.MIN_DUPLICATE_LINES:
                    continue
                groups[method.body_hash].append((cls, method))

        for body_hash, members in groups.items():
            if len(members) < 2:
                continue

            locations = [
                f"{cls.name}.{method.name}() (line {method.line_number})"
                for cls, method in members
            ]
            severity = "high" if len(members) > 2 else "medium"

            # Raise one issue per involved method so each shows up against
            # the right class/file in the dashboard, but they all reference
            # the same duplicate group.
            for cls, method in members:
                other_locations = [loc for loc in locations if loc != f"{cls.name}.{method.name}() (line {method.line_number})"]
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity=severity,
                        class_name=cls.fully_qualified_name,
                        file_path=cls.file_path,
                        method_name=method.name,
                        line_number=method.line_number,
                        message=(
                            f"'{method.name}' duplicates logic found in: "
                            f"{', '.join(other_locations)}."
                        ),
                        suggestion=(
                            "Extract the shared logic into a single reusable method "
                            "(e.g. a helper/utility method or a shared base class) "
                            "and have all duplicates call it."
                        ),
                        metric_value=len(members),
                        metric_threshold=1,
                    )
                )
        return issues
