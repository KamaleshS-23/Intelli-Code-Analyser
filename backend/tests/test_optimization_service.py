import zipfile
from pathlib import Path

import pytest

from refactor import optimization_service
from refactor.optimization_service import (
    OptimizationService,
    _report_with_relative_issue_paths,
)
from debt_analyzer.comparison import compare_debt_reports


def _issue(file_path, severity="high", rule="LongMethod", method="run"):
    return {
        "rule": rule,
        "class_name": "Example",
        "method_name": method,
        "file_path": file_path,
        "severity": severity,
        "message": "Method needs refactoring.",
        "suggestion": "Extract a helper.",
    }


def _key(issue):
    return "{}|{}|{}|{}".format(
        issue.get("rule", ""),
        issue.get("class_name", ""),
        issue.get("method_name") or "",
        issue.get("file_path") or "",
    )


def test_generate_optimized_project_copies_generates_scans_and_zips(
    tmp_path, monkeypatch
):
    project = tmp_path / "source-project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "Example.java").write_text("original", encoding="utf-8")
    (project / "README.md").write_text("keep me", encoding="utf-8")
    issue = _issue("src/Example.java")
    output = tmp_path / "output"
    monkeypatch.setattr(optimization_service, "OUTPUT_DIR", output)

    def fake_generate(code, selected_issue, language):
        assert code == "original"
        assert selected_issue == issue
        assert language == "python"
        return "optimized"

    class FakeScannerService:
        def scan(self, project_path, save_output, stack):
            assert save_output is True
            assert stack == "python"
            assert Path(project_path, "src", "Example.java").read_text(
                encoding="utf-8"
            ) == "optimized"
            return {
                "debt_report": {
                    "total_score": 2,
                    "issues": [],
                    "severity_counts": {},
                    "rule_counts": {},
                }
            }

    monkeypatch.setattr(optimization_service, "generate_optimized_code", fake_generate)
    monkeypatch.setattr(optimization_service, "ScannerService", FakeScannerService)

    result = OptimizationService().generate_optimized_project(
        {
            "debt_report": {
                "total_score": 5,
                "issues": [issue],
                "severity_counts": {"high": 1},
                "rule_counts": {"LongMethod": 1},
            }
        },
        str(project),
        stack="python",
    )

    optimized_project = Path(result["optimized_project_path"])
    archive_path = Path(result["download_zip_path"])
    assert result["generated_files"] == ["src/Example.java"]
    assert result["optimized_scan"]["debt_report"]["total_score"] == 2
    assert result["optimization_meta"]["issues_selected"] == 1
    assert result["optimization_meta"]["files_modified"] == 1
    assert result["optimization_meta"]["source_metrics_before"]["files_discovered"] == 0
    assert result["optimization_meta"]["durations"]["ai_generation_seconds"] >= 0
    assert result["file_comparisons"] == [{
        "path": "src/Example.java",
        "before_code": "original",
        "after_code": "optimized",
    }]
    assert result["failed_issues"] == []
    assert result["baseline_summary"]["issue_count"] == 1
    assert result["optimized_summary"]["issue_count"] == 0
    assert result["comparison"]["improvement_percent"] == 60
    assert (optimized_project / "README.md").read_text(encoding="utf-8") == "keep me"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        assert any(name.endswith("/src/Example.java") for name in archive.namelist())


