"""
Debt Engine
-----------
The single entry point for Phase 2 (Technical Debt Detection).

Given the ProjectModel produced by Phase 1's ProjectScanner, this:
  1. Builds an AnalysisContext (coupling metrics already computed by
     graph_builder, plus inheritance depth computed here from the
     "extends" edges already resolved by dependency_parser)
  2. Runs every registered rule against that context
  3. Scores the combined issues into a DebtReport
"""

from pathlib import Path

from debt_analyzer.rules.base_rule import AnalysisContext
from debt_analyzer.rules.java.java_rules import (
    LongMethodRule,
    ExcessiveParameterListRule,
    GodClassRule,
    LargeClassRule,
    HighCouplingRule,
    DeepInheritanceRule,
    DuplicateCodeRule,
    UnusedVariableRule,
    DeadMethodRule,
    HighCyclomaticComplexityRule,
    DeepNestingRule,
    EmptyCatchBlockRule,
    MagicNumberRule,
    HardcodedCredentialsRule,
    FeatureEnvyRule,
    CircularDependencyRule,
    StringConcatenationInLoopRule,
    UnclosedResourceRule,
    MutableStaticFieldRule,
    GenericExceptionHandlingRule,
    MissingJavadocRule,
)
from debt_analyzer.rules.python.python_rules import (
    PythonLongMethodRule,
    PythonHighCyclomaticComplexityRule,
    PythonDeepNestingRule,
    PythonMagicNumberRule,
    PythonUnusedVariableRule,
    PythonHardcodedCredentialsRule,
    PythonGenericExceptionHandlingRule,
    PythonStringConcatenationInLoopRule,
    PythonDeadMethodRule,
    PythonPossibleRefactorIssueRule,
)
from debt_analyzer.rules.python.ast_rules import PYTHON_AST_RULES
from debt_analyzer.rules.stack_rules import get_web_stack_rules
from debt_analyzer.rules.django import DjangoProjectAnalysisRule
from debt_analyzer.rules.nodejs import NodeProjectAnalysisRule
from debt_analyzer.scoring import score_report
from debt_analyzer.web_metrics import update_web_summary
from scanner.utils.logger import logger


DEFAULT_RULES = [
    LongMethodRule(),
    ExcessiveParameterListRule(),
    GodClassRule(),
    LargeClassRule(),
    HighCouplingRule(),
    DeepInheritanceRule(),
    DuplicateCodeRule(),
    UnusedVariableRule(),
    DeadMethodRule(),
    HighCyclomaticComplexityRule(),
    DeepNestingRule(),
    EmptyCatchBlockRule(),
    MagicNumberRule(),
    HardcodedCredentialsRule(),
    FeatureEnvyRule(),
    CircularDependencyRule(),
    StringConcatenationInLoopRule(),
    UnclosedResourceRule(),
    MutableStaticFieldRule(),
    GenericExceptionHandlingRule(),
    MissingJavadocRule(),
]

PYTHON_RULES = [
    PythonLongMethodRule(),
    PythonHighCyclomaticComplexityRule(),
    PythonDeepNestingRule(),
    PythonMagicNumberRule(),
    PythonUnusedVariableRule(),
    PythonHardcodedCredentialsRule(),
    PythonGenericExceptionHandlingRule(),
    PythonStringConcatenationInLoopRule(),
    PythonDeadMethodRule(),
    PythonPossibleRefactorIssueRule(),
] + PYTHON_AST_RULES

DJANGO_RULES = PYTHON_RULES + get_web_stack_rules("django") + [
    DjangoProjectAnalysisRule()
]
WEB_RULES = get_web_stack_rules("web")
NODEJS_RULES = get_web_stack_rules("nodejs") + [
    NodeProjectAnalysisRule()
]


def get_rules_for_stack(stack="java"):
    normalized = (stack or "java").lower()
    return {
        "python": PYTHON_RULES,
        "web": WEB_RULES,
        "django": DJANGO_RULES,
        "nodejs": NODEJS_RULES,
    }.get(normalized, DEFAULT_RULES)


def _compute_inheritance_depth(project):
    """
    Depth-of-Inheritance-Tree (DIT), computed only from "extends" edges that
    were already resolved against project classes by dependency_parser.py.
    External/library base classes are treated as depth 0 (we can't see how
    deep they go, and it's not actionable debt on this codebase anyway).
    """
    parent_map = {}
    for edge in project.dependencies:
        if edge.get("type") == "extends" and edge["from"] not in parent_map:
            parent_map[edge["from"]] = edge["to"]

    depth_cache = {}

    def depth_of(fqn, visited):
        if fqn in depth_cache:
            return depth_cache[fqn]
        parent = parent_map.get(fqn)
        if not parent or parent in visited:
            depth_cache[fqn] = 0
            return 0
        result = 1 + depth_of(parent, visited | {fqn})
        depth_cache[fqn] = result
        return result

    all_fqns = {c.fully_qualified_name for c in project.classes}
    return {fqn: depth_of(fqn, frozenset()) for fqn in all_fqns}


class DebtEngine:
    def __init__(self, rules=None, stack="java"):
        self.stack = (stack or "java").lower()
        self.rules = rules if rules is not None else get_rules_for_stack(self.stack)

    def analyze(self, project):
        coupling_metrics = (
            project.statistics.get("graph", {}).get("coupling_metrics", {})
        )
        inheritance_depth = _compute_inheritance_depth(project)

        context = AnalysisContext(
            project=project,
            coupling_metrics=coupling_metrics,
            inheritance_depth=inheritance_depth,
        )

        all_issues = []
        for rule in self.rules:
            rule_issues = rule.analyze(context)
            logger.info(f"{rule.name}: {len(rule_issues)} issue(s) found")
            all_issues.extend(rule_issues)

        web_analysis = project.statistics.get("web_analysis")
        if web_analysis:
            web_extensions = {".html", ".htm", ".css", ".js", ".jsx", ".mjs", ".cjs"}
            web_issues = [
                issue for issue in all_issues
                if Path(issue.file_path).suffix.lower() in web_extensions
            ]
            update_web_summary(web_analysis, web_issues)

        report = score_report(project.project_name, all_issues)
        logger.info(
            f"Debt analysis complete: {len(all_issues)} total issues, "
            f"score={report.total_score}"
        )
        return report
