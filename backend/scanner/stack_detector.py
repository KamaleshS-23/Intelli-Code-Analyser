"""Detect the primary technology stack from a project directory."""

import os
from pathlib import Path

from scanner.config import IGNORE_DIRS


_WEB_EXTENSIONS = {".html", ".htm", ".css", ".js", ".jsx", ".mjs"}
_NODE_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def detect_stack(project_path: str) -> str:
    """Return the most specific supported stack detected in a project."""
    root = Path(project_path)
    if not root.is_dir():
        raise NotADirectoryError(f"Project directory does not exist: {project_path}")

    has_java = False
    has_python = False
    has_web = False
    has_package_json = False
    has_node_source = False
    has_manage_py = False
    django_settings = []
    has_templates = False

    for current_dir, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name not in IGNORE_DIRS]
        current_path = Path(current_dir)
        file_names = set(filenames)

        has_java = has_java or (
            "pom.xml" in file_names
            or "build.gradle" in file_names
            or any(name.lower().endswith(".java") for name in filenames)
        )
        has_python = has_python or any(name.lower().endswith(".py") for name in filenames)
        has_web = has_web or any(
            Path(name).suffix.lower() in _WEB_EXTENSIONS for name in filenames
        )
        has_package_json = has_package_json or "package.json" in file_names
        has_node_source = has_node_source or any(
            Path(name).suffix.lower() in _NODE_EXTENSIONS for name in filenames
        )
        has_manage_py = has_manage_py or "manage.py" in file_names
        if "settings.py" in file_names:
            django_settings.append(current_path / "settings.py")
        if "templates" in current_path.parts:
            has_templates = True
        if "templates" in directories:
            has_templates = True

    if has_java:
        return "java"
    if has_manage_py:
        return "django"
    if has_templates:
        for settings in django_settings:
            settings_text = settings.read_text(
                encoding="utf-8", errors="ignore"
            ).lower()
            if "django" in settings_text or "installed_apps" in settings_text:
                return "django"
    if has_package_json and has_node_source:
        return "nodejs"
    if has_python:
        return "python"
    if has_web:
        return "web"
    raise ValueError(f"No supported project stack markers found in: {project_path}")
