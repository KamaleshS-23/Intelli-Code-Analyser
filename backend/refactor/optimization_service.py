"""Generate, rescan, and package optimized project copies."""

import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

from debt_analyzer.comparison import compare_debt_reports
from ai_assistant.config import get_ai_settings
from scanner.config import IGNORE_DIRS, OUTPUT_DIR
from scanner.scanner_service import ScannerService
from scanner.utils.logger import logger
from scanner.utils.file_utils import get_source_files

from .code_generator import generate_optimized_code


_SUPPORTED_STACKS = {"java", "python", "web", "django", "nodejs"}
_HIGH_SEVERITIES = {"critical", "high"}


def _issue_key(issue: dict) -> str:
    return "{}|{}|{}|{}".format(
        issue.get("rule", ""),
        issue.get("class_name", ""),
        issue.get("method_name") or "",
        issue.get("file_path") or "",
    )


def _issue_file_path(project_root: Path, issue: dict) -> tuple[Path, Path]:
    raw_path = issue.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("Issue does not contain a valid file_path.")

    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        try:
            relative_path = relative_path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError("Issue file_path is outside the project.") from exc

    source_path = project_root / relative_path
    resolved_root = project_root.resolve()
    resolved_source = source_path.resolve()
    try:
        normalized_relative_path = resolved_source.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Issue file_path resolves outside the project.") from exc

    if not resolved_source.is_file():
        raise FileNotFoundError(f"Issue file does not exist: {raw_path}")
    return resolved_source, normalized_relative_path


def _select_issues(
    issues: list,
    issue_keys: list[str] | None,
    max_issues: int,
    select_all: bool,
) -> list[dict]:
    valid_issues = [issue for issue in issues if isinstance(issue, dict)]
    if select_all:
        return valid_issues
    if issue_keys is not None:
        selected_keys = set(issue_keys)
        return [issue for issue in valid_issues if _issue_key(issue) in selected_keys]
    return [
        issue
        for issue in valid_issues
        if str(issue.get("severity", "")).lower() in _HIGH_SEVERITIES
    ][:max(0, max_issues)]


def _summary(debt_report: dict) -> dict:
    issues = debt_report.get("issues")
    if not isinstance(issues, list):
        issues = []
    total_score = debt_report.get("total_score")
    if total_score is None:
        total_score = debt_report.get("debt_score", 0)
    return {
        "total_score": total_score,
        "issue_count": len(issues),
        "severity_counts": debt_report.get("severity_counts") or {},
        "rule_counts": debt_report.get("rule_counts") or {},
    }


def _report_with_relative_issue_paths(
    debt_report: dict, project_root: Path
) -> dict:
    report = dict(debt_report)
    issues = debt_report.get("issues")
    if not isinstance(issues, list):
        return report

    relative_issues = []
    root = project_root.resolve()
    for issue in issues:
        if not isinstance(issue, dict):
            relative_issues.append(issue)
            continue
        normalized_issue = dict(issue)
        raw_file_path = issue.get("file_path")
        if isinstance(raw_file_path, str) and raw_file_path:
            file_path = Path(raw_file_path)
            if not file_path.is_absolute():
                file_path = root / file_path
            try:
                normalized_issue["file_path"] = file_path.resolve().relative_to(
                    root
                ).as_posix()
            except (OSError, ValueError):
                pass
        relative_issues.append(normalized_issue)
    report["issues"] = relative_issues
    return report


