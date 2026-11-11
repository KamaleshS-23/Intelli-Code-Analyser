def _safe_list(value):
    return value if isinstance(value, list) else []


def get_project_summary(scan_result):
    if not scan_result:
        return {"project_name": "Unknown", "files": 0, "classes": 0, "methods": 0}

    stats = scan_result.get("statistics") or {}
    classes = _safe_list(scan_result.get("classes"))
    method_count = sum(len(_safe_list(cls.get("methods"))) for cls in classes)

    return {
        "project_name": scan_result.get("project_name") or "Unknown",
        "stack": stats.get("stack") or "unknown",
        "language": stats.get("language") or ", ".join(stats.get("languages") or []) or "unknown",
        "files": stats.get("parsed_files") or 0,
        "classes": stats.get("total_classes") or len(classes),
        "methods": method_count,
        "dependencies": stats.get("dependency_edges") or 0,
        "debt_score": (scan_result.get("debt_report") or {}).get("total_score") or 0,
        "web_analysis": (
            (stats.get("web_analysis") or {}).get("summary")
            if isinstance(stats.get("web_analysis"), dict)
            else None
        ),
        "django_analysis": (
            (stats.get("django_analysis") or {}).get("summary")
            if isinstance(stats.get("django_analysis"), dict)
            else None
        ),
        "node_analysis": (
            {
                "framework": (stats.get("node_analysis") or {}).get("framework"),
                **((stats.get("node_analysis") or {}).get("summary") or {}),
            }
            if isinstance(stats.get("node_analysis"), dict)
            else None
        ),
    }


def get_project_statistics(scan_result):
    stats = (scan_result or {}).get("statistics") or {}
    debt = (scan_result or {}).get("debt_report") or {}
    return {
        "statistics": stats,
        "severity_counts": debt.get("severity_counts") or {},
        "rule_counts": debt.get("rule_counts") or {},
        "top_offenders": _safe_list(debt.get("top_offenders"))[:5],
    }


def get_technical_debt_summary(scan_result):
    debt = (scan_result or {}).get("debt_report") or {}
    issues = _safe_list(debt.get("issues"))
    summary = {
        "score": debt.get("total_score") or 0,
        "count": len(issues),
        "severity_counts": debt.get("severity_counts") or {},
        "top_offenders": _safe_list(debt.get("top_offenders"))[:5],
    }
    return summary


def get_top_issues(scan_result, limit=5):
    debt = (scan_result or {}).get("debt_report") or {}
    issues = _safe_list(debt.get("issues"))
    return issues[:limit]


def get_class_details(scan_result, class_name):
    classes = _safe_list(scan_result.get("classes")) if scan_result else []
    for cls in classes:
        fqcn = f"{cls.get('package', '')}.{cls.get('name', '')}" if cls.get('package') else cls.get('name', '')
        if fqcn == class_name or cls.get("name") == class_name:
            return {
                "class": cls,
                "methods": _safe_list(cls.get("methods")),
                "fields": _safe_list(cls.get("fields")),
            }
    return {"class": None, "methods": [], "fields": []}


def get_method_details(scan_result, class_name, method_name):
    match = get_class_details(scan_result, class_name)
    cls = match.get("class")
    if not cls:
        return None
    for method in _safe_list(cls.get("methods")):
        if method.get("name") == method_name:
            return method
    return None


def find_high_complexity_methods(scan_result, threshold=10):
    findings = []
    for cls in _safe_list((scan_result or {}).get("classes")):
        for method in _safe_list(cls.get("methods")):
            complexity = method.get("cyclomatic_complexity") or 0
            if complexity >= threshold:
                findings.append({
                    "class_name": f"{cls.get('package', '')}.{cls.get('name')}",
                    "method_name": method.get("name"),
                    "complexity": complexity,
                    "line_count": method.get("line_count"),
                })
    return findings


def find_high_coupling_classes(scan_result, threshold=3):
    metrics = ((scan_result or {}).get("statistics") or {}).get("graph", {}).get("coupling_metrics") or {}
    matches = []
    for class_name, values in metrics.items():
        ca = values.get("afferent_coupling") or 0
        ce = values.get("efferent_coupling") or 0
        total = ca + ce
        if total >= threshold:
            matches.append({"class_name": class_name, "ca": ca, "ce": ce, "total": total})
    return sorted(matches, key=lambda item: item["total"], reverse=True)


def find_vulnerable_dependencies(scan_result):
    dependency_report = (scan_result or {}).get("dependency_report") or {}
    return _safe_list(dependency_report.get("outdated_dependencies"))


