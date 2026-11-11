import pytest

from scanner.stack_detector import detect_stack


@pytest.mark.parametrize(
    ("files", "expected_stack"),
    [
        ({"src/Main.java": ""}, "java"),
        ({"pom.xml": ""}, "java"),
        ({"manage.py": ""}, "django"),
        (
            {
                "config/settings.py": "INSTALLED_APPS = ['django.contrib.admin']",
                "templates/home.html": "<html></html>",
            },
            "django",
        ),
        ({"app/main.py": "print('hello')"}, "python"),
        (
            {
                "package.json": '{"name": "sample"}',
                "src/index.ts": "console.log('hello')",
            },
            "nodejs",
        ),
        ({"index.html": "<html></html>", "styles.css": "body {}"}, "web"),
        (
            {
                "package.json": "{}",
                "index.js": "console.log('hello')",
                "templates/home.html": "<html></html>",
                "config/settings.py": "INSTALLED_APPS = ['django']",
            },
            "django",
        ),
    ],
)
def test_detect_stack_identifies_project_markers(tmp_path, files, expected_stack):
    for relative_path, content in files.items():
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    assert detect_stack(str(tmp_path)) == expected_stack


def test_detect_stack_ignores_node_modules(tmp_path):
    (tmp_path / "node_modules" / "package").mkdir(parents=True)
    (tmp_path / "node_modules" / "package" / "index.js").write_text(
        "module.exports = true", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="No supported project stack markers"):
        detect_stack(str(tmp_path))


def test_detect_stack_requires_project_directory(tmp_path):
    file_path = tmp_path / "file.py"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        detect_stack(str(file_path))
