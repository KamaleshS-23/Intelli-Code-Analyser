"""
File-system helpers for the scanner: discovering source files while
skipping build artifacts / IDE folders / VCS folders.
"""

from pathlib import Path
from scanner.config import IGNORE_DIRS
from stacks import STACK_PROFILES, normalize_stack


def get_java_files(project_path):
    """Recursively find all .java files under project_path."""
    java_files = []
    root = Path(project_path)

    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_path}")

    for file in root.rglob("*.java"):
        if any(part in IGNORE_DIRS for part in file.parts):
            continue
        java_files.append(file)

    return java_files


def get_python_files(project_path):
    """Recursively find all .py files under project_path."""
    python_files = []
    root = Path(project_path)

    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_path}")

    for file in root.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in file.parts):
            continue
        python_files.append(file)

    return python_files


def get_source_files(project_path, stack):
    """Find all source files included by a supported stack profile."""
    root = Path(project_path)
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_path}")

    profile = STACK_PROFILES[normalize_stack(stack)]
    return [
        file
        for file in root.rglob("*")
        if file.is_file()
        and file.suffix.lower() in profile["extensions"]
        and not any(part in IGNORE_DIRS for part in file.parts)
    ]


def read_source(file_path):
    """Read a source file safely, tolerating odd encodings."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()
