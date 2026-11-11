"""
Scanner Service
---------------
Thin service layer between the API (or CLI) and the ProjectScanner.
Responsible for:
  - running a scan
  - persisting the result as JSON in scanner/output/
  - returning a plain dict, ready to serialize as a FastAPI response
"""

import json
from pathlib import Path

from scanner.project_scanner import ProjectScanner
from scanner.config import OUTPUT_DIR
from scanner.utils.logger import logger
from debt_analyzer.debt_engine import DebtEngine
from dependency_scanner.dependency_scanner_service import DependencyScannerService


class ScannerService:
    def __init__(self):
        self.scanner = None

    def scan(
        self,
        project_path,
        save_output=True,
        run_debt_analysis=True,
        run_dependency_scan=True,
        stack="java",
    ):
        self.scanner = ProjectScanner(project_path, stack=stack)
        project = self.scanner.scan()

        if run_debt_analysis:
            debt_report = DebtEngine(stack=stack).analyze(project)

        result = project.to_dict()
        if run_debt_analysis:
            result["debt_report"] = debt_report.to_dict()

        if run_dependency_scan:
            dependency_report = DependencyScannerService().scan(project_path)
            result["dependency_report"] = dependency_report.to_dict()

        if save_output:
            output_path = self._save_result(project.project_name, result)
            result["_output_file"] = str(output_path)

        return result

    def _save_result(self, project_name, result_dict):
        safe_name = project_name.replace(" ", "_")
        output_path = Path(OUTPUT_DIR) / f"{safe_name}_scan.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2)

        logger.info(f"Scan result written to {output_path}")
        return output_path