def search_code(scan_result, query):
    query = (query or "").strip().lower()
    if not query or not scan_result:
        return []

    matches = []
    for cls in _safe_list(scan_result.get("classes")):
        class_text = (cls.get("name") or "") + " " + str(cls.get("package") or "")
        if query in class_text.lower():
            matches.append({"type": "class", "name": cls.get("name"), "package": cls.get("package")})
            continue
        for method in _safe_list(cls.get("methods")):
            method_text = (method.get("name") or "") + " " + str(method.get("return_type") or "")
            if query in method_text.lower():
                matches.append({
                    "type": "method",
                    "class_name": f"{cls.get('package', '')}.{cls.get('name')}",
                    "method_name": method.get("name"),
                })
    return matches


def get_file_findings(scan_result, file_path):
    debt = (scan_result or {}).get("debt_report") or {}
    findings = []
    for issue in _safe_list(debt.get("issues")):
        if issue.get("file_path") == file_path:
            findings.append(issue)
    return findings


def get_knowledge_graph_data(scan_result):
    stats = (scan_result or {}).get("statistics") or {}
    graph = stats.get("graph") or {}
    coupling = graph.get("coupling_metrics") or {}
    edges = _safe_list(graph.get("edges"))
    nodes = _safe_list(graph.get("nodes"))
    cycles = _safe_list(graph.get("circular_dependencies"))

    if not edges and scan_result:
        dep_graph = (scan_result or {}).get("dependency_graph") or {}
        edges = _safe_list(dep_graph.get("edges"))
        nodes = _safe_list(dep_graph.get("nodes"))
        cycles = _safe_list(dep_graph.get("circular_dependencies"))

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "edges": edges[:15],
        "circular_dependencies": cycles,
        "coupling_summary": [
            {
                "class": cls_name,
                "fan_in": metrics.get("afferent_coupling", 0),
                "fan_out": metrics.get("efferent_coupling", 0),
                "instability": round(metrics.get("instability", 0), 2),
            }
            for cls_name, metrics in list(coupling.items())[:10]
        ],
    }


def get_root_cause_context(scan_result):
    debt = (scan_result or {}).get("debt_report") or {}
    issues = _safe_list(debt.get("issues"))

    root_causes = []
    god_classes = [i for i in issues if "godclass" in str(i.get("rule", "")).lower()]
    circular = [i for i in issues if "circular" in str(i.get("rule", "")).lower()]
    complex_methods = [i for i in issues if "complexity" in str(i.get("rule", "")).lower() or "longmethod" in str(i.get("rule", "")).lower()]
    coupling_issues = [i for i in issues if "coupling" in str(i.get("rule", "")).lower() or "featureenvy" in str(i.get("rule", "")).lower()]

    if god_classes:
        root_causes.append({
            "category": "Architectural Bloat / Single Responsibility Principle Violation",
            "classes": [i.get("class_name") for i in god_classes],
            "why": "Business logic, persistence, and coordination merged into single classes over time without modular decomposition.",
        })
    if circular:
        root_causes.append({
            "category": "Circular Dependency / Missing Abstraction Layer",
            "details": [i.get("message") for i in circular],
            "why": "Services directly instantiate or reference each other instead of depending on shared abstractions or event-driven interfaces.",
        })
    if complex_methods:
        root_causes.append({
            "category": "Excessive Branching / Procedural Nesting",
            "count": len(complex_methods),
            "why": "Multiple validation rules, business policies, and fallback cases accumulated linearly inside individual methods.",
        })
    if coupling_issues:
        root_causes.append({
            "category": "Feature Envy / Inverted Information Architecture",
            "details": [i.get("message") for i in coupling_issues],
            "why": "Methods access fields and methods of external objects more than their own class data, indicating misallocated responsibilities.",
        })

    return root_causes


def validate_java_code(java_code: str) -> dict:
    if not java_code or not java_code.strip():
        return {"valid": False, "error": "Empty code snippet provided."}

    import javalang
    try:
        tree = javalang.parse.parse(java_code)
        classes_found = [c.name for c in getattr(tree, "types", []) if hasattr(c, "name")]
        methods_found = []
        for type_decl in getattr(tree, "types", []):
            for method in getattr(type_decl, "methods", []):
                methods_found.append(method.name)

        return {
            "valid": True,
            "status": "PASSED",
            "classes": classes_found,
            "methods": methods_found,
            "message": f"Successfully parsed {len(classes_found)} class(es) and {len(methods_found)} method(s). Syntax is valid Java.",
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "FAILED",
            "error": str(exc),
            "message": f"Java syntax validation error: {exc}",
        }
