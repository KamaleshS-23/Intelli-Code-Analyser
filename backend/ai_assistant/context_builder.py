from __future__ import annotations


def _safe_list(items):
    return items if isinstance(items, list) else []


def _extract_root_issue(issue: dict, index: int = 0):
    rule = issue.get("rule") or issue.get("name") or f"Issue {index + 1}"
    severity = issue.get("severity") or "medium"
    class_name = issue.get("class_name") or issue.get("className") or "UnknownClass"
    return {
        "rule": rule,
        "rule_id": issue.get("rule_id") or "",
        "severity": severity,
        "category": issue.get("category") or "",
        "language": issue.get("language") or "",
        "class_name": class_name,
        "file_path": issue.get("file_path") or "",
        "method_name": issue.get("method_name") or issue.get("methodName") or "",
        "message": issue.get("message") or "",
        "suggestion": issue.get("suggestion") or "",
        "metric_value": issue.get("metric_value"),
        "threshold": issue.get("threshold", issue.get("metric_threshold")),
        "line_number": issue.get("line_number") or 0,
        "column": issue.get("column") or 0,
        "refactoring_pattern": issue.get("refactoring_pattern") or "",
        "estimated_fix_minutes": issue.get("estimated_fix_minutes") or 0,
        "layer": issue.get("layer") or "",
        "django_version_aware": bool(issue.get("django_version_aware", False)),
        "node_version_aware": bool(issue.get("node_version_aware", False)),
        "framework": issue.get("framework"),
        "code_snippet": issue.get("code_snippet") or "",
    }


def _extract_web_analysis(statistics: dict) -> dict | None:
    analysis = statistics.get("web_analysis")
    if not isinstance(analysis, dict):
        return None
    metrics = analysis.get("metrics") or {}
    web_metrics = {
        language: (metrics.get(language) or {}).get("totals") or {}
        for language in ("html", "css", "javascript")
    }
    web_metrics["coupling"] = list((metrics.get("coupling") or {}).items())[:10]
    return {
        "summary": analysis.get("summary") or {},
        "metrics": web_metrics,
    }


def extract_django_analysis(statistics: dict) -> dict | None:
    analysis = statistics.get("django_analysis")
    if not isinstance(analysis, dict):
        return None
    metrics = analysis.get("metrics") or {}
    orm = metrics.get("orm") or {}
    query_counts = orm.get("queries_per_function") or {}
    view_files = metrics.get("views") or {}
    template_files = metrics.get("templates") or {}
    template_totals = {
        key: sum(item.get(key, 0) for item in template_files.values())
        for key in (
            "lines", "if_blocks", "for_blocks", "include_tags", "extends_tags",
            "blocks", "static_uses", "url_uses", "safe_filters", "inline_scripts",
            "inline_styles",
        )
    }
    return {
        "summary": analysis.get("summary") or {},
        "metrics": {
            "django_version": metrics.get("django_version"),
            "orm": {
                "n_plus_one_risk": orm.get("n_plus_one_risk", 0),
                "query_function_count": len(query_counts),
                "query_count": sum(query_counts.values()),
                "top_query_functions": sorted(
                    query_counts.items(), key=lambda item: item[1], reverse=True
                )[:10],
            },
            "views": {
                "file_count": len(view_files),
                "view_count": sum(item.get("view_count", 0) for item in view_files.values()),
                "max_view_loc": max(
                    (item.get("max_view_loc", 0) for item in view_files.values()),
                    default=0,
                ),
                "files": list(view_files.items())[:10],
            },
            "templates": {"file_count": len(template_files), "totals": template_totals},
            "architecture": metrics.get("architecture") or {},
        },
    }


