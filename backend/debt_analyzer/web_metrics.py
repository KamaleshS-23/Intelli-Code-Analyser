"""Metrics for HTML, CSS, JavaScript, and their DOM relationships."""

import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from debt_analyzer.rules.web_common import (
    HtmlDocument,
    css_rule_blocks,
    js_class_references,
    mask_js,
    read_source,
    source_files,
)


def html_metrics(source):
    document = HtmlDocument(source)
    tags = Counter(element["tag"] for element in document.elements)
    semantic_tags = {
        "article", "aside", "footer", "header", "main", "nav", "section",
        "details", "figure", "figcaption", "summary", "time",
    }
    semantic_count = sum(count for tag, count in tags.items() if tag in semantic_tags)
    return {
        "elements": len(document.elements),
        "unique_tags": len(tags),
        "tag_names": sorted(tags),
        "div_count": tags.get("div", 0),
        "inline_styles": sum("style" in element["attrs"] for element in document.elements),
        "inline_handlers": sum(
            attr.startswith("on")
            for element in document.elements
            for attr in element["attrs"]
        ),
        "semantic_ratio": round(semantic_count / max(len(document.elements), 1), 3),
        "ids": sorted({
            element["attrs"]["id"] for element in document.elements
            if element["attrs"].get("id")
        }),
        "classes": sorted({
            name
            for element in document.elements
            for name in (element["attrs"].get("class") or "").split()
        }),
        "class_count": len({
            name
            for element in document.elements
            for name in (element["attrs"].get("class") or "").split()
        }),
    }


def _specificity(selector):
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+", selector))
    without_pseudo = re.sub(r"::?[\w-]+(?:\([^)]*\))?", " ", selector)
    elements = len(re.findall(r"(?<![\w-])(?:[A-Za-z][\w-]*|\*)", without_pseudo))
    return ids * 100 + classes * 10 + elements


