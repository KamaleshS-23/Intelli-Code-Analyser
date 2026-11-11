"""Helpers for comparing technical-debt reports."""

import math
from collections import Counter, defaultdict
from numbers import Real


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        return 0
    return value if math.isfinite(value) else 0


def _score(report):
    total_score = _number(report.get("total_score"))
    if total_score or report.get("total_score") == 0:
        return total_score
    return _number(report.get("debt_score"))


def _issues(report):
    issues = report.get("issues", [])
    return issues if isinstance(issues, list) else []


def _counts(report, field):
    counts = report.get(field, {})
    if not isinstance(counts, dict):
        return {}
    return {key: _number(value) for key, value in counts.items()}


def _issue_key(issue):
    if not isinstance(issue, dict):
        return None
    return "{}|{}|{}|{}".format(
        issue.get("rule", ""),
        issue.get("class_name", ""),
        issue.get("method_name") or "",
        issue.get("file_path") or "",
    )


def _count_delta(baseline, current):
    baseline_counts = _counts(baseline, "severity_counts")
    current_counts = _counts(current, "severity_counts")
    return {
        key: current_counts.get(key, 0) - baseline_counts.get(key, 0)
        for key in dict.fromkeys((*baseline_counts, *current_counts))
    }


def _rule_delta(baseline, current):
    baseline_counts = _counts(baseline, "rule_counts")
    current_counts = _counts(current, "rule_counts")
    return {
        key: current_counts.get(key, 0) - baseline_counts.get(key, 0)
        for key in dict.fromkeys((*baseline_counts, *current_counts))
    }


def compare_debt_reports(baseline: dict, current: dict) -> dict:
    """Compare two report dictionaries and summarize debt changes."""
    baseline = baseline if isinstance(baseline, dict) else {}
    current = current if isinstance(current, dict) else {}
    baseline_issues = _issues(baseline)
    current_issues = _issues(current)

    baseline_keys = Counter(_issue_key(issue) for issue in baseline_issues)
    current_keys = Counter(_issue_key(issue) for issue in current_issues)
    fixed_keys = baseline_keys - current_keys
    new_keys = current_keys - baseline_keys

    current_by_key = defaultdict(list)
    baseline_by_key = defaultdict(list)
    for issue in current_issues:
        current_by_key[_issue_key(issue)].append(issue)
    for issue in baseline_issues:
        baseline_by_key[_issue_key(issue)].append(issue)

    fixed_issues = []
    new_issues = []
    still_present = []
    for key, count in fixed_keys.items():
        fixed_issues.extend(baseline_by_key[key][:count])
    for key, count in new_keys.items():
        new_issues.extend(current_by_key[key][:count])
    for key in baseline_keys:
        if key in current_keys:
            still_present.extend(current_by_key[key][:min(
                baseline_keys[key], current_keys[key]
            )])

    baseline_class_counts = Counter(
        issue.get("class_name", "")
        for issue in baseline_issues
        if isinstance(issue, dict)
    )
    current_class_counts = Counter(
        issue.get("class_name", "")
        for issue in current_issues
        if isinstance(issue, dict)
    )
    improved_classes = []
    worsened_classes = []
    class_names = dict.fromkeys((*baseline_class_counts, *current_class_counts))
    for class_name in class_names:
        baseline_count = baseline_class_counts[class_name]
        current_count = current_class_counts[class_name]
        if current_count < baseline_count:
            improved_classes.append(class_name)
        elif current_count > baseline_count:
            worsened_classes.append(class_name)

    baseline_score = _score(baseline)
    current_score = _score(current)
    return {
        "baseline_score": baseline_score,
        "current_score": current_score,
        "score_delta": current_score - baseline_score,
        "improvement_percent": (
            (baseline_score - current_score) / baseline_score * 100
            if baseline_score > 0 else 0
        ),
        "baseline_issue_count": len(baseline_issues),
        "current_issue_count": len(current_issues),
        "issue_count_delta": len(current_issues) - len(baseline_issues),
        "severity_delta": _count_delta(baseline, current),
        "rule_delta": _rule_delta(baseline, current),
        "fixed_issues": fixed_issues,
        "new_issues": new_issues,
        "still_present": still_present,
        "improved_classes": improved_classes,
        "worsened_classes": worsened_classes,
    }
