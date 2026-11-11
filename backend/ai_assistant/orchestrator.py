from __future__ import annotations

import json
from .context_builder import (
    build_project_context,
    extract_django_analysis,
    extract_node_analysis,
)
from .memory import ProjectMemory
from .provider import get_provider
from .tools import (
    find_high_complexity_methods,
    find_high_coupling_classes,
    find_vulnerable_dependencies,
    get_knowledge_graph_data,
    get_project_summary,
    get_root_cause_context,
    get_technical_debt_summary,
    search_code,
    validate_java_code,
)


class AIChatOrchestrator:
    def __init__(self):
        self.memory = ProjectMemory()
        self.latest_scan = None

    def register_scan(self, scan_result):
        self.latest_scan = scan_result
        project_id = (scan_result or {}).get("project_name") or "default"
        self.memory.store_scan(project_id, scan_result)

    def _choose_scan(self, project_id=None, scan_id=None):
        if project_id:
            scan = self.memory.get_latest_scan(project_id)
            if scan:
                return scan
        if scan_id and self.latest_scan:
            if (self.latest_scan.get("_output_file") or "") == scan_id:
                return self.latest_scan
        return self.latest_scan

    def _detect_feature_intent(self, message: str, explicit_mode: str | None = None) -> str:
        if explicit_mode and explicit_mode in {"explain", "root-cause", "graph", "refactor", "validation"}:
            return explicit_mode

        msg = (message or "").lower()
        if any(term in msg for term in ["diff", "before-after", "before after", "validate", "validation", "build", "test validation", "prove"]):
            return "validation"
        if any(term in msg for term in ["refactor", "code generation", "generate fix", "fix the code", "rewrite", "extract class", "extract method"]):
            return "refactor"
        if any(term in msg for term in ["graph", "knowledge graph", "relationship", "dependency", "circular", "coupling", "caller", "callee", "blast radius"]):
            return "graph"
        if any(term in msg for term in ["why", "root cause", "root-cause", "anti-pattern", "solid", "reason", "architectural flaw"]):
            return "root-cause"
        return "explain"

    def _build_prompt(self, message, context, mode="explain"):
        scan_result = context.get("scan_result")
        project_summary = get_project_summary(scan_result)
        debt_summary = get_technical_debt_summary(scan_result)
        complexity_search = find_high_complexity_methods(scan_result, threshold=10)[:6]
        coupling_search = find_high_coupling_classes(scan_result, threshold=2)[:6]
        graph_data = get_knowledge_graph_data(scan_result)
        root_causes = get_root_cause_context(scan_result)
        vulnerabilities = find_vulnerable_dependencies(scan_result)[:5]

        # Detailed debt findings for grounding
        debt = (scan_result or {}).get("debt_report") or {}
        issues = debt.get("issues") or []
        top_issues_sample = [
            {
                "rule": i.get("rule"),
                "rule_id": i.get("rule_id"),
                "severity": i.get("severity"),
                "category": i.get("category"),
                "language": i.get("language"),
                "class": i.get("class_name"),
                "method": i.get("method_name"),
                "line": i.get("line_number"),
                "message": i.get("message"),
                "suggestion": i.get("suggestion"),
                "refactoring_pattern": i.get("refactoring_pattern"),
                "estimated_fix_minutes": i.get("estimated_fix_minutes"),
                "layer": i.get("layer"),
                "django_version_aware": i.get("django_version_aware"),
                "node_version_aware": i.get("node_version_aware"),
                "framework": i.get("framework"),
            }
            for i in issues[:12]
        ]
        project_language = project_summary.get("language") or "the detected stack"
        web_analysis = ((scan_result or {}).get("statistics") or {}).get("web_analysis")
        web_metrics = None
        if web_analysis:
            metrics = web_analysis.get("metrics") or {}
            web_metrics = {
                "summary": web_analysis.get("summary") or {},
                "html": (metrics.get("html") or {}).get("totals") or {},
                "css": (metrics.get("css") or {}).get("totals") or {},
                "javascript": (metrics.get("javascript") or {}).get("totals") or {},
                "coupling": list((metrics.get("coupling") or {}).items())[:10],
            }
        django_metrics = extract_django_analysis(
            ((scan_result or {}).get("statistics") or {})
        )
        node_metrics = extract_node_analysis(
            ((scan_result or {}).get("statistics") or {})
        )

        feature_instructions = {
            "explain": """
You are acting as FEATURE 1: 🔍 Technical Debt Explanation.
- Explain the detected technical debt clearly and accurately.
- Break down the issues by severity (Critical, High, Medium, Low) and rule category.
- Reference exact files, components, classes, methods, and line numbers from the facts below.
- Clarify the concrete impact on maintainability, testing, and defect rates.
""",
            "root-cause": """
You are acting as FEATURE 2: 🧠 Root-Cause Analysis.
- Explain WHY the technical debt exists in this project from an architectural perspective.
- Identify design anti-patterns (e.g. God Class in UserService, Procedural Nesting, Missing Abstractions, Tight Coupling).
- Explain how SOLID principles (Single Responsibility, Dependency Inversion, etc.) were violated.
- Contrast quick-fix legacy development habits with proper object-oriented domain design.
""",
            "graph": """
You are acting as FEATURE 3: 🕸️ Knowledge Graph Query.
- Explain code and dependency relationships across classes and components.
- Highlight incoming/outgoing dependencies (fan-in/fan-out) and coupling metrics.
- Detail any circular dependency chains (e.g., AuditLogService <-> UserService).
- Explain the 'blast radius' (which components are impacted if a specific class is modified).
""",
            "refactor": """
You are acting as FEATURE 4: 🛠️ AI Refactoring & Code Generation.
- Recommend concrete, production-ready refactoring solutions for the detected project stack.
- Use the project's actual languages and file types; do not assume Java.
- Demonstrate appropriate modularity, accessibility, safety, and maintainability improvements.
- Give clear step-by-step migration instructions for the developer.
""",
            "validation": """
You are acting as FEATURE 5: ✅ Before–After Diff & Build/Test Validation.
- Prove and validate the proposed changes.
- Provide a unified Before vs. After code diff in a ```diff block using - for removed lines and + for added lines.
- Include a structured 'Build & Test Validation Report' verifying:
  * Java Syntax & Compilation: Validated (No unresolved types or syntax errors)
  * Cyclomatic Complexity Delta (e.g. Reduced from 23 to <= 5)
  * Circular Dependency Check: Resolved / Decoupled
  * Build Status: ✅ VALIDATION PASSED
""",
        }

        active_mode_instruction = feature_instructions.get(mode, feature_instructions["explain"])

        return f"""
You are the AI Technical Debt Assistant for {project_language} projects.
You have 5 core capabilities:
1. 🔍 Technical Debt Explanation (Explain detected debt)
2. 🧠 Root-Cause Analysis (Explain why the debt exists)
3. 🕸️ Knowledge Graph Query (Understand code & dependency relationships)
4. 🛠️ AI Refactoring & Code Generation (Recommend and generate fixes)
5. ✅ Before–After Diff & Build/Test Validation (Prove and validate changes)

ACTIVE SPECIALIZED MODE:
{active_mode_instruction}

STRICT GROUNDING RULES:
1. Use only the real project facts supplied below. Never invent non-existent files or fake classes.
2. If data is not present in the scan, state clearly: 'Based on the scan data, this is not present.'
3. Output clean, formatted GitHub Markdown with clear headers, bullet points, tables, and ```java / ```diff blocks where relevant.

==================================================
PROJECT FACTS & SCAN DATA
==================================================
Project Summary:
{json.dumps(project_summary, indent=2)}

Technical Debt Summary:
{json.dumps(debt_summary, indent=2)}

Knowledge Graph & Dependency Metrics:
{json.dumps(graph_data, indent=2)}

Root-Cause Architectural Signals:
{json.dumps(root_causes, indent=2)}

Top Complexity Methods:
{json.dumps(complexity_search, indent=2)}

High-Coupling Classes:
{json.dumps(coupling_search, indent=2)}

Vulnerable / Outdated Dependencies:
{json.dumps(vulnerabilities, indent=2)}

Sample Detected Debt Findings (Issues):
{json.dumps(top_issues_sample, indent=2)}

Web Stack Metrics (when applicable):
{json.dumps(web_metrics, indent=2)}

Django Framework Metrics (when applicable):
{json.dumps(django_metrics, indent=2)}

Node.js Project Metrics (when applicable):
{json.dumps(node_metrics, indent=2)}

==================================================
USER QUERY:
{message}
==================================================
Produce a high quality, structured, grounded response:
"""

    def chat(self, scan_result, message, request_context=None):
        if not scan_result:
            raise ValueError("No project scan is available yet. Run a scan first.")

        provider = get_provider()
        if not provider:
            raise RuntimeError("AI provider is not configured.")

        req_ctx = request_context or {}
        explicit_mode = req_ctx.get("mode")
        mode = self._detect_feature_intent(message, explicit_mode)

        context = build_project_context(scan_result, req_ctx)
        prompt = self._build_prompt(message, {"scan_result": scan_result}, mode=mode)

        try:
            answer = provider.generate(prompt, context)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc

        project_id = scan_result.get("project_name") or "default"
        self.memory.remember(project_id, message, answer)

        response = {
            "message": answer,
            "mode": mode,
            "type": mode,
            "evidence": context.get("evidence", []),
            "recommendations": [
                "Review the top findings in the debt report.",
                "Inspect the most complex or highly coupled classes first.",
                "Validate any proposed refactor before committing changes.",
            ],
            "actions": ["EXPLAIN", "ROOT_CAUSE", "GRAPH_QUERY", "REFACTOR", "VALIDATE"],
        }
        return response
