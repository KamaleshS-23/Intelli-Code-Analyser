"""Build a stack-aware PDF report from completed scan and optimization data."""

import difflib
import html
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


_NAVY = colors.HexColor("#12213A")
_INK = colors.HexColor("#1F2937")
_MUTED = colors.HexColor("#64748B")
_CYAN = colors.HexColor("#0891B2")
_GREEN = colors.HexColor("#059669")
_RED = colors.HexColor("#DC2626")
_PURPLE = colors.HexColor("#6D5BD0")
_LINE = colors.HexColor("#D9E2EC")
_SEVERITIES = ("critical", "high", "medium", "low")
REPORT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "scanner" / "output" / "reports"


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _sequence(value):
    return value if isinstance(value, list) else []


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _fmt(value, decimals=0):
    number = _number(value)
    if number is None:
        return "N/A"
    return f"{number:,.{decimals}f}"


def _percent(part, total):
    part_number, total_number = _number(part), _number(total)
    if part_number is None or total_number is None or total_number <= 0:
        return "N/A"
    return f"{part_number / total_number * 100:.1f}%"


def _bytes(value):
    number = _number(value)
    if number is None:
        return "N/A"
    size = number
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{size:,.0f} B"
        size /= 1024
    return "N/A"


def _duration(value):
    number = _number(value)
    return f"{number:.2f} s" if number is not None else "N/A"


