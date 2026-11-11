"""
Base class for all debt-detection rules, plus the shared AnalysisContext
that gets passed to every rule so they don't each have to recompute
project-wide data (coupling metrics, inheritance depth, etc).
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AnalysisContext:
    project: object                     # ProjectModel
    coupling_metrics: Dict[str, dict] = field(default_factory=dict)
    inheritance_depth: Dict[str, int] = field(default_factory=dict)
    python_ast_cache: dict = field(default_factory=dict)


class BaseRule:
    """
    Subclasses implement `analyze(context) -> list[DebtIssue]`.
    `name` is used as the DebtIssue.rule value and in rule_counts.
    """
    name = "BaseRule"

    def analyze(self, context: AnalysisContext) -> List:
        raise NotImplementedError
