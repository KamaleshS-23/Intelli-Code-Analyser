import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from api import main
from reports import comparison_report
from refactor import optimization_service


client = TestClient(main.app)


def test_upload_scan_keeps_persistent_project_copy(tmp_path, monkeypatch):
    temp_uploads = tmp_path / "temp"
    workdirs = tmp_path / "workdir"
    temp_uploads.mkdir()
    workdirs.mkdir()
    monkeypatch.setattr(main, "UPLOAD_TEMP_DIR", temp_uploads)
    monkeypatch.setattr(main, "UPLOAD_WORKDIR", workdirs)
    monkeypatch.setattr(main.ai_orchestrator, "register_scan", lambda result: None)
    monkeypatch.setattr(main, "_persist_scan", lambda *args: None)

    def fake_scan(project_path, save_output, stack):
        project_file = Path(project_path) / "main.py"
        assert project_file.read_text(encoding="utf-8") == "print('persisted')"
        assert save_output is True
        assert stack == "python"
        return {
            "project_name": Path(project_path).name,
            "project_path": str(project_path),
            "debt_report": {"issues": []},
        }

    monkeypatch.setattr(main.scanner_service, "scan", fake_scan)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("uploaded-project/main.py", "print('persisted')")

    response = client.post(
        "/api/scan-upload",
        data={"stack": "java"},
        files={"file": ("project.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stack"] == "python"
    workdir_path = Path(data["workdir_path"])
    assert workdir_path.parent == workdirs
    assert (workdir_path / "main.py").read_text(encoding="utf-8") == "print('persisted')"
    assert data["debt_report"] == {"issues": []}
    assert not list(temp_uploads.iterdir())


def test_scan_path_returns_detected_stack(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("print('detected')", encoding="utf-8")
    monkeypatch.setattr(
        main.scanner_service,
        "scan",
        lambda project_path, save_output, stack: {
            "project_name": Path(project_path).name,
            "project_path": project_path,
            "statistics": {"stack": stack},
            "debt_report": {"issues": []},
        },
    )
    monkeypatch.setattr(main.ai_orchestrator, "register_scan", lambda result: None)
    monkeypatch.setattr(main, "_persist_scan", lambda *args: None)

    response = client.post(
        "/api/scan-path",
        params={"path": str(tmp_path), "stack": "java"},
    )

    assert response.status_code == 200
    assert response.json()["stack"] == "python"
    assert response.json()["statistics"]["stack"] == "python"


def test_compare_reports_endpoint_returns_comparison():
    response = client.post(
        "/api/compare/reports",
        json={
            "baseline_debt_report": {
                "total_score": 4,
                "issues": [{"rule": "LongMethod", "class_name": "Example"}],
            },
            "current_debt_report": {"total_score": 0, "issues": []},
        },
    )

    assert response.status_code == 200
    assert response.json()["score_delta"] == -4
    assert response.json()["fixed_issues"] == [
        {"rule": "LongMethod", "class_name": "Example"}
    ]


def test_comparison_report_endpoint_returns_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison_report, "REPORT_OUTPUT_DIR", tmp_path)
    baseline_scan = {
        "project_name": "API Report",
        "statistics": {"stack": "python", "total_files": 0, "parsed_files": 0},
        "debt_report": {"total_score": 0, "issues": []},
    }
    response = client.post(
        "/api/report/comparison",
        json={
            "baseline_scan": baseline_scan,
            "optimized_scan": baseline_scan,
            "comparison": {
                "baseline_score": 0,
                "current_score": 0,
                "fixed_issues": [],
                "new_issues": [],
                "still_present": [],
            },
            "optimization_meta": {
                "generated_files": [],
                "durations": {},
            },
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_generate_endpoint_validates_inputs(tmp_path):
    response = client.post(
        "/api/refactor/generate",
        json={
            "project_path": str(tmp_path),
            "baseline_scan": {"debt_report": {"issues": []}},
            "stack": "unsupported",
        },
    )

    assert response.status_code == 400
    assert "Unsupported stack" in response.json()["detail"]


def test_generate_endpoint_returns_download_details(tmp_path, monkeypatch):
    project = tmp_path / "source"
    project.mkdir()
    download_path = tmp_path / "optimized.zip"

    class FakeOptimizationService:
        def generate_optimized_project(self, **kwargs):
            assert kwargs["project_path"] == str(project)
            assert kwargs["stack"] == "python"
            return {
                "comparison": {"score_delta": -1},
                "download_zip_path": str(download_path),
            }

    monkeypatch.setattr(main, "OptimizationService", FakeOptimizationService)
    response = client.post(
        "/api/refactor/generate",
        json={
            "project_path": str(project),
            "baseline_scan": {"debt_report": {"issues": []}},
            "stack": "python",
        },
    )

    assert response.status_code == 200
    assert response.json()["comparison"] == {"score_delta": -1}
    assert response.json()["download_filename"] == "optimized.zip"
    assert response.json()["download_url"] == "/api/refactor/download?file=optimized.zip"


def test_download_endpoint_serves_only_optimized_zip_files(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    optimized_dir = backend_dir / "scanner" / "output" / "optimized"
    optimized_dir.mkdir(parents=True)
    archive_path = optimized_dir / "project.zip"
    archive_path.write_bytes(b"zip content")
    monkeypatch.setattr(main, "BACKEND_DIR", backend_dir)

    response = client.get(
        "/api/refactor/download",
        params={"file": archive_path.name},
    )
    traversal_response = client.get(
        "/api/refactor/download",
        params={"file": "..\\outside.zip"},
    )

    assert response.status_code == 200
    assert response.content == b"zip content"
    assert response.headers["content-disposition"].endswith(
        'filename="project.zip"'
    )
    assert traversal_response.status_code == 400


def test_download_endpoint_rejects_non_zip_and_missing_files(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    optimized_dir = backend_dir / "scanner" / "output" / "optimized"
    optimized_dir.mkdir(parents=True)
    (optimized_dir / "report.txt").write_text("not a zip", encoding="utf-8")
    monkeypatch.setattr(main, "BACKEND_DIR", backend_dir)

    response = client.get(
        "/api/refactor/download",
        params={"file": "report.txt"},
    )

    assert response.status_code == 404


def test_generate_and_download_optimized_project_end_to_end(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    output_dir = backend_dir / "scanner" / "output"
    source_project = tmp_path / "sample-java"
    (source_project / "src" / "main" / "java").mkdir(parents=True)
    (source_project / "src" / "main" / "java" / "Example.java").write_text(
        "class Example { void run() { old(); } }",
        encoding="utf-8",
    )
    (source_project / "README.md").write_text("Project instructions", encoding="utf-8")
    (source_project / "empty-assets").mkdir()

    monkeypatch.setattr(main, "BACKEND_DIR", backend_dir)
    monkeypatch.setattr(optimization_service, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        optimization_service,
        "generate_optimized_code",
        lambda code, issue, language: "class Example { void run() { optimized(); } }",
    )

    class FakeScannerService:
        def scan(self, project_path, save_output, stack):
            return {
                "debt_report": {
                    "total_score": 0,
                    "issues": [],
                    "severity_counts": {},
                    "rule_counts": {},
                }
            }

    monkeypatch.setattr(optimization_service, "ScannerService", FakeScannerService)
    issue = {
        "rule": "LongMethod",
        "class_name": "Example",
        "method_name": "run",
        "file_path": "src/main/java/Example.java",
        "severity": "high",
        "message": "Method is long.",
        "suggestion": "Extract a helper.",
    }

    generate_response = client.post(
        "/api/refactor/generate",
        json={
            "project_path": str(source_project),
            "baseline_scan": {
                "debt_report": {
                    "total_score": 5,
                    "issues": [issue],
                    "severity_counts": {"high": 1},
                    "rule_counts": {"LongMethod": 1},
                }
            },
            "issue_keys": [
                "LongMethod|Example|run|src/main/java/Example.java"
            ],
            "stack": "java",
        },
    )

    assert generate_response.status_code == 200
    response_data = generate_response.json()
    download_response = client.get(response_data["download_url"])

    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download_response.content)) as archive:
        project_prefix = f"{Path(response_data['optimized_project_path']).name}/"
        assert f"{project_prefix}README.md" in archive.namelist()
        assert f"{project_prefix}empty-assets/" in archive.namelist()
        optimized_source = archive.read(
            f"{project_prefix}src/main/java/Example.java"
        ).decode("utf-8")
        assert "optimized()" in optimized_source