def _escape(value):
    text = "N/A" if value is None or value == "" else str(value)
    text = (
        text.replace("→", " to ")
        .replace("•", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("×", "x")
    )
    return html.escape(text, quote=True).encode("latin-1", "replace").decode("latin-1")


def _paragraph(value, style):
    return Paragraph(_escape(value), style)


def _issues(scan):
    return [
        issue for issue in _sequence(_mapping(scan.get("debt_report")).get("issues"))
        if isinstance(issue, dict)
    ]


def _score(scan, comparison, key):
    candidate = _number(_mapping(comparison).get(key))
    if candidate is not None:
        return candidate
    report = _mapping(scan.get("debt_report"))
    score = _number(report.get("total_score"))
    return score if score is not None else _number(report.get("debt_score"))


def _severity_counts(issues, report):
    counts = {
        str(key).lower(): value
        for key, value in _mapping(_mapping(report).get("severity_counts")).items()
    }
    return {
        severity: (
            _number(counts.get(severity))
            if severity in counts else
            sum(str(issue.get("severity", "")).lower() == severity for issue in issues)
        )
        for severity in _SEVERITIES
    }


def _category_count(issues, category):
    return sum(
        str(issue.get("category", "")).upper() == category
        for issue in issues
    )


def _code_smell_count(issues):
    return sum(
        str(issue.get("category", "")).upper()
        not in {"SECURITY", "DEPENDENCY", "VULNERABILITY"}
        for issue in issues
    )


def _source_metrics(scan, metadata, side):
    metrics = _mapping(_mapping(metadata).get(f"source_metrics_{side}"))
    stats = _mapping(scan.get("statistics"))
    return {
        "files_discovered": metrics.get("files_discovered", stats.get("total_files")),
        "parsed_files": stats.get("parsed_files"),
        "parse_failures": stats.get("failed_files"),
        "project_size_bytes": metrics.get("project_size_bytes"),
        "lines_of_code": metrics.get("lines_of_code"),
        "comment_lines": metrics.get("comment_lines"),
        "blank_lines": metrics.get("blank_lines"),
    }


def _classes(scan):
    return [
        item for item in _sequence(scan.get("classes"))
        if isinstance(item, dict)
    ]


def _quality_values(scan):
    classes = _classes(scan)
    methods = [
        method for cls in classes
        for method in _sequence(_mapping(cls).get("methods"))
        if isinstance(method, dict)
    ]
    complexity = [
        value for value in (_number(method.get("cyclomatic_complexity")) for method in methods)
        if value is not None
    ]
    statistics = _mapping(scan.get("statistics"))
    graph = _mapping(statistics.get("graph"))
    fan_out = [
        _number(item.get("fan_out"))
        for item in _sequence(graph.get("class_metrics"))
        if isinstance(item, dict)
    ]
    fan_out = [value for value in fan_out if value is not None]
    return {
        "average_complexity": sum(complexity) / len(complexity) if complexity else None,
        "maximum_complexity": max(complexity) if complexity else None,
        "methods_over_threshold": sum(value > 10 for value in complexity) if complexity else None,
        "average_coupling": sum(fan_out) / len(fan_out) if fan_out else None,
        "duplication": None,
        "stack": str(statistics.get("stack", "unknown")).lower(),
    }


def _dependency_values(scan):
    report = _mapping(scan.get("dependency_report"))
    dependencies = _sequence(report.get("dependencies"))
    outdated = _sequence(report.get("outdated_dependencies"))
    stack = str(_mapping(scan.get("statistics")).get("stack", "")).lower()
    if stack == "nodejs":
        packages = _mapping(
            _mapping(_mapping(scan.get("statistics")).get("node_analysis")).get("metrics")
        ).get("dependencies", {})
        packages = _mapping(packages)
        total = _number(packages.get("total"))
        return {
            "total": total,
            "outdated": None,
            "vulnerable": None,
            "build": "npm / package.json" if total is not None else None,
        }
    return {
        "total": len(dependencies) if dependencies or report.get("build_tool") not in (None, "", "unknown") else None,
        "outdated": len(outdated) if outdated or report.get("build_tool") not in (None, "", "unknown") else None,
        "vulnerable": sum(
            str(item.get("severity", "")).lower() in {"critical", "high"}
            for item in outdated if isinstance(item, dict)
        ) if outdated or report.get("build_tool") not in (None, "", "unknown") else None,
        "build": report.get("build_tool") if report else None,
    }


def _stack_metrics(scan):
    statistics = _mapping(scan.get("statistics"))
    stack = str(statistics.get("stack", "unknown")).lower()
    stats_metrics = _mapping(statistics)
    web = _mapping(statistics.get("web_analysis"))
    django = _mapping(statistics.get("django_analysis"))
    node = _mapping(statistics.get("node_analysis"))
    metrics = []
    if web:
        web_metrics = _mapping(web.get("metrics"))
        for label, key in (("HTML", "html"), ("CSS", "css"), ("JavaScript", "javascript")):
            totals = _mapping(_mapping(web_metrics.get(key)).get("totals"))
            if totals:
                preferred = ("elements", "semantic_ratio") if key == "html" else (
                    ("rules", "important_count") if key == "css" else ("loc", "functions")
                )
                metrics.append(
                    f"{label}: " + ", ".join(f"{name} {_fmt(totals.get(name))}" for name in preferred)
                )
    if django:
        dm = _mapping(django.get("metrics"))
        metrics.extend([
            f"Django version: {dm.get('django_version', 'N/A')}",
            f"ORM N+1 risk: {_fmt(_mapping(dm.get('orm')).get('n_plus_one_risk'))}",
            f"Views: {_fmt(_mapping(dm.get('views')).get('view_count'))}",
            f"Apps: {_fmt(_mapping(dm.get('architecture')).get('app_count'))}",
        ])
    if node:
        nm = _mapping(node.get("metrics"))
        deps = _mapping(nm.get("dependencies"))
        routes = _mapping(nm.get("routes"))
        route_total = sum(
            (_number(item.get("route_count")) or 0)
            for item in routes.values() if isinstance(item, dict)
        )
        metrics.extend([
            f"Framework: {node.get('framework', 'N/A')}",
            f"Production / dev packages: {_fmt(deps.get('production'))} / {_fmt(deps.get('dev'))}",
            f"Routes: {_fmt(route_total) if routes else 'N/A'}",
        ])
    if stack in {"java", "python"}:
        quality = _quality_values(scan)
        metrics.extend([
            f"Classes / methods: {_fmt(stats_metrics.get('total_classes'))} / {_fmt(stats_metrics.get('total_methods'))}",
            f"Average / maximum cyclomatic complexity: {_fmt(quality['average_complexity'], 2)} / {_fmt(quality['maximum_complexity'], 2)}",
            f"Dependency edges / cycles: {_fmt(stats_metrics.get('dependency_edges'))} / {_fmt(stats_metrics.get('circular_dependencies'))}",
        ])
    if not metrics:
        metrics.append(f"Stack profile: {stack}")
    return metrics


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=21, leading=24, textColor=_NAVY, alignment=TA_CENTER, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle", parent=base["Normal"], fontSize=10.5, leading=14,
            textColor=_MUTED, alignment=TA_CENTER, spaceAfter=3,
        ),
        "tagline": ParagraphStyle(
            "ReportTagline", parent=base["Normal"], fontSize=8, leading=11,
            textColor=_CYAN, alignment=TA_CENTER, spaceAfter=11,
        ),
        "section": ParagraphStyle(
            "ReportSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=_NAVY, spaceBefore=9, spaceAfter=5,
            keepWithNext=True,
        ),
        "subsection": ParagraphStyle(
            "ReportSubsection", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=_CYAN, spaceBefore=5, spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ReportBody", parent=base["BodyText"], fontSize=8.2, leading=11.2,
            textColor=_INK, spaceAfter=5, alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "ReportSmall", parent=base["BodyText"], fontSize=7, leading=9,
            textColor=_MUTED,
        ),
        "cell": ParagraphStyle(
            "ReportCell", parent=base["BodyText"], fontSize=7, leading=8.7,
            textColor=_INK, wordWrap="CJK",
        ),
        "cell_header": ParagraphStyle(
            "ReportCellHeader", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7, leading=8, textColor=colors.white,
        ),
        "kpi_label": ParagraphStyle(
            "KpiLabel", parent=base["Normal"], fontSize=6.5, leading=8,
            textColor=_MUTED, alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "KpiValue", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=14, leading=16, textColor=_NAVY, alignment=TA_CENTER,
        ),
        "kpi_note": ParagraphStyle(
            "KpiNote", parent=base["Normal"], fontSize=6, leading=7,
            textColor=_MUTED, alignment=TA_CENTER,
        ),
        "metric": ParagraphStyle(
            "MetricCell", parent=base["Normal"], fontSize=6.3, leading=8,
            textColor=_INK,
        ),
    }


def _table(rows, widths, styles, repeat_rows=1):
    max_width = 180 * mm
    requested_width = sum(widths)
    if requested_width > max_width:
        widths = [width * max_width / requested_width for width in widths]
    cells = []
    for row_index, row in enumerate(rows):
        style = styles["cell_header"] if row_index == 0 else styles["cell"]
        cells.append([_paragraph(value, style) for value in row])
    table = Table(cells, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
    ]))
    return table


