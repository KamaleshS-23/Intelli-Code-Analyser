"""
Data models for the technical-debt analyzer output.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class DebtIssue:
    rule: str                      # e.g. "LongMethod", "GodClass"
    severity: str                  # low | medium | high | critical
    class_name: str                # fully qualified class name
    file_path: str = ""
    method_name: Optional[str] = None
    line_number: int = 0
    message: str = ""
    suggestion: str = ""
    metric_value: Optional[float] = None
    metric_threshold: Optional[float] = None
    rule_id: str = ""
    category: str = ""
    language: str = ""
    column: int = 0
    code_snippet: str = ""
    refactoring_pattern: str = ""
    estimated_fix_minutes: int = 0
    threshold: Optional[float] = None
    layer: str = ""
    django_version_aware: bool = False
    node_version_aware: bool = False
    framework: Optional[str] = None


@dataclass
class ClassScore:
    class_name: str
    score: int
    issue_count: int


@dataclass
class DebtReport:
    project_name: str
    issues: List[DebtIssue] = field(default_factory=list)
    total_score: int = 0
    severity_counts: dict = field(default_factory=dict)
    rule_counts: dict = field(default_factory=dict)
    top_offenders: List[ClassScore] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
