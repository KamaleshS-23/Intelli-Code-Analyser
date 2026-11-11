from debt_analyzer.rules.python.python_rules import (
    PythonPossibleRefactorIssueRule,
    PythonLongMethodRule,
)
from debt_analyzer.rules.python import __all__ as python_all


def test_python_rule_registry_contains_refactor_rule():
    assert PythonPossibleRefactorIssueRule.__name__ == "PythonPossibleRefactorIssueRule"
    assert "PythonPossibleRefactorIssueRule" in python_all
    assert "PythonLongMethodRule" in python_all