def extract_node_analysis(statistics: dict) -> dict | None:
    analysis = statistics.get("node_analysis")
    if not isinstance(analysis, dict):
        return None
    metrics = analysis.get("metrics") or {}
    async_files = metrics.get("async") or {}
    security_files = metrics.get("security") or {}
    route_files = metrics.get("routes") or {}
    return {
        "summary": analysis.get("summary") or {},
        "framework": analysis.get("framework") or "none",
        "metrics": {
            "packages": metrics.get("packages") or {},
            "dependencies": metrics.get("dependencies") or {},
            "async": {
                "files": len(async_files),
                "await_count": sum(item.get("await_count", 0) for item in async_files.values()),
                "then_count": sum(item.get("then_count", 0) for item in async_files.values()),
                "catch_count": sum(item.get("catch_count", 0) for item in async_files.values()),
                "callback_nesting_max": max(
                    (item.get("callback_nesting_max", 0) for item in async_files.values()),
                    default=0,
                ),
            },
            "routes": {
                "files": len(route_files),
                "route_count": sum(item.get("route_count", 0) for item in route_files.values()),
                "write_count": sum(item.get("writes", 0) for item in route_files.values()),
            },
            "security": {
                "files": len(security_files),
                "eval_calls": sum(item.get("eval_calls", 0) for item in security_files.values()),
                "exec_calls": sum(item.get("exec_calls", 0) for item in security_files.values()),
                "hardcoded_secrets": sum(
                    item.get("hardcoded_secrets", 0) for item in security_files.values()
                ),
            },
        },
    }


def build_project_context(scan_result: dict | None, request_context: dict | None = None) -> dict:
    if not scan_result:
        return {
            "project": {"name": "unknown", "language": "unknown", "stack": "unknown"},
            "summary": {"files": 0, "classes": 0, "methods": 0},
            "technical_debt": {"score": 0, "issues": 0},
            "findings": [],
            "dependencies": [],
            "graph": {},
            "selected": request_context or {},
            "evidence": [],
        }

    classes = _safe_list(scan_result.get("classes"))
    methods = []
    for cls in classes:
        for method in _safe_list(cls.get("methods")):
            methods.append({
                "class_name": cls.get("package", "") + "." + cls.get("name", ""),
                "name": method.get("name"),
                "line_count": method.get("line_count"),
                "cyclomatic_complexity": method.get("cyclomatic_complexity"),
            })

    debt_report = scan_result.get("debt_report") or {}
    issues = [_extract_root_issue(issue, index) for index, issue in enumerate(_safe_list(debt_report.get("issues")))]
    dependency_report = scan_result.get("dependency_report") or {}
    project_statistics = scan_result.get("statistics") or {}
    graph_summary = project_statistics.get("graph") or {}
    languages = project_statistics.get("languages") or []
    language = project_statistics.get("language") or (
        ", ".join(languages) if languages else "unknown"
    )

    project = {
        "name": scan_result.get("project_name") or "Unknown Project",
        "language": language,
        "stack": project_statistics.get("stack") or "unknown",
        "build_system": dependency_report.get("build_tool") or "unknown",
        "path": scan_result.get("project_path") or "",
    }

    summary = {
        "files": project_statistics.get("parsed_files") or 0,
        "classes": project_statistics.get("total_classes") or len(classes),
        "methods": len(methods),
        "dependencies": project_statistics.get("dependency_edges") or 0,
    }

    technical_debt = {
        "score": debt_report.get("total_score") or 0,
        "issues": len(issues),
        "severity_counts": debt_report.get("severity_counts") or {},
        "top_offenders": _safe_list(debt_report.get("top_offenders"))[:5],
    }
    web_analysis = _extract_web_analysis(project_statistics)
    if web_analysis:
        technical_debt["web_analysis"] = web_analysis
    django_analysis = extract_django_analysis(project_statistics)
    if django_analysis:
        technical_debt["django_analysis"] = django_analysis
    node_analysis = extract_node_analysis(project_statistics)
    if node_analysis:
        technical_debt["node_analysis"] = node_analysis

    evidence = []
    for issue in issues[:5]:
        if issue.get("class_name"):
            evidence.append({
                "class_name": issue.get("class_name"),
                "rule": issue.get("rule"),
                "severity": issue.get("severity"),
                "message": issue.get("message"),
                "line_number": issue.get("line_number"),
            })

    selected = request_context or {
        "file": "",
        "class": "",
        "method": "",
        "finding_id": "",
    }

    return {
        "project": project,
        "summary": summary,
        "technical_debt": technical_debt,
        "findings": issues,
        "dependencies": _safe_list(dependency_report.get("dependencies")),
        "graph": graph_summary,
        "selected": selected,
        "evidence": evidence,
        "project_file_count": summary["files"],
        "project_class_count": summary["classes"],
    }
