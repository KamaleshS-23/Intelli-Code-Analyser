from debt_analyzer.comparison import compare_debt_reports


def test_compare_debt_reports_matches_issues_by_file_path():
    baseline_issue = {
        "rule": "LongMethod",
        "class_name": "Example",
        "method_name": "run",
        "file_path": "src/old.py",
    }
    current_issue = {
        "rule": "LongMethod",
        "class_name": "Example",
        "method_name": "run",
        "file_path": "src/new.py",
    }

    comparison = compare_debt_reports(
        {"issues": [baseline_issue]},
        {"issues": [current_issue]},
    )

    assert comparison["fixed_issues"] == [baseline_issue]
    assert comparison["new_issues"] == [current_issue]
    assert comparison["still_present"] == []


def test_compare_debt_reports_handles_missing_values_and_debt_score():
    comparison = compare_debt_reports(
        {
            "debt_score": 8,
            "issues": [{"rule": "LongMethod", "class_name": "Example"}],
        },
        {"total_score": 0, "issues": []},
    )

    assert comparison["baseline_score"] == 8
    assert comparison["current_score"] == 0
    assert comparison["improvement_percent"] == 100
    assert comparison["baseline_issue_count"] == 1
    assert comparison["current_issue_count"] == 0
    assert comparison["severity_delta"] == {}
    assert comparison["rule_delta"] == {}
    assert comparison["fixed_issues"] == [
        {"rule": "LongMethod", "class_name": "Example"}
    ]