def css_metrics(source):
    rules = list(css_rule_blocks(source))
    declarations = sum(len(items) for _, items, _ in rules)
    selectors = [re.sub(r"\s+", " ", selector).strip() for selector, _, _ in rules]
    clean = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return {
        "rules": len(rules),
        "declarations": declarations,
        "avg_declarations_per_rule": round(declarations / max(len(rules), 1), 2),
        "important_count": len(re.findall(r"!important\b", clean, re.I)),
        "specificity_max": max((_specificity(selector) for selector in selectors), default=0),
        "unique_selectors": len(set(selectors)),
        "duplicate_selectors": sum(count - 1 for count in Counter(selectors).values() if count > 1),
        "hardcoded_colors": len(re.findall(
            r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\s*\(", clean, re.I
        )),
        "media_queries": len(re.findall(r"@media\b", clean, re.I)),
    }


def javascript_metrics(source):
    code = mask_js(source)
    function_matches = []
    for pattern in (
        r"\bfunction\s*[\w$]*\s*\([^)]*\)\s*\{",
        r"\b(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>\s*\{",
    ):
        function_matches.extend(re.finditer(pattern, code))
    function_lengths = []
    for match in function_matches:
        opening = code.find("{", match.start(), match.end())
        depth = 0
        closing = len(code)
        for index in range(opening, len(code)):
            if code[index] == "{":
                depth += 1
            elif code[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        function_lengths.append(source.count("\n", opening, closing) + 1)
    nonempty_lines = sum(bool(line.strip()) for line in source.splitlines())
    classes = len(re.findall(r"\bclass\s+[A-Za-z_$][\w$]*", code))
    return {
        "loc": nonempty_lines,
        "functions": len(function_matches),
        "classes": classes,
        "avg_lines_per_function": round(
            sum(function_lengths) / max(len(function_lengths), 1), 2
        ),
        "var_count": len(re.findall(r"\bvar\s+[\w$]+", code)),
        "let_count": len(re.findall(r"\blet\s+[\w$]+", code)),
        "const_count": len(re.findall(r"\bconst\s+[\w$]+", code)),
        "loose_equality": len(re.findall(r"(?<![=!])==(?![=])|(?<![!])!=(?!=)", code)),
        "eval_calls": len(re.findall(r"\beval\s*\(|\bnew\s+Function\s*\(", code)),
        "innerHTML_uses": len(re.findall(r"\.\s*innerHTML\s*=", code)),
        "async_await": len(re.findall(r"\basync\b|\bawait\b", code)),
        "callbacks": len(re.findall(r"\bfunction\b|=>", code)),
        "console_calls": len(re.findall(
            r"\bconsole\.(?:log|debug|info|warn|error)\s*\(", code
        )),
        "document_writes": len(re.findall(r"\bdocument\.write\s*\(", code)),
    }


def _totals(metrics, keys):
    totals = {key: sum(item[key] for item in metrics.values()) for key in keys}
    if "specificity_max" in keys:
        totals["specificity_max"] = max(
            (item["specificity_max"] for item in metrics.values()), default=0
        )
    if "avg_declarations_per_rule" in keys:
        rules = totals["rules"]
        totals["avg_declarations_per_rule"] = round(
            totals["declarations"] / max(rules, 1), 2
        )
    if "avg_lines_per_function" in keys:
        functions = totals["functions"]
        totals["avg_lines_per_function"] = round(
            sum(item["avg_lines_per_function"] * item["functions"] for item in metrics.values())
            / max(functions, 1),
            2,
        )
    return totals


def analyze_web_metrics(context, issues):
    html_paths = source_files(context, {".html", ".htm"})
    css_paths = source_files(context, {".css"})
    js_paths = source_files(context, {".js", ".jsx", ".mjs", ".cjs"})
    root = context.project.project_path

    html_by_file = {
        path.relative_to(root).as_posix(): html_metrics(read_source(path))
        for path in html_paths
    }
    html_totals = _totals(
        html_by_file,
        ("elements", "div_count", "inline_styles", "inline_handlers"),
    )
    html_totals["class_count"] = len({
        name for item in html_by_file.values() for name in item["classes"]
    })
    html_totals["unique_tags"] = len({
        tag for item in html_by_file.values() for tag in item["tag_names"]
    })
    html_totals["semantic_ratio"] = round(
        sum(item["semantic_ratio"] * item["elements"] for item in html_by_file.values())
        / max(html_totals["elements"], 1),
        3,
    )
    css_by_file = {
        path.relative_to(root).as_posix(): css_metrics(read_source(path))
        for path in css_paths
    }
    css_totals = _totals(
        css_by_file,
        ("rules", "declarations", "avg_declarations_per_rule", "important_count",
         "specificity_max", "duplicate_selectors", "hardcoded_colors", "media_queries"),
    )
    css_totals["unique_selectors"] = len({
        re.sub(r"\s+", " ", selector).strip()
        for path in css_paths
        for selector, _, _ in css_rule_blocks(read_source(path))
    })
    js_sources = {path: read_source(path) for path in js_paths}
    js_by_file = {
        path.relative_to(root).as_posix(): javascript_metrics(source)
        for path, source in js_sources.items()
    }

    coupling = {}
    root_path = Path(root).resolve()
    js_paths_by_resolved_path = {path.resolve(): path for path in js_paths}
    for html_path in html_paths:
        html_name = html_path.relative_to(root).as_posix()
        html_source = read_source(html_path)
        html_ids = set(html_metrics(html_source)["ids"])
        script_targets = []
        for element in HtmlDocument(html_source).elements:
            if element["tag"] != "script" or not element["attrs"].get("src"):
                continue
            src = urlsplit(element["attrs"]["src"])
            if src.scheme or src.netloc or not src.path:
                continue
            if src.path.startswith(("/", "\\")):
                target = root_path / src.path.lstrip("/\\")
            else:
                target = html_path.parent / src.path
            try:
                target.resolve().relative_to(root_path)
            except ValueError:
                continue
            script_targets.append(target.resolve())

        paired_js_paths = [
            js_paths_by_resolved_path[target]
            for target in script_targets
            if target in js_paths_by_resolved_path
        ]
        if not paired_js_paths:
            paired_js_paths = [path for path in js_paths if path.stem == html_path.stem]

        for js_path in paired_js_paths:
            js_source = js_sources[js_path]
            js_name = js_path.relative_to(root).as_posix()
            html_classes = set(html_metrics(html_source)["classes"])
            bound_ids = {
                left or right for left, right in re.findall(
                    r"getElementById\s*\(\s*['\"]([\w-]+)['\"]\s*\)"
                    r"|querySelector(?:All)?\s*\(\s*['\"]#([\w-]+)['\"]\s*\)",
                    js_source,
                )
            }
            bound_classes = js_class_references(js_source)
            coupling[f"{html_name}::{js_name}"] = {
                "html_ids": len(html_ids),
                "js_bound_ids": len(bound_ids),
                "orphan_js_ids": len(bound_ids - html_ids),
                "orphan_html_ids": len(html_ids - bound_ids),
                "orphan_js_id_names": sorted(bound_ids - html_ids),
                "orphan_html_id_names": sorted(html_ids - bound_ids),
                "html_classes": len(html_classes),
                "js_bound_classes": len(bound_classes),
                "orphan_js_classes": len(bound_classes - html_classes),
                "orphan_html_classes": len(html_classes - bound_classes),
                "orphan_js_class_names": sorted(bound_classes - html_classes),
                "orphan_html_class_names": sorted(html_classes - bound_classes),
                "dom_coupling_score": round(
                    len(bound_ids) / max(len(html_ids), 1), 2
                ),
            }

    analysis = {
        "summary": {
            "files": {
                "html": len(html_paths),
                "css": len(css_paths),
                "javascript": len(js_paths),
            },
        },
        "metrics": {
            "html": {
                "files": html_by_file,
                "totals": html_totals,
            },
            "css": {
                "files": css_by_file,
                "totals": css_totals,
            },
            "javascript": {
                "files": js_by_file,
                "totals": _totals(
                    js_by_file,
                    ("loc", "functions", "classes", "avg_lines_per_function", "var_count",
                     "let_count", "const_count", "loose_equality", "eval_calls",
                     "innerHTML_uses", "async_await", "callbacks", "console_calls",
                     "document_writes"),
                ),
            },
            "coupling": coupling,
        },
    }
    update_web_summary(analysis, issues)
    return analysis


def update_web_summary(analysis, issues):
    weights = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0.5}
    metrics = analysis["metrics"]
    total_loc = (
        metrics["javascript"]["totals"]["loc"]
        + metrics["css"]["totals"]["rules"]
        + metrics["html"]["totals"]["elements"]
    )
    analysis["summary"].update({
        "total_issues": len(issues),
        "severity_counts": dict(Counter(issue.severity for issue in issues)),
        "debt_score": round(min(
            100,
            sum(weights.get(issue.severity, 1) for issue in issues)
            / max(total_loc, 1) * 100,
        ), 2),
    })