def _source_metrics(project_root: Path, stack: str) -> dict:
    source_files = get_source_files(project_root, stack)
    total_bytes = 0
    for file_path in project_root.rglob("*"):
        if (
            file_path.is_file()
            and not file_path.is_symlink()
            and not any(part in IGNORE_DIRS for part in file_path.relative_to(project_root).parts)
        ):
            try:
                total_bytes += file_path.stat().st_size
            except OSError:
                continue
    code_lines = 0
    comment_lines = 0
    blank_lines = 0
    read_failures = 0
    comment_prefixes = {
        ".py": ("#",),
        ".html": ("<!--",),
        ".htm": ("<!--",),
        ".css": ("/*", "*", "*/"),
        ".js": ("//", "/*", "*", "*/"),
        ".jsx": ("//", "/*", "*", "*/"),
        ".ts": ("//", "/*", "*", "*/"),
        ".tsx": ("//", "/*", "*", "*/"),
        ".java": ("//", "/*", "*", "*/"),
    }
    for source_file in source_files:
        try:
            lines = source_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            read_failures += 1
            continue
        prefixes = comment_prefixes.get(source_file.suffix.lower(), ())
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif prefixes and stripped.startswith(prefixes):
                comment_lines += 1
            else:
                code_lines += 1
    return {
        "files_discovered": len(source_files),
        "project_size_bytes": total_bytes,
        "lines_of_code": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "read_failures": read_failures,
    }


