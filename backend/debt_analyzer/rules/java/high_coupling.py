"""
High Coupling
-------------
Reuses the afferent/efferent coupling metrics already computed by
scanner/graph_builder.py in Phase 1 - no need to recompute the dependency
graph here.

- High efferent coupling (Ce): this class depends on too many others ->
  it's fragile, since a change in any of them can break it.
- High afferent coupling (Ca): too many other classes depend on this one ->
  it's risky to change, since it will ripple outward.
"""

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.models import DebtIssue
from debt_analyzer import thresholds


class HighCouplingRule(BaseRule):
    name = "HighCoupling"

    def analyze(self, context):
        issues = []
        classes_by_fqn = {c.fully_qualified_name: c for c in context.project.classes}

        for fqn, metrics in context.coupling_metrics.items():
            cls = classes_by_fqn.get(fqn)
            if cls is None:
                continue

            ce = metrics.get("efferent_coupling", 0)
            ca = metrics.get("afferent_coupling", 0)

            if ce > thresholds.HIGH_EFFERENT_COUPLING:
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="high",
                        class_name=fqn,
                        file_path=cls.file_path,
                        message=(
                            f"'{cls.name}' depends on {ce} other project classes "
                            f"(threshold: {thresholds.HIGH_EFFERENT_COUPLING}), making it "
                            f"fragile to changes elsewhere in the codebase."
                        ),
                        suggestion=(
                            "Reduce direct dependencies by introducing interfaces/"
                            "facades, or by splitting this class's responsibilities."
                        ),
                        metric_value=ce,
                        metric_threshold=thresholds.HIGH_EFFERENT_COUPLING,
                    )
                )

            if ca > thresholds.HIGH_AFFERENT_COUPLING:
                issues.append(
                    DebtIssue(
                        rule=self.name,
                        severity="high",
                        class_name=fqn,
                        file_path=cls.file_path,
                        message=(
                            f"'{cls.name}' is depended on by {ca} other project classes "
                            f"(threshold: {thresholds.HIGH_AFFERENT_COUPLING}), so changes "
                            f"here carry high risk of breaking other code."
                        ),
                        suggestion=(
                            "Keep this class's public API especially stable; consider "
                            "an interface so implementation details can change safely."
                        ),
                        metric_value=ca,
                        metric_threshold=thresholds.HIGH_AFFERENT_COUPLING,
                    )
                )
        return issues