def _card(label, value, note, background, styles, accent):
    card = Table([
        [_paragraph(label, styles["kpi_label"])],
        [_paragraph(value, ParagraphStyle(
            f"KpiValue{label}", parent=styles["kpi_value"], textColor=accent,
        ))],
        [_paragraph(note, styles["kpi_note"])],
    ], colWidths=[40 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#DCE5EF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return card


def _kpi_section(baseline, optimized, comparison, metadata, before_metrics,
                 after_metrics, before_issues, after_issues, styles):
    before_score = _score(baseline, comparison, "baseline_score")
    after_score = _score(optimized, comparison, "current_score")
    if before_score is None or after_score is None:
        score_improvement = "N/A"
    elif before_score > 0:
        score_improvement = f"{(before_score - after_score) / before_score * 100:.1f}%"
    else:
        score_improvement = "0.0%"
    issue_delta = len(after_issues) - len(before_issues)
    parse_before = _percent(before_metrics["parsed_files"], before_metrics["files_discovered"])
    parse_after = _percent(after_metrics["parsed_files"], after_metrics["files_discovered"])
    workflow = _mapping(metadata.get("durations")).get("total_workflow_seconds")
    cards = [
        ("Debt Score (Before)", _fmt(before_score), "Original scan", colors.HexColor("#EAF3FF"), _CYAN),
        ("Debt Score (After)", _fmt(after_score), "Optimized rescan", colors.HexColor("#E9FAF3"), _GREEN),
        ("Improvement %", score_improvement, "Score-based", colors.HexColor("#F0EDFF"), _PURPLE),
        ("Issues Reduced (delta)", _fmt(-issue_delta), "Before minus after", colors.HexColor("#FFF4E5"), _RED if issue_delta > 0 else _GREEN),
        ("Total Issues", f"{len(before_issues)} → {len(after_issues)}", "Before → after", colors.HexColor("#F3F6FA"), _NAVY),
        ("Files Optimized", _fmt(len(_sequence(metadata.get("generated_files")))), "Modified source files", colors.HexColor("#E9FAF3"), _GREEN),
        ("Parse Success %", parse_after, f"Before {parse_before}", colors.HexColor("#EAF3FF"), _CYAN),
        ("Total Workflow Time", _duration(workflow), "Measured components", colors.HexColor("#F0EDFF"), _PURPLE),
    ]
    # Keep the first-page headline metrics in a compact two-row card grid.
    card_cells = [
        [_card(*item[:3], item[3], styles, item[4]) for item in cards[index:index + 4]]
        for index in (0, 4)
    ]
    card_table = Table(card_cells, colWidths=[42 * mm] * 4, hAlign="LEFT")
    card_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    support = [
        ("Files discovered", f"{_fmt(before_metrics['files_discovered'])} → {_fmt(after_metrics['files_discovered'])}"),
        ("Parsed files", f"{_fmt(before_metrics['parsed_files'])} → {_fmt(after_metrics['parsed_files'])}"),
        ("Parse failures", f"{_fmt(before_metrics['parse_failures'])} → {_fmt(after_metrics['parse_failures'])}"),
        ("Project size", f"{_bytes(before_metrics['project_size_bytes'])} → {_bytes(after_metrics['project_size_bytes'])}"),
        ("Lines of code", f"{_fmt(before_metrics['lines_of_code'])} → {_fmt(after_metrics['lines_of_code'])}"),
        ("Original scan", _duration(_mapping(metadata.get("durations")).get("original_scan_seconds"))),
        ("AI generation", _duration(_mapping(metadata.get("durations")).get("ai_generation_seconds"))),
        ("Optimized rescan", _duration(_mapping(metadata.get("durations")).get("optimized_rescan_seconds"))),
        ("Critical issues", f"{_severity_counts(before_issues, baseline.get('debt_report'))['critical']} → {_severity_counts(after_issues, optimized.get('debt_report'))['critical']}"),
        ("High issues", f"{_severity_counts(before_issues, baseline.get('debt_report'))['high']} → {_severity_counts(after_issues, optimized.get('debt_report'))['high']}"),
        ("Code smells", f"{_code_smell_count(before_issues)} → {_code_smell_count(after_issues)}"),
        ("Security findings", f"{_category_count(before_issues, 'SECURITY')} → {_category_count(after_issues, 'SECURITY')}"),
    ]
    metric_cells = []
    for index in range(0, len(support), 3):
        row = []
        for label, value in support[index:index + 3]:
            row.append(Paragraph(
                f"<b>{_escape(label)}</b><br/>{_escape(value)}",
                styles["metric"],
            ))
        metric_cells.append(row)
    metric_table = Table(metric_cells, colWidths=[56 * mm] * 3, hAlign="LEFT")
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F8FC")),
        ("GRID", (0, 0), (-1, -1), 0.35, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    note = ParagraphStyle(
        "KpiNoteText", parent=styles["small"], fontName="Helvetica-Oblique",
        textColor=_MUTED, spaceBefore=4, spaceAfter=5,
    )
    return [
        Paragraph("KEY PERFORMANCE SNAPSHOT", styles["section"]),
        card_table,
        Spacer(1, 4),
        metric_table,
        Paragraph(
            "All values are populated from actual scan and optimization outputs. "
            "Debt-score improvement and issue-count reduction are separate measures.",
            note,
        ),
    ]


def _counts_by_rule(issues):
    result = {}
    for issue in issues:
        rule = str(issue.get("rule", "Unknown"))
        item = result.setdefault(rule, {"severity": issue.get("severity", "N/A"), "count": 0})
        item["count"] += 1
    return result


def _file_changes(metadata, before_issues, after_issues):
    files = _sequence(metadata.get("file_comparisons"))
    if not files:
        return [["File", "Size Before", "Size After", "Issues Before", "Issues After", "Result"],
                ["N/A", "N/A", "N/A", "N/A", "N/A", "No generated file comparison data"]]
    rows = [["File", "Size Before", "Size After", "Issues Before", "Issues After", "Result"]]
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "N/A"))
        before_code = str(item.get("before_code", ""))
        after_code = str(item.get("after_code", ""))
        before_count = sum(str(issue.get("file_path", "")).replace("\\", "/").endswith(path) for issue in before_issues)
        after_count = sum(str(issue.get("file_path", "")).replace("\\", "/").endswith(path) for issue in after_issues)
        status = "Updated" if before_code != after_code else "Unchanged"
        rows.append([
            path, _bytes(len(before_code.encode("utf-8"))),
            _bytes(len(after_code.encode("utf-8"))),
            str(before_count), str(after_count), status,
        ])
    return rows


def _issue_table(issues, status, limit=None):
    selected = issues[:limit] if limit is not None else issues
    rows = [["ID", "Rule", "Severity", "File / location", "Status"]]
    for issue in selected:
        file_location = str(issue.get("file_path") or issue.get("class_name") or "N/A")
        line = issue.get("line_number")
        if line not in (None, "", 0):
            file_location += f":{line}"
        rows.append([
            issue.get("rule_id") or "N/A",
            issue.get("rule") or "N/A",
            issue.get("severity") or "N/A",
            file_location,
            status,
        ])
    if len(rows) == 1:
        rows.append(["N/A", "N/A", "N/A", "N/A", "No issues"])
    return rows


def _summary_paragraph(baseline, optimized, comparison, before_issues, after_issues,
                       stack, project_name, styles):
    before_score = _score(baseline, comparison, "baseline_score")
    after_score = _score(optimized, comparison, "current_score")
    delta = after_score - before_score if before_score is not None and after_score is not None else None
    fixed = len(_sequence(_mapping(comparison).get("fixed_issues")))
    new = len(_sequence(_mapping(comparison).get("new_issues")))
    return Paragraph(
        f"<b>{_escape(project_name)}</b> was analyzed as a <b>{_escape(stack)}</b> project. "
        f"The baseline contained {_fmt(len(before_issues))} issues with a debt score of {_fmt(before_score, 1)}. "
        f"AI-assisted optimization processed the selected findings and the updated project was rescanned, "
        f"resulting in {_fmt(len(after_issues))} issues and a debt score of {_fmt(after_score, 1)}. "
        f"The measured score change was {_fmt(delta, 1)} points; the comparison reports "
        f"{fixed} fixed and {new} new issue(s). These are independent measures and should be reviewed "
        f"alongside the changed source files.",
        styles["body"],
    )


def _build_story(baseline_scan, optimized_scan, comparison, metadata, styles):
    baseline = _mapping(baseline_scan)
    optimized = _mapping(optimized_scan)
    comparison = _mapping(comparison)
    metadata = _mapping(metadata)
    before_issues, after_issues = _issues(baseline), _issues(optimized)
    before_metrics = _source_metrics(baseline, metadata, "before")
    after_metrics = _source_metrics(optimized, metadata, "after")
    before_severity = _severity_counts(before_issues, baseline.get("debt_report"))
    after_severity = _severity_counts(after_issues, optimized.get("debt_report"))
    project_name = baseline.get("project_name") or "Project"
    stack = _mapping(baseline.get("statistics")).get("stack", "N/A")
    story = [
        Paragraph("INTELLI CODE ANALYZER", styles["title"]),
        Paragraph("AI Technical Debt Analysis &amp; Optimization Comparison Report", styles["subtitle"]),
        Paragraph("Original Code Analysis | AI-Powered Refactoring | Before &amp; After Results", styles["tagline"]),
    ]
    story.extend(_kpi_section(
        baseline, optimized, comparison, metadata, before_metrics, after_metrics,
        before_issues, after_issues, styles,
    ))

    story.extend([
        Paragraph("Report Overview", styles["section"]),
        Paragraph(
            f"This report compares the original and AI-optimized scans for <b>{_escape(project_name)}</b> "
            f"using the <b>{_escape(stack)}</b> analyzer profile. It summarizes measured findings, "
            "source statistics, optimization output, and file-level changes.",
            styles["body"],
        ),
        Paragraph("Executive Summary", styles["section"]),
        _summary_paragraph(
            baseline, optimized, comparison, before_issues, after_issues,
            stack, project_name, styles,
        ),
    ])
    metric_rows = [["Key Metric", "Previous Code", "Current Code", "Change"]]
    before_total = _score(baseline, comparison, "baseline_score")
    after_total = _score(optimized, comparison, "current_score")
    metric_rows.extend([
        ["Debt score", _fmt(before_total, 1), _fmt(after_total, 1), _fmt(after_total - before_total, 1) if before_total is not None and after_total is not None else "N/A"],
        ["Total issues", str(len(before_issues)), str(len(after_issues)), _fmt(len(after_issues) - len(before_issues))],
    ])
    for severity in _SEVERITIES:
        metric_rows.append([
            severity.title(), _fmt(before_severity[severity]), _fmt(after_severity[severity]),
            _fmt((after_severity[severity] or 0) - (before_severity[severity] or 0)),
        ])
    metric_rows.extend([
        ["Code smells", str(_code_smell_count(before_issues)),
         str(_code_smell_count(after_issues)), "See category counts"],
        ["Security findings", str(_category_count(before_issues, "SECURITY")), str(_category_count(after_issues, "SECURITY")), "See category counts"],
        ["Files modified", _fmt(0), _fmt(len(_sequence(metadata.get("generated_files")))), _fmt(len(_sequence(metadata.get("generated_files"))))],
    ])
    story.append(_table(metric_rows, [42 * mm, 39 * mm, 39 * mm, 38 * mm], styles))

    story.extend([Paragraph("Project Overview", styles["section"]), Paragraph(
        f"The original project is identified as {_escape(project_name)}. "
        f"The selected analyzer profile is {_escape(stack)}; stack-aware measurements below are taken "
        "from the scan's corresponding metrics object when available.",
        styles["body"],
    )])
    build_before = _dependency_values(baseline)
    build_after = _dependency_values(optimized)
    overview = [["Attribute", "Original Project", "Optimized Project"]]
    for label, before, after in [
        ("Project name", baseline.get("project_name"), optimized.get("project_name")),
        ("Stack / language", _mapping(baseline.get("statistics")).get("language") or stack,
         _mapping(optimized.get("statistics")).get("language") or stack),
        ("Build configuration", build_before["build"], build_after["build"]),
        ("Files discovered", before_metrics["files_discovered"], after_metrics["files_discovered"]),
        ("Files parsed", before_metrics["parsed_files"], after_metrics["parsed_files"]),
        ("Parse failures", before_metrics["parse_failures"], after_metrics["parse_failures"]),
        ("Project size", _bytes(before_metrics["project_size_bytes"]), _bytes(after_metrics["project_size_bytes"])),
        ("Classes / interfaces", f"{_fmt(_mapping(baseline.get('statistics')).get('total_classes'))} / {_fmt(_mapping(baseline.get('statistics')).get('total_interfaces'))}",
         f"{_fmt(_mapping(optimized.get('statistics')).get('total_classes'))} / {_fmt(_mapping(optimized.get('statistics')).get('total_interfaces'))}"),
        ("Methods", _mapping(baseline.get("statistics")).get("total_methods"), _mapping(optimized.get("statistics")).get("total_methods")),
    ]:
        overview.append([label, before, after])
    story.append(_table(overview, [48 * mm, 74 * mm, 74 * mm], styles))

    story.extend([Paragraph("Codebase Statistics", styles["section"]), Paragraph(
        "Source line and file-size measures are collected from stack-supported source files; "
        "unsupported or unavailable values are reported as N/A.",
        styles["body"],
    )])
    added, removed = 0, 0
    file_comparisons = _sequence(metadata.get("file_comparisons"))
    for item in file_comparisons:
        if not isinstance(item, dict):
            continue
        before_lines = str(item.get("before_code", "")).splitlines()
        after_lines = str(item.get("after_code", "")).splitlines()
        diff = list(difflib.ndiff(before_lines, after_lines))
        added += sum(line.startswith("+ ") for line in diff)
        removed += sum(line.startswith("- ") for line in diff)
    code_stats = [["Metric", "Before", "After", "Change"]]
    before_stats, after_stats = _mapping(baseline.get("statistics")), _mapping(optimized.get("statistics"))
    for label, key in [
        ("Files parsed", "parsed_files"),
        ("Lines of code", "lines_of_code"),
        ("Comment lines", "comment_lines"),
        ("Blank lines", "blank_lines"),
        ("Classes", "total_classes"),
        ("Interfaces", "total_interfaces"),
        ("Methods", "total_methods"),
    ]:
        old = before_metrics.get(key) if key in before_metrics else before_stats.get(key)
        new = after_metrics.get(key) if key in after_metrics else after_stats.get(key)
        old_number, new_number = _number(old), _number(new)
        delta = _fmt(new_number - old_number) if old_number is not None and new_number is not None else "N/A"
        code_stats.append([label, _fmt(old), _fmt(new), delta])
    code_stats.extend([
        ["Project size", _bytes(before_metrics["project_size_bytes"]), _bytes(after_metrics["project_size_bytes"]), "See values"],
        ["Files modified", "0", _fmt(len(_sequence(metadata.get("generated_files")))), _fmt(len(_sequence(metadata.get("generated_files"))))],
        ["Changed lines (added / removed)", "N/A", f"{added} / {removed}", "Generated file diffs"],
    ])
    story.append(_table(code_stats, [50 * mm, 42 * mm, 42 * mm, 42 * mm], styles))

    before_rules, after_rules = _counts_by_rule(before_issues), _counts_by_rule(after_issues)
    story.extend([Paragraph("Code Smell Analysis", styles["section"]), Paragraph(
        f"Code-smell counts include non-security source-analysis findings. "
        f"The scan reported {_code_smell_count(before_issues)} "
        "such finding(s) before and "
        f"{_code_smell_count(after_issues)} after optimization.",
        styles["body"],
    )])
    smell_rows = [["Rule", "Severity", "Before", "After", "Status"]]
    smell_rules = sorted(set(before_rules) | set(after_rules))
    for rule in smell_rules:
        if not any(
            str(issue.get("rule")) == rule
            and str(issue.get("category", "")).upper() != "SECURITY"
            for issue in before_issues + after_issues
        ):
            continue
        old, new = before_rules.get(rule, {}).get("count", 0), after_rules.get(rule, {}).get("count", 0)
        smell_rows.append([rule, (before_rules.get(rule) or after_rules.get(rule))["severity"], str(old), str(new),
                           "Improved" if new < old else "Increased" if new > old else "Unchanged"])
    if len(smell_rows) == 1:
        smell_rows.append(["N/A", "N/A", "N/A", "N/A", "No classified code smells"])
    story.append(_table(smell_rows, [58 * mm, 28 * mm, 24 * mm, 24 * mm, 42 * mm], styles))
    representative = next((issue for issue in comparison.get("fixed_issues", []) if isinstance(issue, dict)), None)
    if representative is None and before_issues:
        representative = before_issues[0]
    story.extend([
        Paragraph("4.1 Representative Issue Example", styles["subsection"]),
        Paragraph(
            f"Rule: {_escape((representative or {}).get('rule', 'N/A'))}; "
            f"severity: {_escape((representative or {}).get('severity', 'N/A'))}; "
            f"location: {_escape((representative or {}).get('file_path') or (representative or {}).get('class_name') or 'N/A')}. "
            f"{_escape((representative or {}).get('message', 'No issue example is available in the scan output.'))}",
            styles["body"],
        ),
    ])

    story.extend([Paragraph("Technical Debt Analysis", styles["section"]), Paragraph(
        "Debt score is read from the scan report. Score delta is current minus baseline; "
        "improvement is (baseline score - current score) / baseline score × 100 when baseline is positive. "
        "Issue-count delta is current issues minus baseline issues.",
        styles["body"],
    )])
    severity_rows = [["Severity", "Before", "After", "Delta"]]
    for severity in _SEVERITIES:
        old, new = before_severity[severity], after_severity[severity]
        severity_rows.append([severity.title(), _fmt(old), _fmt(new), _fmt((new or 0) - (old or 0))])
    severity_rows.append(["TOTAL", str(len(before_issues)), str(len(after_issues)), str(len(after_issues) - len(before_issues))])
    story.append(_table(severity_rows, [45 * mm, 45 * mm, 45 * mm, 45 * mm], styles))

    q_before, q_after = _quality_values(baseline), _quality_values(optimized)
    story.extend([Paragraph("Code Quality and Maintainability", styles["section"]), Paragraph(
        f"Quality metrics are derived from parsed class and method objects. Stack-specific metrics: "
        f"{'; '.join(_stack_metrics(baseline))}.",
        styles["body"],
    )])
    quality_rows = [["Metric", "Before", "After", "Interpretation"]]
    for key, label in [
        ("average_complexity", "Cyclomatic complexity (average)"),
        ("maximum_complexity", "Cyclomatic complexity (maximum)"),
        ("methods_over_threshold", "Methods above complexity threshold (10)"),
        ("average_coupling", "Average class fan-out"),
        ("duplication", "Duplication percentage"),
    ]:
        old, new = q_before[key], q_after[key]
        interpretation = "Lower is generally preferable" if old is not None and new is not None else "N/A: metric not emitted by this stack"
        quality_rows.append([label, _fmt(old, 2), _fmt(new, 2), interpretation])
    story.append(_table(quality_rows, [61 * mm, 30 * mm, 30 * mm, 59 * mm], styles))

    dep_before, dep_after = _dependency_values(baseline), _dependency_values(optimized)
    story.extend([Paragraph("Dependency Analysis", styles["section"]), Paragraph(
        "Dependency totals and outdated-package counts use the dependency scanner output where available. "
        "Node.js package counts come from the Node stack analyzer. N/A means the scan did not provide that measure.",
        styles["body"],
    ), _table([
        ["Metric", "Before", "After"],
        ["Build configuration", dep_before["build"], dep_after["build"]],
        ["Total dependencies", _fmt(dep_before["total"]), _fmt(dep_after["total"])],
        ["Outdated dependencies", _fmt(dep_before["outdated"]), _fmt(dep_after["outdated"])],
        ["Vulnerable / high-risk dependencies", _fmt(dep_before["vulnerable"]), _fmt(dep_after["vulnerable"])],
    ], [75 * mm, 65 * mm, 65 * mm], styles)])

    story.extend([Paragraph("Security Analysis", styles["section"]), Paragraph(
        "Source-code security findings are counted from issue categories. Dependency vulnerability totals are shown "
        "separately so source rules and package advisories are not conflated.",
        styles["body"],
    )])
    security_rows = [["Source finding severity", "Before", "After"]]
    for severity in _SEVERITIES:
        security_rows.append([
            severity.title(),
            str(sum(str(issue.get("category", "")).upper() == "SECURITY" and str(issue.get("severity", "")).lower() == severity for issue in before_issues)),
            str(sum(str(issue.get("category", "")).upper() == "SECURITY" and str(issue.get("severity", "")).lower() == severity for issue in after_issues)),
        ])
    security_rows.extend([
        ["Dependency advisories", _fmt(dep_before["vulnerable"]), _fmt(dep_after["vulnerable"])],
        ["Outdated dependencies", _fmt(dep_before["outdated"]), _fmt(dep_after["outdated"])],
    ])
    story.append(_table(security_rows, [75 * mm, 65 * mm, 65 * mm], styles))

    durations = _mapping(metadata.get("durations"))
    story.extend([Paragraph("AI Optimization Summary", styles["section"]), Paragraph(
        "AI optimization results include completed generation attempts, modified files, and per-issue failures. "
        "A generated file is not proof that every associated issue was resolved; the optimized rescan is the validation source.",
        styles["body"],
    )])
    ai_rows = [
        ["Metric", "Measured value"],
        ["Configured provider / model", f"{metadata.get('provider', 'N/A')} / {metadata.get('model', 'N/A')}"],
        ["Issues selected", _fmt(metadata.get("issues_selected"))],
        ["Files processed / modified", f"{_fmt(metadata.get('files_processed'))} / {_fmt(metadata.get('files_modified'))}"],
        ["Failed issue generations", _fmt(metadata.get("failed_issues"))],
        ["AI generation duration", _duration(durations.get("ai_generation_seconds"))],
        ["Optimized rescan duration", _duration(durations.get("optimized_rescan_seconds"))],
    ]
    story.append(_table(ai_rows, [90 * mm, 115 * mm], styles))
    file_rows = [["File", "Issue Addressed", "Result"]]
    selected_by_file = {}
    for issue in _sequence(metadata.get("selected_issues")):
        if isinstance(issue, dict):
            selected_by_file.setdefault(str(issue.get("file_path", "N/A")), []).append(str(issue.get("rule", "Finding")))
    for path in metadata.get("generated_files") or []:
        rules = selected_by_file.get(path, [])
        file_rows.append([path, ", ".join(rules) or "Selected issue(s)", "Generated"])
    for failure in _sequence(metadata.get("failed_issue_details")):
        if isinstance(failure, dict):
            issue = _mapping(failure.get("issue"))
            file_rows.append([
                issue.get("file_path", "N/A"), issue.get("rule", "Finding"),
                "Failed: " + str(failure.get("error", "N/A")),
            ])
    if len(file_rows) == 1:
        file_rows.append(["N/A", "N/A", "No generated files"])
    story.append(_table(file_rows, [60 * mm, 70 * mm, 75 * mm], styles))

    story.extend([Paragraph("Before and After Issue Comparison", styles["section"]), Paragraph(
        "Fixed means an issue key present in the baseline is absent in the optimized scan. New means the issue key "
        "appears only after optimization. Still present means a matching issue remains. Improved class counts are "
        "based on total findings per class.",
        styles["body"],
    )])
    summary_rows = [["Status", "Count"], ["Fixed", str(len(_sequence(comparison.get("fixed_issues"))))],
                    ["New", str(len(_sequence(comparison.get("new_issues"))))],
                    ["Still present", str(len(_sequence(comparison.get("still_present"))))],
                    ["Improved classes", str(len(_sequence(comparison.get("improved_classes"))))],
                    ["Worsened classes", str(len(_sequence(comparison.get("worsened_classes"))))]]
    story.append(_table(summary_rows, [100 * mm, 60 * mm], styles))
    for title, key in [("Sample fixed issues", "fixed_issues"), ("Sample new issues", "new_issues"),
                       ("Sample still-present issues", "still_present")]:
        story.append(Paragraph(title, styles["subsection"]))
        status = "Fixed" if key == "fixed_issues" else "New" if key == "new_issues" else "Still present"
        story.append(_table(_issue_table(_sequence(comparison.get(key)), status, limit=10),
                            [24 * mm, 38 * mm, 23 * mm, 82 * mm, 37 * mm], styles))

    workflow = _mapping(metadata.get("durations"))
    efficiency_rows = [["Efficiency metric", "Value"],
                       ["Original scan duration", _duration(workflow.get("original_scan_seconds"))],
                       ["Files discovered (before / after)", f"{_fmt(before_metrics['files_discovered'])} / {_fmt(after_metrics['files_discovered'])}"],
                       ["Files parsed (before / after)", f"{_fmt(before_metrics['parsed_files'])} / {_fmt(after_metrics['parsed_files'])}"],
                       ["Parse success (before / after)", f"{_percent(before_metrics['parsed_files'], before_metrics['files_discovered'])} / {_percent(after_metrics['parsed_files'], after_metrics['files_discovered'])}"],
                       ["AI generation duration", _duration(workflow.get("ai_generation_seconds"))],
                       ["Optimized rescan duration", _duration(workflow.get("optimized_rescan_seconds"))],
                       ["Comparison duration", _duration(workflow.get("comparison_seconds"))],
                       ["Total workflow duration", _duration(workflow.get("total_workflow_seconds"))]]
    story.extend([Paragraph("Analysis and Optimization Efficiency", styles["section"]), Paragraph(
        "Workflow time is the sum of measured original scan, AI generation, optimized rescan, and comparison durations; "
        "it excludes user wait time outside those operations.",
        styles["body"],
    ), _table(efficiency_rows, [100 * mm, 100 * mm], styles)])

    story.extend([Paragraph("File-Level Change Summary", styles["section"]), Paragraph(
        "File sizes and issue counts are shown for files returned by the optimization service. "
        "The generated result is based on the output source content.",
        styles["body"],
    ), _table(_file_changes(metadata, before_issues, after_issues),
              [62 * mm, 26 * mm, 26 * mm, 28 * mm, 28 * mm, 30 * mm], styles)])

    before_by_class, after_by_class = {}, {}
    for issue in before_issues:
        before_by_class[str(issue.get("class_name", "N/A"))] = before_by_class.get(str(issue.get("class_name", "N/A")), 0) + 1
    for issue in after_issues:
        after_by_class[str(issue.get("class_name", "N/A"))] = after_by_class.get(str(issue.get("class_name", "N/A")), 0) + 1
    class_rows = [["Class / component", "Before findings", "After findings", "Status"]]
    for name in sorted(set(before_by_class) | set(after_by_class)):
        old, new = before_by_class.get(name, 0), after_by_class.get(name, 0)
        class_rows.append([name, str(old), str(new), "Improved" if new < old else "Worsened" if new > old else "Unchanged"])
    if len(class_rows) == 1:
        class_rows.append(["N/A", "N/A", "N/A", "No class-level findings"])
    story.extend([Paragraph("Class and Method Analysis", styles["section"]), Paragraph(
        "Class and method rows aggregate findings from analyzer issue records. Stacks without class-based parser results "
        "are represented by the analyzer's component/file names.",
        styles["body"],
    ), _table(class_rows, [82 * mm, 38 * mm, 38 * mm, 42 * mm], styles)])

    story.extend([Paragraph("Reliability and Detection Coverage", styles["section"]), Paragraph(
        "Parse success describes successfully parsed files relative to discovered source files, not defect-detection "
        "accuracy. Precision, recall, and F1 require a verified ground-truth issue set and are therefore reported as N/A.",
        styles["body"],
    ), _table([
        ["Coverage metric", "Before", "After"],
        ["Files discovered", _fmt(before_metrics["files_discovered"]), _fmt(after_metrics["files_discovered"])],
        ["Files parsed", _fmt(before_metrics["parsed_files"]), _fmt(after_metrics["parsed_files"])],
        ["Parse success", _percent(before_metrics["parsed_files"], before_metrics["files_discovered"]),
         _percent(after_metrics["parsed_files"], after_metrics["files_discovered"])],
        ["Parse failures", _fmt(before_metrics["parse_failures"]), _fmt(after_metrics["parse_failures"])],
        ["Precision / recall / F1", "N/A", "N/A"],
    ], [75 * mm, 65 * mm, 65 * mm], styles)])

    recommendations = []
    if _number(after_metrics["parse_failures"]) and _number(after_metrics["parse_failures"]) > 0:
        recommendations.append("Resolve parse failures and rerun the analysis to improve source coverage.")
    if _category_count(after_issues, "SECURITY") > 0:
        recommendations.append("Prioritize remaining security findings and verify fixes with stack-specific security tests.")
    if _number(dep_after["outdated"]) and _number(dep_after["outdated"]) > 0:
        recommendations.append("Review outdated dependencies and confirm compatible safe-version upgrades.")
    if _sequence(metadata.get("failed_issue_details")):
        recommendations.append("Review failed AI-generation entries; manually inspect those files before release.")
    if not recommendations:
        recommendations.append("Review all generated file changes, run the project's test suite, and monitor the next scan for regressions.")
    recommendation_rows = [[f"• {item}"] for item in recommendations]
    story.extend([Paragraph("Recommendations", styles["section"]), Table(
        [[_paragraph(row[0], styles["body"])] for row in recommendation_rows],
        colWidths=[180 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FC")),
            ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    )])

    before_score = _score(baseline, comparison, "baseline_score")
    after_score = _score(optimized, comparison, "current_score")
    score_improvement = (
        (before_score - after_score) / before_score * 100
        if before_score is not None and after_score is not None and before_score > 0
        else 0 if before_score == 0 else None
    )
    final_rows = [
        ["Final metric", "Result"],
        ["Score change (after - before)", _fmt(after_score - before_score, 1) if before_score is not None and after_score is not None else "N/A"],
        ["Score improvement", f"{score_improvement:.1f}%" if score_improvement is not None else "N/A"],
        ["Issue-count change (after - before)", str(len(after_issues) - len(before_issues))],
        ["Fixed / new / still present", f"{len(_sequence(comparison.get('fixed_issues')))} / {len(_sequence(comparison.get('new_issues')))} / {len(_sequence(comparison.get('still_present')))}"],
        ["Files modified", _fmt(len(_sequence(metadata.get("generated_files"))))],
        ["Status", "Review generated changes and run project validation"],
    ]
    story.extend([Paragraph("Final Summary", styles["section"]), Paragraph(
        "The figures below summarize the measured comparison. AI-generated code should be reviewed and validated before use.",
        styles["body"],
    ), _table(final_rows, [95 * mm, 105 * mm], styles)])

    statuses = {}
    for name, key in (("Fixed", "fixed_issues"), ("New", "new_issues"), ("Still present", "still_present")):
        for issue in _sequence(comparison.get(key)):
            if isinstance(issue, dict):
                statuses.setdefault((
                    issue.get("rule_id"), issue.get("rule"), issue.get("file_path"),
                    issue.get("line_number"), issue.get("class_name"),
                ), name)
    appendix = [["ID", "Rule", "Severity", "File / location", "Status"]]
    for issue in before_issues + after_issues:
        key = (issue.get("rule_id"), issue.get("rule"), issue.get("file_path"),
               issue.get("line_number"), issue.get("class_name"))
        file_location = str(issue.get("file_path") or issue.get("class_name") or "N/A")
        if issue.get("line_number"):
            file_location += f":{issue['line_number']}"
        appendix.append([
            issue.get("rule_id") or "N/A", issue.get("rule") or "N/A",
            issue.get("severity") or "N/A", file_location,
            statuses.get(key, "Still present" if key in statuses else "Current finding"),
        ])
    if len(appendix) == 1:
        appendix.append(["N/A", "N/A", "N/A", "N/A", "No issues"])
    story.extend([Paragraph("Detailed Issue Appendix", styles["section"]), Paragraph(
        "The appendix lists issues returned by the baseline and optimized scans. Production use should include full "
        "issue descriptions, remediation guidance, and code context where available.",
        styles["body"],
    ), _table(appendix, [26 * mm, 42 * mm, 24 * mm, 77 * mm, 31 * mm], styles)])

    story.extend([Paragraph("Report Definitions and Notes", styles["section"]), Paragraph(
        "<b>Previous code</b> means the baseline scan. <b>Current code</b> means the optimized rescan. "
        "<b>Delta</b> is current minus baseline unless labeled otherwise. <b>Improvement percentage</b> is "
        "(baseline score - current score) / baseline score × 100 for a positive baseline score. "
        "<b>Fixed</b> means a baseline issue key is no longer present in the optimized scan. "
        "<b>N/A</b> indicates the metric was not available in the supplied scan output; it is not estimated. "
        "AI-generated changes are suggestions and require human review, tests, and deployment-specific validation.",
        styles["body"],
    )])
    return story


def generate_comparison_report(
    baseline_scan: dict,
    optimized_scan: dict,
    comparison: dict,
    optimization_meta: dict,
) -> Path:
    """Generate a PDF comparison report and return its persisted path."""
    project_name = str(_mapping(baseline_scan).get("project_name") or "project")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", project_name).strip("._-") or "project"
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = REPORT_OUTPUT_DIR / f"{safe_name}_{timestamp}_comparison.pdf"
    styles = _styles()

    def page_footer(canvas, document):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(_LINE)
        canvas.line(15 * mm, 13 * mm, width - 15 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(15 * mm, 8 * mm, "Intelli Code Analyzer | AI Technical Debt Analysis")
        canvas.drawRightString(width - 15 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = BaseDocTemplate(
        str(output_path), pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=13 * mm, bottomMargin=18 * mm,
        title="Intelli Code Analyzer Comparison Report",
        author="Intelli Code Analyzer",
    )
    frame = Frame(
        document.leftMargin, document.bottomMargin,
        document.width, document.height, id="normal",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    document.addPageTemplates([
        PageTemplate(id="report", frames=[frame], onPage=page_footer)
    ])
    document.build(_build_story(
        baseline_scan, optimized_scan, comparison, optimization_meta, styles,
    ))
    return output_path