class OptimizationService:
    def generate_optimized_project(
        self,
        baseline_scan: dict,
        project_path: str,
        issue_keys: list[str] | None = None,
        stack: str = "java",
        max_issues: int = 20,
        select_all: bool = False,
    ) -> dict:
        """Create an optimized project copy, rescan it, and produce a zip."""
        if stack not in _SUPPORTED_STACKS:
            raise ValueError(
                f"Unsupported stack '{stack}'. Supported stacks: "
                f"{', '.join(sorted(_SUPPORTED_STACKS))}."
            )
        if not isinstance(baseline_scan, dict):
            raise TypeError("baseline_scan must be a dict.")

        project_root = Path(project_path).resolve()
        if not project_root.is_dir():
            raise NotADirectoryError(f"Project directory does not exist: {project_path}")

        baseline_debt_report = baseline_scan.get("debt_report")
        if not isinstance(baseline_debt_report, dict):
            baseline_debt_report = {}
        baseline_issues = baseline_debt_report.get("issues")
        if not isinstance(baseline_issues, list):
            baseline_issues = []
        selected_issues = _select_issues(
            baseline_issues, issue_keys, max_issues, select_all
        )
        workflow_started = time.perf_counter()
        baseline_source_metrics = _source_metrics(project_root, stack)

        safe_project_name = project_root.name or "project"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_root = Path(OUTPUT_DIR) / "optimized"
        resolved_output_root = output_root.resolve()
        try:
            resolved_output_root.relative_to(project_root)
        except ValueError:
            pass
        else:
            raise ValueError(
                "Optimized output directory cannot be inside the source project."
            )
        output_root.mkdir(parents=True, exist_ok=True)
        optimized_project_path = output_root / f"{safe_project_name}_{timestamp}"
        download_zip_path = output_root / f"{safe_project_name}_{timestamp}.zip"

        shutil.copytree(project_root, optimized_project_path, symlinks=True)

        generated_files = []
        original_file_contents = {}
        optimized_file_contents = {}
        failed_issues = []
        generated_file_set = set()
        generation_started = time.perf_counter()
        for issue in selected_issues:
            try:
                source_path, relative_path = _issue_file_path(project_root, issue)
                copied_path = optimized_project_path / relative_path
                relative_name = relative_path.as_posix()
                source_code = source_path.read_text(encoding="utf-8")
                original_file_contents.setdefault(relative_name, source_code)
                current_code = (
                    copied_path.read_text(encoding="utf-8")
                    if relative_name in generated_file_set
                    else source_code
                )
                optimized_code = generate_optimized_code(
                    current_code,
                    issue,
                    language=stack,
                )
                copied_path.write_text(optimized_code, encoding="utf-8")
                optimized_file_contents[relative_name] = optimized_code
                if relative_name not in generated_file_set:
                    generated_file_set.add(relative_name)
                    generated_files.append(relative_name)
            except Exception as exc:
                logger.exception(
                    f"Failed to optimize issue {_issue_key(issue)}: {exc}"
                )
                failed_issues.append({"issue": issue, "error": str(exc)})
        generation_duration = time.perf_counter() - generation_started

        rescan_started = time.perf_counter()
        optimized_scan = ScannerService().scan(
            str(optimized_project_path),
            save_output=True,
            stack=stack,
        )
        rescan_duration = time.perf_counter() - rescan_started
        optimized_debt_report = optimized_scan.get("debt_report")
        if not isinstance(optimized_debt_report, dict):
            optimized_debt_report = {}

        with zipfile.ZipFile(
            download_zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for file_path in optimized_project_path.rglob("*"):
                if file_path.is_dir() and not file_path.is_symlink():
                    archive.writestr(
                        file_path.relative_to(
                            optimized_project_path.parent
                        ).as_posix().rstrip("/") + "/",
                        "",
                    )
                elif file_path.is_file() and not file_path.is_symlink():
                    archive.write(
                        file_path,
                        file_path.relative_to(
                            optimized_project_path.parent
                        ).as_posix(),
                    )

        comparison_started = time.perf_counter()
        comparison = compare_debt_reports(
            _report_with_relative_issue_paths(
                baseline_debt_report, project_root
            ),
            _report_with_relative_issue_paths(
                optimized_debt_report, optimized_project_path
            ),
        )
        comparison_duration = time.perf_counter() - comparison_started
        ai_settings = get_ai_settings()
        code_generation_provider = ai_settings.code_generation_provider
        if code_generation_provider in {"", "default"}:
            code_generation_provider = (
                "gemini" if ai_settings.has_gemini else ai_settings.provider
            )
        code_generation_fallback_provider = (
            ai_settings.provider
            if code_generation_provider == "gemini"
            and ai_settings.provider in {"groq", "openai", "openai_compatible"}
            and ai_settings.openai_api_key
            else None
        )
        code_generation_model = (
            ai_settings.gemini_model
            if code_generation_provider == "gemini"
            else ai_settings.model
        )
        original_scan_duration = (
            baseline_scan.get("statistics", {}).get("scan_time_seconds")
            if isinstance(baseline_scan.get("statistics"), dict)
            else None
        )
        logger.info(
            f"Optimized project created at {optimized_project_path}; "
            f"{len(generated_files)} file(s) generated, "
            f"{len(failed_issues)} issue(s) failed."
        )
        file_comparisons = [
            {
                "path": relative_name,
                "before_code": original_file_contents[relative_name],
                "after_code": optimized_file_contents[relative_name],
            }
            for relative_name in generated_files
        ]
        optimized_source_metrics = _source_metrics(optimized_project_path, stack)
        total_workflow_duration = (
            time.perf_counter() - workflow_started
            + (original_scan_duration if isinstance(original_scan_duration, (int, float)) else 0)
        )
        optimization_meta = {
            "provider": code_generation_provider,
            "fallback_provider": code_generation_fallback_provider,
            "model": code_generation_model,
            "issues_selected": len(selected_issues),
            "files_processed": len(set(generated_files) | {
                str(item.get("issue", {}).get("file_path", ""))
                for item in failed_issues
                if isinstance(item.get("issue"), dict)
            }),
            "files_modified": len(generated_files),
            "failed_issues": len(failed_issues),
            "durations": {
                "original_scan_seconds": original_scan_duration,
                "ai_generation_seconds": round(generation_duration, 3),
                "optimized_rescan_seconds": round(rescan_duration, 3),
                "comparison_seconds": round(comparison_duration, 3),
                "total_workflow_seconds": round(total_workflow_duration, 3),
            },
            "source_metrics_before": baseline_source_metrics,
            "source_metrics_after": optimized_source_metrics,
            "download_zip_path": str(download_zip_path),
        }
        return {
            "selected_issues": selected_issues,
            "generated_files": generated_files,
            "file_comparisons": file_comparisons,
            "failed_issues": failed_issues,
            "optimized_scan": optimized_scan,
            "optimization_meta": optimization_meta,
            "optimized_project_path": str(optimized_project_path),
            "download_zip_path": str(download_zip_path),
            "baseline_summary": _summary(baseline_debt_report),
            "optimized_summary": _summary(optimized_debt_report),
            "comparison": comparison,
        }
