from pathlib import Path

from reports import comparison_report


def _scan(project_name, score, issue):
    return {
        "project_name": project_name,
        "statistics": {
            "stack": "web",
            "language": "HTML, CSS, JavaScript",
            "total_files": 2,
            "parsed_files": 2,
            "failed_files": 0,
            "total_classes": 0,
            "total_interfaces": 0,
            "total_methods": 1,
            "scan_time_seconds": 0.25,
            "web_analysis": {
                "summary": {"debt_score": score},
                "metrics": {"html": {"totals": {"elements": 4}}},
            },
        },
        "classes": [],
        "debt_report": {
            "total_score": score,
            "severity_counts": {"high": int(issue is not None)},
            "issues": [issue] if issue else [],
        },
        "dependency_report": {
            "build_tool": "unknown",
            "dependencies": [],
            "outdated_dependencies": [],
        },
    }


def test_generate_comparison_report_uses_scans_and_writes_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison_report, "REPORT_OUTPUT_DIR", tmp_path)
    issue = {
        "rule_id": "WEB-HT-001",
        "rule": "MissingImageAlt",
        "severity": "high",
        "category": "ACCESSIBILITY",
        "file_path": "public/index.html",
        "line_number": 12,
        "message": "Image has no alternative text.",
    }
    baseline = _scan("Web Sample", 12, issue)
    optimized = _scan("Web Sample", 0, None)
    comparison = {
        "baseline_score": 12,
        "current_score": 0,
        "score_delta": -12,
        "improvement_percent": 100,
        "fixed_issues": [issue],
        "new_issues": [],
        "still_present": [],
        "improved_classes": [],
        "worsened_classes": [],
    }
    metadata = {
        "generated_files": ["public/index.html"],
        "selected_issues": [issue],
        "failed_issue_details": [],
        "file_comparisons": [{
            "path": "public/index.html",
            "before_code": '<img src="logo.png">',
            "after_code": '<img src="logo.png" alt="Logo">',
        }],
        "durations": {
            "original_scan_seconds": 0.25,
            "ai_generation_seconds": 1.2,
            "optimized_rescan_seconds": 0.3,
            "comparison_seconds": 0.01,
            "total_workflow_seconds": 1.76,
        },
        "source_metrics_before": {
            "files_discovered": 2, "project_size_bytes": 100,
            "lines_of_code": 10, "comment_lines": 1, "blank_lines": 2,
        },
        "source_metrics_after": {
            "files_discovered": 2, "project_size_bytes": 110,
            "lines_of_code": 11, "comment_lines": 1, "blank_lines": 2,
        },
        "provider": "test-provider",
        "model": "test-model",
        "issues_selected": 1,
        "files_processed": 1,
        "files_modified": 1,
        "failed_issues": 0,
    }

    report_path = comparison_report.generate_comparison_report(
        baseline, optimized, comparison, metadata,
    )

    assert report_path.is_file()
    assert report_path.suffix == ".pdf"
    assert report_path.read_bytes().startswith(b"%PDF-")
