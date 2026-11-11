import pytest

from refactor import clean_ai_code_output, generate_optimized_code
from refactor import code_generator


@pytest.mark.parametrize(
    "fenced_code",
    [
        "```java\nclass Example {}\n```",
        "```python\nprint('hello')\n```",
        "```js\nconsole.log('hello');\n```",
        "```html\n<p>Hello</p>\n```",
        "```\nsource code\n```",
    ],
)
def test_clean_ai_code_output_removes_enclosing_fence(fenced_code):
    assert "```" not in clean_ai_code_output(fenced_code)


def test_clean_ai_code_output_preserves_unfenced_source():
    source = "class Example {\n    String marker = \"```\";\n}"

    assert clean_ai_code_output(source) == source


def test_generate_optimized_code_uses_provider_and_cleans_output(monkeypatch):
    class FakeProvider:
        def generate(self, prompt, context=None):
            assert "Language/stack: java" in prompt
            assert "Stack context: Java application source." in prompt
            assert "LongMethod" in prompt
            assert "Method is too long." in prompt
            assert "Extract the repeated work." in prompt
            assert "File path: src/Example.java" in prompt
            assert "class Example {}" in prompt
            return "```java\nclass Example { /* refactored */ }\n```"

    monkeypatch.setattr(code_generator, "get_code_generation_provider", lambda: FakeProvider())

    result = generate_optimized_code(
        "class Example {}",
        {
            "rule": "LongMethod",
            "message": "Method is too long.",
            "suggestion": "Extract the repeated work.",
            "file_path": "src/Example.java",
        },
        language="java",
    )

    assert result == "class Example { /* refactored */ }"


def test_generate_optimized_code_surfaces_provider_errors(monkeypatch):
    class FailingProvider:
        def generate(self, prompt, context=None):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(code_generator, "get_code_generation_provider", lambda: FailingProvider())

    with pytest.raises(RuntimeError, match="AI code generation failed: provider unavailable"):
        generate_optimized_code("class Example {}", {}, language="java")


def test_generate_optimized_code_rejects_empty_response(monkeypatch):
    class EmptyProvider:
        def generate(self, prompt, context=None):
            return "```python\n\n```"

    monkeypatch.setattr(code_generator, "get_code_generation_provider", lambda: EmptyProvider())

    with pytest.raises(ValueError, match="AI provider returned empty code"):
        generate_optimized_code("print('hello')", {}, language="python")


@pytest.mark.parametrize(
    ("language", "stack_context"),
    [
        ("python", "Python application source."),
        ("javascript", "JavaScript source for a web or Node.js application."),
        ("html", "HTML source in a web frontend."),
        ("css", "CSS source in a web frontend."),
        ("web", "Web stack source: HTML, CSS, and JavaScript."),
        ("django", "Django stack source: Python backend, templates, and static assets."),
        ("nodejs", "Node.js stack source: JavaScript backend with HTML/CSS assets."),
    ],
)
def test_generate_optimized_code_includes_stack_context(
    monkeypatch, language, stack_context
):
    class FakeProvider:
        def generate(self, prompt, context=None):
            assert f"Language/stack: {language}" in prompt
            assert f"Stack context: {stack_context}" in prompt
            return "optimized source"

    monkeypatch.setattr(code_generator, "get_code_generation_provider", lambda: FakeProvider())

    assert generate_optimized_code("source", {}, language=language) == "optimized source"


def test_generate_optimized_code_rejects_unsupported_language():
    with pytest.raises(ValueError, match="Unsupported language"):
        generate_optimized_code("source", {}, language="ruby")
