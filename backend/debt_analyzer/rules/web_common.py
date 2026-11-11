"""Shared source discovery and lightweight HTML/CSS/JavaScript helpers."""

import re
from html.parser import HTMLParser
from pathlib import Path

from debt_analyzer.models import DebtIssue
from scanner.config import IGNORE_DIRS


WEB_RULE_METADATA = {
    "MissingImageAlt": ("WEB-HT-001", "ACCESSIBILITY", "HTML", "Add Accessibility Attribute", 2),
    "InlineStyle": ("WEB-HT-002", "STYLE", "HTML", "Extract Inline Style to CSS Class", 5),
    "InlineEventHandler": ("WEB-HT-003", "DESIGN", "HTML", "Move Event Handler to JS", 8),
    "DeprecatedTag": ("WEB-HT-004", "STRUCTURE", "HTML", "Modernize Markup", 10),
    "MissingDoctype": ("WEB-HT-005", "STRUCTURE", "HTML", "Add DOCTYPE", 1),
    "NonSemanticDivSoup": ("WEB-HT-006", "STRUCTURE", "HTML", "Replace Div with Semantic Element", 30),
    "ExcessiveImportant": ("WEB-CS-001", "STYLE", "CSS", "Reduce Specificity", 25),
    "HardcodedColor": ("WEB-CS-002", "STYLE", "CSS", "Replace Magic Value with CSS Variable", 2),
    "DuplicateSelector": ("WEB-CS-003", "STYLE", "CSS", "Consolidate Duplicate Rules", 5),
    "DeepSelectorNesting": ("WEB-CS-004", "STYLE", "CSS", "Flatten Selector Hierarchy", 5),
    "UnusedCssClass": ("WEB-XL-001", "STYLE", "CROSS", "Remove Dead CSS", 3),
    "UndefinedCssClass": ("WEB-XL-002", "STYLE", "CROSS", "Align Markup with Styles", 5),
    "UnusedJsFunction": ("WEB-XL-003", "LOGIC", "CROSS", "Remove Dead Code", 3),
    "MissingEventListenerCleanup": ("WEB-XL-004", "PERFORMANCE", "CROSS", "Add Event Cleanup", 20),
    "VarInsteadOfLetConst": ("WEB-JS-001", "LOGIC", "JS", "Replace var with let/const", 2),
    "LooseEquality": ("WEB-JS-002", "LOGIC", "JS", "Enforce Strict Equality", 1),
    "ConsoleLogInProduction": ("WEB-JS-003", "LOGIC", "JS", "Introduce Logging Abstraction", 6),
    "LongFunction": ("WEB-JS-004", "LOGIC", "JS", "Extract Function", 15),
    "CallbackHell": ("WEB-JS-005", "DESIGN", "JS", "Replace Callback with Promise/async-await", 30),
    "GlobalVariablePollution": ("WEB-JS-006", "DESIGN", "JS", "Encapsulate in Module", 5),
    "UnsafeEval": ("WEB-JS-007", "SECURITY", "JS", "Eliminate Dynamic Code Execution", 30),
    "UnsafeInnerHTML": ("WEB-JS-008", "SECURITY", "JS", "Replace innerHTML with Safe DOM API", 10),
}


class HtmlDocument(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.elements.append({
            "tag": tag.lower(),
            "attrs": dict(attrs),
            "line": self.getpos()[0],
        })

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def source_files(context, suffixes):
    root = Path(context.project.project_path)
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not any(part in IGNORE_DIRS for part in path.parts)
    )


def read_source(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def relative_path(path, root):
    return path.relative_to(root).as_posix()


def debt_issue(rule, severity, path, root, line, message, suggestion,
               metric_value=None, metric_threshold=None):
    relative = relative_path(path, root)
    rule_id, category, language, refactoring_pattern, fix_minutes = (
        WEB_RULE_METADATA.get(rule, ("", "", "", "", 0))
    )
    return DebtIssue(
        rule=rule,
        severity=severity,
        class_name=relative,
        file_path=relative,
        line_number=line,
        message=message,
        suggestion=suggestion,
        metric_value=metric_value,
        metric_threshold=metric_threshold,
        rule_id=rule_id,
        category=category,
        language=language,
        refactoring_pattern=refactoring_pattern,
        estimated_fix_minutes=_estimated_fix_minutes(rule, metric_value, fix_minutes),
        threshold=metric_threshold,
    )


def _estimated_fix_minutes(rule, metric_value, default):
    if metric_value is None:
        return default
    multiplier = {
        "NonSemanticDivSoup": 2,
        "ExcessiveImportant": 5,
        "MissingEventListenerCleanup": 5,
        "ConsoleLogInProduction": 2,
    }.get(rule)
    if multiplier is None:
        return default
    return max(1, int(metric_value * multiplier))


def css_rule_blocks(source):
    clean = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), source, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", clean, re.S):
        selector = match.group(1).strip()
        if not selector or selector.startswith("@"):
            continue
        line = clean.count("\n", 0, match.start()) + 1
        declarations = [
            part.strip() for part in match.group(2).split(";")
            if ":" in part and part.strip()
        ]
        yield selector, declarations, line


def js_class_references(source):
    classes = set()
    for match in re.finditer(
        r"\bclassList\.(?:add|remove|toggle|contains)\s*\(([^)]*)\)", source
    ):
        classes.update(re.findall(r"['\"]([\w-]+)['\"]", match.group(1)))
    for match in re.finditer(
        r"\bquerySelector(?:All)?\s*\(\s*['\"]([^'\"]*)['\"]", source
    ):
        classes.update(re.findall(r"\.([\w-]+)", match.group(1)))
    for match in re.finditer(
        r"\bgetElementsByClassName\s*\(\s*['\"]([^'\"]*)['\"]", source
    ):
        classes.update(match.group(1).split())
    for match in re.finditer(
        r"\bclassName\s*(?:=|\+=)\s*['\"]([^'\"]*)['\"]", source
    ):
        classes.update(match.group(1).split())
    return classes


def mask_js(source):
    """Blank comments and quoted text without changing offsets or line numbers."""
    chars = list(source)
    index = 0
    state = "code"
    quote = ""
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char in ("'", '"', "`"):
                state, quote = "string", char
                chars[index] = " "
            elif char == "/" and next_char == "/":
                state = "line_comment"
                chars[index] = chars[index + 1] = " "
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                chars[index] = chars[index + 1] = " "
                index += 1
        elif state == "string":
            if char == "\\":
                chars[index] = " "
                if index + 1 < len(source):
                    if source[index + 1] != "\n":
                        chars[index + 1] = " "
                    index += 1
            else:
                if char != "\n":
                    chars[index] = " "
                if char == quote:
                    state = "code"
        elif state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                chars[index] = " "
        else:
            if char == "*" and next_char == "/":
                chars[index] = chars[index + 1] = " "
                index += 1
                state = "code"
            elif char != "\n":
                chars[index] = " "
        index += 1
    return "".join(chars)


def line_number(source, offset):
    return source.count("\n", 0, offset) + 1


def matching_brace(source, masked, opening):
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(source)
