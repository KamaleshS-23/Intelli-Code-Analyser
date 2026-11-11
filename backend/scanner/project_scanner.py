"""
Project Scanner
----------------
The orchestrator for Phase 1. Given a project directory, it:

  1. Discovers every source file for the selected stack
  2. Parses each one into ClassModel objects
  3. Resolves internal class-to-class dependencies
  4. Builds a dependency graph + coupling metrics
  5. Packages everything into a single ProjectModel
"""

import time
from pathlib import Path

from scanner.utils.file_utils import get_source_files
from scanner.utils.logger import logger
from scanner.java_parser.java_ast_parser import parse_java_file
from scanner.python_parser.python_ast_parser import parse_python_file
from scanner.dependency_parser import build_dependency_edges
from scanner.graph_builder import build_and_analyze
from scanner.models.project_model import ProjectModel, FileParseError
from stacks import STACK_PROFILES, normalize_stack


class ProjectScanner:
    def __init__(self, project_path, stack="java"):
        self.project_path = Path(project_path)
        self.stack = normalize_stack(stack)

    def scan(self):
        start_time = time.time()
        project_name = self.project_path.name

        logger.info(f"Scanning project: {self.project_path} using stack={self.stack}")

        source_files = get_source_files(self.project_path, self.stack)
        parser_by_extension = {
            ".java": parse_java_file,
            ".py": parse_python_file,
        }

        project = ProjectModel(
            project_name=project_name,
            project_path=str(self.project_path),
        )

        for file_path in source_files:
            parser = parser_by_extension.get(file_path.suffix.lower())
            if parser is None:
                continue
            classes, error = (
                parser(file_path, str(self.project_path))
                if file_path.suffix.lower() == ".py"
                else parser(file_path)
            )

            if error:
                project.errors.append(
                    FileParseError(file_path=str(file_path), error=error)
                )
                continue

            project.classes.extend(classes)

        logger.info(f"Classes parsed: {len(project.classes)}")

        edges = build_dependency_edges(project.classes)
        project.dependencies = edges

        graph_stats = build_and_analyze(project.classes, edges)

        elapsed = round(time.time() - start_time, 3)

        project.statistics = {
            "stack": self.stack,
            "language": ", ".join(STACK_PROFILES[self.stack]["languages"]),
            "languages": STACK_PROFILES[self.stack]["languages"],
            "total_files": len(source_files),
            "parsed_files": len(source_files) - len(project.errors),
            "failed_files": len(project.errors),
            "total_classes": len(
                [c for c in project.classes if c.class_type == "class"]
            ),
            "total_interfaces": len(
                [c for c in project.classes if c.class_type == "interface"]
            ),
            "total_enums": len(
                [c for c in project.classes if c.class_type == "enum"]
            ),
            "total_methods": sum(len(c.methods) for c in project.classes),
            "total_fields": sum(len(c.fields) for c in project.classes),
            "dependency_edges": len(edges),
            "circular_dependencies": len(graph_stats["circular_dependencies"]),
            "scan_time_seconds": elapsed,
            "graph": graph_stats,
        }

        logger.info(f"Scan complete in {elapsed}s")
        return project