def test_generate_optimized_project_continues_after_issue_failure(
    tmp_path, monkeypatch
):
    project = tmp_path / "source-project"
    project.mkdir()
    (project / "good.py").write_text("good", encoding="utf-8")
    (project / "missing.py").write_text("missing", encoding="utf-8")
    good_issue = _issue("good.py")
    bad_issue = _issue("missing.py", rule="GodClass")
    output = tmp_path / "output"
    monkeypatch.setattr(optimization_service, "OUTPUT_DIR", output)

    def fake_generate(code, selected_issue, language):
        if selected_issue == bad_issue:
            raise RuntimeError("provider unavailable")
        return "optimized good"

    class FakeScannerService:
        def scan(self, project_path, save_output, stack):
            assert Path(project_path, "good.py").read_text(encoding="utf-8") == "optimized good"
            assert Path(project_path, "missing.py").read_text(encoding="utf-8") == "missing"
            return {"debt_report": {"issues": []}}

    monkeypatch.setattr(optimization_service, "generate_optimized_code", fake_generate)
    monkeypatch.setattr(optimization_service, "ScannerService", FakeScannerService)

    result = OptimizationService().generate_optimized_project(
        {"debt_report": {"issues": [good_issue, bad_issue]}},
        str(project),
        select_all=True,
    )

    assert result["generated_files"] == ["good.py"]
    assert result["file_comparisons"] == [{
        "path": "good.py",
        "before_code": "good",
        "after_code": "optimized good",
    }]
    assert len(result["failed_issues"]) == 1
    assert result["failed_issues"][0]["issue"] == bad_issue
    assert "provider unavailable" in result["failed_issues"][0]["error"]


def test_generate_optimized_project_selects_issue_keys_and_defaults_to_high(
    tmp_path, monkeypatch
):
    project = tmp_path / "source-project"
    project.mkdir()
    issues = [
        _issue("critical.py", severity="critical"),
        _issue("high.py", severity="high"),
        _issue("medium.py", severity="medium"),
    ]
    for issue in issues:
        (project / issue["file_path"]).write_text(issue["file_path"], encoding="utf-8")
    monkeypatch.setattr(optimization_service, "OUTPUT_DIR", tmp_path / "output")

    class FakeScannerService:
        def scan(self, project_path, save_output, stack):
            return {"debt_report": {"issues": []}}

    monkeypatch.setattr(optimization_service, "ScannerService", FakeScannerService)
    monkeypatch.setattr(
        optimization_service,
        "generate_optimized_code",
        lambda code, issue, language: code,
    )

    default_result = OptimizationService().generate_optimized_project(
        {"debt_report": {"issues": issues}},
        str(project),
        max_issues=1,
    )
    assert default_result["selected_issues"] == [issues[0]]

    keyed_result = OptimizationService().generate_optimized_project(
        {"debt_report": {"issues": issues}},
        str(project),
        issue_keys=[_key(issues[1])],
    )
    assert keyed_result["selected_issues"] == [issues[1]]


def test_generate_optimized_project_rejects_issue_paths_outside_project(
    tmp_path, monkeypatch
):
    project = tmp_path / "source-project"
    project.mkdir()
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("outside", encoding="utf-8")
    monkeypatch.setattr(optimization_service, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(
        optimization_service,
        "ScannerService",
        lambda: type("FakeScanner", (), {"scan": lambda self, *args, **kwargs: {"debt_report": {"issues": []}}})(),
    )

    result = OptimizationService().generate_optimized_project(
        {"debt_report": {"issues": [_issue("../outside.py")]}},
        str(project),
        select_all=True,
    )

    assert result["generated_files"] == []
    assert len(result["failed_issues"]) == 1
    assert "outside the project" in result["failed_issues"][0]["error"]


def test_comparison_normalizes_source_and_optimized_absolute_paths(tmp_path):
    source_root = tmp_path / "source-project"
    optimized_root = tmp_path / "optimized-project"
    baseline_issue = _issue(str(source_root / "src" / "Example.java"))
    current_issue = _issue(str(optimized_root / "src" / "Example.java"))

    baseline = _report_with_relative_issue_paths(
        {"issues": [baseline_issue]},
        source_root,
    )
    current = _report_with_relative_issue_paths(
        {"issues": [current_issue]},
        optimized_root,
    )
    comparison = compare_debt_reports(baseline, current)

    assert baseline["issues"][0]["file_path"] == "src/Example.java"
    assert current["issues"][0]["file_path"] == "src/Example.java"
    assert baseline_issue["file_path"] != current_issue["file_path"]
    assert comparison["fixed_issues"] == []
    assert comparison["new_issues"] == []
    assert comparison["still_present"] == [current["issues"][0]]
