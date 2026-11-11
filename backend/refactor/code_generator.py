"""AI-assisted code generation for technical-debt refactoring."""

import re

from ai_assistant.provider import get_code_generation_provider


_CODE_FENCE_PATTERN = re.compile(
    r"\A\s*```[^\r\n]*\r?\n(.*?)\r?\n?```\s*\Z",
    re.DOTALL,
)

_STACK_CONTEXT = {
    "java": "Java application source.",
    "python": "Python application source.",
    "javascript": "JavaScript source for a web or Node.js application.",
    "html": "HTML source in a web frontend.",
    "css": "CSS source in a web frontend.",
    "web": "Web stack source: HTML, CSS, and JavaScript.",
    "django": "Django stack source: Python backend, templates, and static assets.",
    "nodejs": "Node.js stack source: JavaScript backend with HTML/CSS assets.",
}


def clean_ai_code_output(text: str) -> str:
    """Remove an enclosing Markdown code fence from generated code."""
    if not isinstance(text, str):
        raise TypeError("AI code output must be a string.")

    output = text.strip()
    fenced_match = _CODE_FENCE_PATTERN.fullmatch(output)
    if fenced_match:
        output = fenced_match.group(1).strip()
    return output


def generate_optimized_code(
    original_code: str,
    issue: dict,
    language: str,
) -> str:
    """Generate a behavior-preserving refactoring for a reported issue."""
    if not isinstance(original_code, str):
        raise TypeError("original_code must be a string.")
    if not isinstance(issue, dict):
        raise TypeError("issue must be a dict.")
    if not isinstance(language, str):
        raise TypeError("language must be a string.")

    normalized_language = language.strip().lower()
    stack_context = _STACK_CONTEXT.get(normalized_language)
    if stack_context is None:
        supported_languages = ", ".join(_STACK_CONTEXT)
        raise ValueError(
            f"Unsupported language '{language}'. Supported values: "
            f"{supported_languages}."
        )

    prompt = f"""Refactor the following code to address the reported issue.

Language/stack: {normalized_language}
Stack context: {stack_context}

Issue rule: {issue.get("rule") or "Not specified"}
Issue message: {issue.get("message") or "Not specified"}
Suggested refactoring: {issue.get("suggestion") or "Not specified"}
File path: {issue.get("file_path") or "Not specified"}

Requirements:
1. Refactor only according to the suggestion.
2. Preserve the code's behavior.
3. Do not add dependencies.
4. Keep public signatures stable unless a change is required.
5. Return ONLY optimized code.
6. Do not include Markdown or an explanation.

Original code:
{original_code}
"""

    try:
        response = get_code_generation_provider().generate(prompt)
    except Exception as exc:
        raise RuntimeError(f"AI code generation failed: {exc}") from exc

    optimized_code = clean_ai_code_output(response)
    if not optimized_code:
        raise ValueError("AI provider returned empty code.")
    return optimized_code
