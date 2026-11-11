STACK_PROFILES = {
    "java": {
        "label": "Java",
        "description": "Java projects and Java-specific debt rules.",
        "extensions": {".java"},
        "languages": ["java"],
    },
    "python": {
        "label": "Python",
        "description": "Python projects and Python-specific debt rules.",
        "extensions": {".py"},
        "languages": ["python"],
    },
    "web": {
        "label": "Web (HTML/CSS/JavaScript)",
        "description": "Frontend projects: HTML, CSS, and JavaScript.",
        "extensions": {".html", ".htm", ".css", ".js", ".jsx", ".mjs"},
        "languages": ["html", "css", "javascript"],
    },
    "django": {
        "label": "Django (Python + HTML/CSS/JS)",
        "description": "Django/Python backends with HTML, CSS, and JavaScript.",
        "extensions": {".py", ".html", ".htm", ".css", ".js", ".jsx", ".mjs"},
        "languages": ["python", "html", "css", "javascript"],
    },
    "nodejs": {
        "label": "Node.js (JavaScript + HTML/CSS)",
        "description": "Node.js projects with JavaScript, HTML, and CSS.",
        "extensions": {".js", ".jsx", ".mjs", ".cjs", ".html", ".htm", ".css"},
        "languages": ["javascript", "html", "css"],
    },
}

STACK_ALIASES = {
    "py": "python",
    "javascript": "web",
    "frontend": "web",
    "node": "nodejs",
    "django-python": "django",
}


def normalize_stack(stack_value):
    normalized = str(stack_value or "java").strip().lower()
    normalized = STACK_ALIASES.get(normalized, normalized)
    if normalized not in STACK_PROFILES:
        choices = ", ".join(STACK_PROFILES)
        raise ValueError(f"Unsupported stack '{stack_value}'. Choose one of: {choices}.")
    return normalized
