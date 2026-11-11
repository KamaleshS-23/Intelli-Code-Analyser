import re
from collections import Counter
from pathlib import Path

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.web_common import (
    HtmlDocument,
    debt_issue,
    read_source,
    source_files,
)


HTML_EXTENSIONS = {".html", ".htm"}
DEPRECATED_TAGS = {
    "acronym", "applet", "basefont", "big", "blink", "center", "dir", "font",
    "frame", "frameset", "marquee", "noframes", "strike", "tt",
}
SEMANTIC_TAGS = {
    "article", "aside", "footer", "header", "main", "nav", "section",
    "details", "figure", "figcaption", "summary", "time",
}


class HtmlRules(BaseRule):
    name = "HtmlWebRules"

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        for path in source_files(context, HTML_EXTENSIONS):
            source = read_source(path)
            document = HtmlDocument(source)
            for element in document.elements:
                tag = element["tag"]
                attrs = element["attrs"]
                line = element["line"]
                if tag == "img" and "alt" not in attrs:
                    issues.append(debt_issue(
                        "MissingImageAlt", "high", path, root, line,
                        "Image is missing an alt attribute.",
                        "Add concise alternative text, or alt=\"\" for a decorative image.",
                    ))
                if "style" in attrs:
                    issues.append(debt_issue(
                        "InlineStyle", "medium", path, root, line,
                        "Inline styling couples presentation to HTML markup.",
                        "Move the styling into a reusable CSS class.",
                    ))
                for attr in attrs:
                    if attr.startswith("on"):
                        issues.append(debt_issue(
                            "InlineEventHandler", "medium", path, root, line,
                            f"Inline event handler '{attr}' couples behavior to markup.",
                            "Register the event handler from a JavaScript module.",
                        ))
                if tag in DEPRECATED_TAGS:
                    issues.append(debt_issue(
                        "DeprecatedTag", "medium", path, root, line,
                        f"Deprecated HTML element <{tag}> found.",
                        "Replace it with semantic HTML and CSS.",
                    ))

            if not re.match(r"\s*<!doctype\s+html\b", source, re.I):
                issues.append(debt_issue(
                    "MissingDoctype", "high", path, root, 1,
                    "Missing HTML5 <!DOCTYPE html> declaration.",
                    "Add <!DOCTYPE html> as the first document declaration.",
                ))

            div_count = sum(element["tag"] == "div" for element in document.elements)
            if div_count > 30:
                issues.append(debt_issue(
                    "NonSemanticDivSoup", "low", path, root, 1,
                    f"{div_count} <div> elements make the document structure difficult to understand.",
                    "Use semantic elements such as <main>, <nav>, <section>, and <article>.",
                    metric_value=div_count,
                    metric_threshold=30,
                ))
        return issues
