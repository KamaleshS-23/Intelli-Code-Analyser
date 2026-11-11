import re
from pathlib import Path

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.web_common import (
    HtmlDocument,
    css_rule_blocks,
    debt_issue,
    js_class_references,
    read_source,
    source_files,
)


HTML_EXTENSIONS = {".html", ".htm"}
CSS_EXTENSIONS = {".css"}
JS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs"}
DYNAMIC_CLASSES = {"active", "hidden", "open", "selected", "disabled"}


class WebCrossLanguageRules(BaseRule):
    name = "WebCrossLanguageRules"

    def analyze(self, context):
        root = Path(context.project.project_path)
        html_paths = source_files(context, HTML_EXTENSIONS)
        css_paths = source_files(context, CSS_EXTENSIONS)
        js_paths = source_files(context, JS_EXTENSIONS)
        html_sources = {path: read_source(path) for path in html_paths}
        css_sources = {path: read_source(path) for path in css_paths}
        js_sources = {path: read_source(path) for path in js_paths}

        html_classes = set()
        for source in html_sources.values():
            for element in HtmlDocument(source).elements:
                html_classes.update((element["attrs"].get("class") or "").split())
        js_classes = set()
        for source in js_sources.values():
            js_classes.update(js_class_references(source))

        css_classes = set()
        for source in css_sources.values():
            for selector, _, _ in css_rule_blocks(source):
                css_classes.update(re.findall(r"\.([\w-]+)", selector))

        issues = []
        if css_paths:
            for name in sorted(css_classes - html_classes - js_classes - DYNAMIC_CLASSES):
                issues.append(debt_issue(
                    "UnusedCssClass", "medium", css_paths[0], root, 1,
                    f"CSS class '.{name}' is not used by HTML or JavaScript.",
                    "Remove the unused selector or connect it to a component.",
                ))
        if html_paths and css_paths:
            for name in sorted(html_classes - css_classes - js_classes):
                issues.append(debt_issue(
                    "UndefinedCssClass", "medium", html_paths[0], root, 1,
                    f"HTML class '{name}' is not defined in the project's CSS.",
                    "Define the class in a stylesheet or remove the stale markup reference.",
                ))

        for path, source in js_sources.items():
            function_matches = list(re.finditer(
                r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", source
            ))
            for function in function_matches:
                name = function.group(1)
                if re.search(r"\bexport\s+(?:default\s+)?function\s+" + re.escape(name), source):
                    continue
                without_declaration = source[:function.start()] + source[function.end():]
                html_event_reference = any(
                    re.search(r"\bon[a-z]+\s*=\s*['\"][^'\"]*\b" + re.escape(name) + r"\s*\(", html, re.I)
                    for html in html_sources.values()
                )
                if not re.search(r"\b" + re.escape(name) + r"\s*\(", without_declaration) and not html_event_reference:
                    issues.append(debt_issue(
                        "UnusedJsFunction", "medium", path, root,
                        source.count("\n", 0, function.start()) + 1,
                        f"JavaScript function '{name}' is never referenced.",
                        "Remove the dead function or wire it to an application event.",
                    ))

            adds = len(re.findall(r"\baddEventListener\s*\(", source))
            removes = len(re.findall(r"\bremoveEventListener\s*\(", source))
            if adds > 3 and removes == 0:
                issues.append(debt_issue(
                    "MissingEventListenerCleanup", "medium", path, root, 1,
                    f"{adds} event listeners are registered without any matching cleanup.",
                    "Remove listeners when their component or page lifecycle ends.",
                    metric_value=adds,
                    metric_threshold=3,
                ))
        return issues
