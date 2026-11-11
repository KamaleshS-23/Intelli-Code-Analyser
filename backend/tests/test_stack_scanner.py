import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scanner.project_scanner import ProjectScanner
from debt_analyzer.debt_engine import DebtEngine
from stacks import STACK_PROFILES, normalize_stack


class StackAwareScannerTests(unittest.TestCase):
    def test_stack_profiles_are_available_and_reject_unknown_values(self):
        self.assertEqual(
            set(STACK_PROFILES),
            {"java", "python", "web", "django", "nodejs"},
        )
        with self.assertRaises(ValueError):
            normalize_stack("unsupported")

    def test_java_stack_still_parses_java_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "Hello.java").write_text(
                "public class Hello {\n"
                "    public void greet() {}\n"
                "}\n",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="java").scan()

            self.assertEqual(project.statistics["total_files"], 1)
            self.assertEqual(project.statistics["total_classes"], 1)

    def test_python_project_scan_works_for_python_stack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "app").mkdir()
            (project_dir / "app" / "service.py").write_text(
                "class OrderService:\n"
                "    def __init__(self):\n"
                "        self.total = 0\n\n"
                "    def process(self, items):\n"
                "        for item in items:\n"
                "            self.total += item['price']\n"
                "        return self.total\n",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="python").scan()

            self.assertGreater(len(project.classes), 0)
            self.assertIn("python", str(project.statistics).lower())
            self.assertGreater(project.statistics.get("total_methods", 0), 0)

    def test_python_debt_engine_detects_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "app").mkdir()
            (project_dir / "app" / "bad_service.py").write_text(
                "class BadService:\n"
                "    def process(self, items):\n"
                "        total = 0\n"
                "        for item in items:\n"
                "            total += item * 7\n"
                "            if total > 100:\n"
                "                if total > 200:\n"
                "                    if total > 300:\n"
                "                        print('deep')\n"
                "        return total\n",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="python").scan()
            report = DebtEngine(stack="python").analyze(project)

            self.assertGreater(len(report.issues), 0)
            self.assertTrue(any(issue.rule in {"LongMethod", "HighCyclomaticComplexity", "DeepNesting", "MagicNumber"} for issue in report.issues))

    def test_python_ast_rules_cover_module_functions_and_security_findings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "report.py").write_text(
                "import hashlib\n"
                "def build_report(cursor, region, options, customer_id, retries, include_archived):\n"
                "    try:\n"
                "        query = f\"SELECT * FROM customers WHERE region = '{region}'\"\n"
                "        cursor.execute(query)\n"
                "    except Exception:\n"
                "        pass\n"
                "    digest = hashlib.md5(customer_id.encode()).hexdigest()\n"
                "    source = open('report.txt')\n"
                "    return digest, source\n"
                "def evaluate(expression, values=[]):\n"
                "    return eval(expression), values\n"
                "def find_blocked(users):\n"
                "    for user in users:\n"
                "        if user in ['blocked', 'retired']:\n"
                "            return user\n"
                "class SharedCache:\n"
                "    cached_items = {}\n",
                encoding="utf-8",
            )
            (project_dir / "cycle_a.py").write_text(
                "from cycle_b import helper\n"
                "def first():\n"
                "    return helper()\n",
                encoding="utf-8",
            )
            (project_dir / "cycle_b.py").write_text(
                "from cycle_a import first\n"
                "def helper():\n"
                "    return first()\n",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="python").scan()
            report = DebtEngine(stack="python").analyze(project)
            rules = {issue.rule for issue in report.issues}

            self.assertTrue({
                "ExcessiveParameterList",
                "CircularDependency",
                "EmptyExceptBlock",
                "BroadExceptionHandling",
                "SqlInjection",
                "WeakHashAlgorithm",
                "UnclosedResource",
                "MutableDefaultArgument",
                "UnsafeDynamicExecution",
                "MutableClassAttribute",
                "InefficientLookup",
                "MissingDocstring",
            }.issubset(rules))

    def test_python_ast_rules_cover_class_design_and_performance_findings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            source = [
                "class A: pass",
                "class B(A): pass",
                "class C(B): pass",
                "class D(C): pass",
                "class E(D): pass",
                "class DataPresenter:",
                "    def present(self, record):",
                "        return record.one + record.two + record.three + record.four + record.five + record.six",
                "class DependencyHeavy:",
                "    def execute(self):",
                "        return " + " + ".join(f"dependency_{i}()" for i in range(11)),
                "class ManyMethods:",
            ]
            source.extend(
                f"    def method_{i}(self): pass"
                for i in range(21)
            )
            (project_dir / "design.py").write_text(
                "\n".join(source) + "\n",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="python").scan()
            report = DebtEngine(stack="python").analyze(project)
            rules = {issue.rule for issue in report.issues}

            self.assertTrue({
                "DeepInheritance",
                "FeatureEnvy",
                "HighCoupling",
                "LargeClass",
            }.issubset(rules))

    def test_python_sample_project_demonstrates_the_rule_catalog(self):
        sample = (
            Path(__file__).resolve().parent.parent
            / "scanner"
            / "uploads"
            / "SamplePythonProject"
        )
        project = ProjectScanner(str(sample), stack="python").scan()
        report = DebtEngine(stack="python").analyze(project)
        rules = {issue.rule for issue in report.issues}

        self.assertTrue({
            "CircularDependency",
            "DuplicateCode",
            "DeepInheritance",
            "ExcessiveParameterList",
            "FeatureEnvy",
            "HighCoupling",
            "LargeClass",
            "MutableClassAttribute",
            "MutableDefaultArgument",
            "SqlInjection",
            "UnsafeDynamicExecution",
            "WeakHashAlgorithm",
        }.issubset(rules))

    def test_web_stack_scans_assets_and_runs_web_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "index.html").write_text(
                '<h1 style="color: red">Hello</h1>', encoding="utf-8"
            )
            (project_dir / "app.js").write_text(
                "// TODO: remove the debug output\nconsole.log('hello');",
                encoding="utf-8",
            )

            project = ProjectScanner(str(project_dir), stack="web").scan()
            report = DebtEngine(stack="web").analyze(project)

            self.assertEqual(project.statistics["total_files"], 2)
            self.assertEqual(project.statistics["languages"], ["html", "css", "javascript"])
            self.assertEqual(
                {issue.rule for issue in report.issues},
                {"UnresolvedTodo", "MissingDoctype", "InlineStyle"},
            )
            self.assertEqual(project.statistics["web_analysis"]["summary"]["files"]["html"], 1)

    def test_web_sample_reports_cross_language_rules_and_metrics(self):
        sample = (
            Path(__file__).resolve().parents[1]
            / "scanner"
            / "uploads"
            / "SampleWebProject"
        )
        from scanner.scanner_service import ScannerService

        result = ScannerService().scan(
            str(sample),
            save_output=False,
            run_dependency_scan=False,
            stack="web",
        )
        rules = {issue["rule"] for issue in result["debt_report"]["issues"]}
        self.assertTrue({
            "MissingImageAlt",
            "InlineStyle",
            "InlineEventHandler",
            "DeprecatedTag",
            "MissingDoctype",
            "NonSemanticDivSoup",
            "ExcessiveImportant",
            "HardcodedColor",
            "DuplicateSelector",
            "DeepSelectorNesting",
            "VarInsteadOfLetConst",
            "LooseEquality",
            "ConsoleLogInProduction",
            "LongFunction",
            "CallbackHell",
            "GlobalVariablePollution",
            "UnsafeEval",
            "UnsafeInnerHTML",
            "UnusedCssClass",
            "UndefinedCssClass",
            "UnusedJsFunction",
            "MissingEventListenerCleanup",
        }.issubset(rules))

        metrics = result["statistics"]["web_analysis"]
        self.assertEqual(
            metrics["summary"]["total_issues"],
            len(result["debt_report"]["issues"]),
        )
        self.assertGreater(metrics["metrics"]["html"]["totals"]["semantic_ratio"], 0)
        self.assertGreater(metrics["metrics"]["css"]["totals"]["important_count"], 5)
        self.assertGreater(metrics["metrics"]["javascript"]["totals"]["eval_calls"], 0)
        self.assertEqual(
            next(issue for issue in result["debt_report"]["issues"]
                 if issue["rule"] == "MissingImageAlt")["rule_id"],
            "WEB-HT-001",
        )
        self.assertGreater(
            next(issue for issue in result["debt_report"]["issues"]
                 if issue["rule"] == "MissingImageAlt")["estimated_fix_minutes"],
            0,
        )
        self.assertEqual(
            next(issue for issue in result["debt_report"]["issues"]
                 if issue["rule"] == "ExcessiveImportant")["category"],
            "STYLE",
        )
        self.assertEqual(
            next(issue for issue in result["debt_report"]["issues"]
                 if issue["rule"] == "UnsafeEval")["language"],
            "JS",
        )
        coupling = list(metrics["metrics"]["coupling"].values())
        self.assertTrue(coupling)
        self.assertTrue(all(metric["orphan_js_ids"] == 0 for metric in coupling))
        self.assertGreater(
            sum(metric["orphan_html_ids"] for metric in coupling),
            0,
        )

    def test_django_and_node_stacks_run_framework_specific_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "project").mkdir()
            (project_dir / "project" / "settings.py").write_text(
                "DEBUG = True\nSECRET_KEY = 'sample-secret-value'\n",
                encoding="utf-8",
            )
            (project_dir / "project" / "views.py").write_text(
                "def list_items(cursor):\n"
                "    cursor.execute('SELECT * FROM items')\n",
                encoding="utf-8",
            )
            (project_dir / "templates").mkdir()
            (project_dir / "templates" / "index.html").write_text(
                "<h1>Django</h1>", encoding="utf-8"
            )

            django_project = ProjectScanner(str(project_dir), stack="django").scan()
            django_report = DebtEngine(stack="django").analyze(django_project)
            django_rules = {issue.rule for issue in django_report.issues}
            self.assertIn("DjangoDebugEnabled", django_rules)
            self.assertIn("DjangoRawSql", django_rules)
            self.assertIn("DjangoHardcodedSecret", django_rules)
            self.assertEqual(django_project.statistics["total_files"], 3)

            (project_dir / "server.js").write_text(
                "const fs = require('fs');\n"
                "fs.readFileSync('data.txt');\n"
                "eval('run()');\n",
                encoding="utf-8",
            )
            node_project = ProjectScanner(str(project_dir), stack="nodejs").scan()
            node_report = DebtEngine(stack="nodejs").analyze(node_project)
            node_rules = {issue.rule for issue in node_report.issues}
            self.assertIn("NodeSynchronousIo", node_rules)
            self.assertIn("UnsafeEval", node_rules)
            self.assertNotIn("DjangoDebugEnabled", node_rules)
            self.assertIn("node_analysis", node_project.statistics)
            self.assertNotIn("django_analysis", node_project.statistics)

    def test_node_sample_reports_node_rules_metrics_and_metadata(self):
        sample = (
            Path(__file__).resolve().parents[1]
            / "scanner"
            / "uploads"
            / "SampleNodeProject"
        )
        from scanner.scanner_service import ScannerService

        result = ScannerService().scan(
            str(sample),
            save_output=False,
            run_dependency_scan=False,
            stack="nodejs",
        )
        issues = result["debt_report"]["issues"]
        rule_ids = {issue["rule_id"] for issue in issues}
        expected = {
            "ND-PK-001",
            "ND-PK-003",
            "ND-PK-004",
            "ND-PK-006",
            "ND-AS-005",
            "ND-EX-002",
            "ND-EX-003",
            "ND-EX-004",
            "ND-EX-005",
            "ND-MW-001",
            "ND-MW-003",
            "ND-MW-004",
            "ND-SC-001",
            "ND-SC-002",
            "ND-SC-003",
            "ND-DB-004",
        }
        self.assertTrue(expected.issubset(rule_ids), expected - rule_ids)
        analysis = result["statistics"]["node_analysis"]
        self.assertEqual(analysis["framework"], "express")
        self.assertEqual(analysis["metrics"]["dependencies"]["production"], 3)
        self.assertGreater(analysis["metrics"]["async"]["server.js"]["await_count"], 0)
        self.assertGreater(analysis["metrics"]["routes"]["server.js"]["route_count"], 0)
        self.assertGreater(analysis["metrics"]["security"]["server.js"]["exec_calls"], 0)
        self.assertEqual(
            analysis["summary"]["total_issues"],
            sum(issue["rule_id"].startswith("ND-") for issue in issues),
        )
        finding = next(issue for issue in issues if issue["rule_id"] == "ND-SC-001")
        self.assertEqual(finding["framework"], "express")
        self.assertTrue(finding["node_version_aware"])

    def test_node_template_findings_are_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "package.json").write_text(
                '{"dependencies":{"express":"^4.18.0"}}\n',
                encoding="utf-8",
            )
            (project_dir / "server.js").write_text(
                "const express = require('express');\n"
                "const app = express();\n"
                "app.use(express.static('public'));\n",
                encoding="utf-8",
            )
            public_dir = project_dir / "public"
            public_dir.mkdir()
            for name in ("index.html", "admin.html"):
                (public_dir / name).write_text(
                    "<html><head><style>body { color: red; }</style></head>"
                    "<body><script>run();</script></body></html>\n",
                    encoding="utf-8",
                )

            project = ProjectScanner(str(project_dir), stack="nodejs").scan()
            report = DebtEngine(stack="nodejs").analyze(project)
            counts = {}
            for issue in report.issues:
                counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1

            self.assertEqual(counts.get("ND-FE-001"), 2)
            self.assertEqual(counts.get("ND-FE-002"), 1)

    def test_ai_context_includes_node_metrics_and_finding_metadata(self):
        from ai_assistant.context_builder import build_project_context
        from ai_assistant.orchestrator import AIChatOrchestrator
        from ai_assistant.tools import get_project_summary

        node_analysis = {
            "framework": "express",
            "summary": {"debt_score": 22, "total_issues": 3},
            "metrics": {
                "packages": {"lockfile": None, "scripts": ["start"]},
                "dependencies": {"production": 2, "dev": 1},
                "async": {"server.js": {"await_count": 2, "then_count": 1, "catch_count": 0}},
                "routes": {"server.js": {"route_count": 3, "writes": 1}},
                "security": {"server.js": {"eval_calls": 1, "exec_calls": 0, "hardcoded_secrets": 0}},
            },
        }
        scan = {
            "project_name": "NodeExample",
            "statistics": {
                "stack": "nodejs",
                "language": "JavaScript, HTML, CSS",
                "languages": ["javascript", "html", "css"],
                "node_analysis": node_analysis,
            },
            "debt_report": {
                "issues": [{
                    "rule": "UnsafeChildProcess",
                    "rule_id": "ND-SC-001",
                    "severity": "critical",
                    "category": "SECURITY",
                    "language": "Node.js",
                    "class_name": "server.js",
                    "message": "Dynamic shell command.",
                    "node_version_aware": True,
                    "framework": "express",
                }],
            },
        }
        context = build_project_context(scan)
        self.assertEqual(context["technical_debt"]["node_analysis"]["framework"], "express")
        self.assertEqual(context["technical_debt"]["node_analysis"]["metrics"]["routes"]["route_count"], 3)
        self.assertTrue(context["findings"][0]["node_version_aware"])
        self.assertEqual(get_project_summary(scan)["node_analysis"]["framework"], "express")
        prompt = AIChatOrchestrator()._build_prompt(
            "Explain the Node.js findings.", {"scan_result": scan}
        )
        self.assertIn("Node.js Project Metrics", prompt)
        self.assertIn('"framework": "express"', prompt)

    def test_django_sample_runs_web_rules_and_reports_metrics(self):
        sample = (
            Path(__file__).resolve().parents[1]
            / "scanner"
            / "uploads"
            / "SampleDjangoProject"
        )
        from scanner.scanner_service import ScannerService

        result = ScannerService().scan(
            str(sample),
            save_output=False,
            run_dependency_scan=False,
            stack="django",
        )
        rules = {issue["rule"] for issue in result["debt_report"]["issues"]}

        self.assertTrue({
            "DjangoDebugEnabled",
            "DjangoRawSql",
            "DjangoHardcodedSecret",
            "MissingImageAlt",
            "MissingDoctype",
            "InlineEventHandler",
            "DeprecatedTag",
            "ExcessiveImportant",
            "HardcodedColor",
            "DuplicateSelector",
            "VarInsteadOfLetConst",
            "LooseEquality",
            "LongFunction",
            "UnsafeEval",
            "UnsafeInnerHTML",
            "UnusedJsFunction",
            "MissingEventListenerCleanup",
        }.issubset(rules))
        analysis = result["statistics"]["web_analysis"]
        self.assertEqual(analysis["summary"]["files"]["html"], 2)
        self.assertEqual(analysis["summary"]["files"]["css"], 1)
        self.assertEqual(analysis["summary"]["files"]["javascript"], 2)
        self.assertGreater(analysis["metrics"]["html"]["totals"]["inline_handlers"], 0)
        self.assertGreater(analysis["metrics"]["css"]["totals"]["important_count"], 5)
        self.assertGreater(analysis["metrics"]["javascript"]["totals"]["eval_calls"], 0)
        self.assertGreater(analysis["metrics"]["html"]["totals"]["class_count"], 0)
        self.assertGreater(analysis["metrics"]["css"]["totals"]["unique_selectors"], 0)
        self.assertIn(
            "orphan_html_classes",
            next(iter(analysis["metrics"]["coupling"].values())),
        )

    def test_django_sample_reports_framework_rules_metrics_and_metadata(self):
        sample = (
            Path(__file__).resolve().parents[1]
            / "scanner"
            / "uploads"
            / "SampleDjangoProject"
        )
        from scanner.scanner_service import ScannerService

        result = ScannerService().scan(
            str(sample),
            save_output=False,
            run_dependency_scan=False,
            stack="django",
        )
        issues = result["debt_report"]["issues"]
        rules = {issue["rule"] for issue in issues}
        rule_ids = {issue["rule_id"] for issue in issues}
        expected = {
            "DjangoDebugEnabled",
            "DjangoHardcodedSecret",
            "DjangoRawSql",
            "AllowedHostsWildcard",
            "CorsAllowAll",
            "InsecureSessionCookie",
            "MissingSecurityMiddleware",
            "WeakPasswordValidators",
            "ModelMissingMeta",
            "ModelMissingStr",
            "NullableBooleanField",
            "CharFieldWithoutMaxLength",
            "MissingLoginRequired",
            "N1QueryProblem",
            "MissingSelectRelated",
            "UnboundedQueryset",
            "DirectRenderWithManyLocals",
            "FieldsAllRisk",
            "MissingFormValidation",
            "DangerousWildcardURL",
            "NonDescriptiveURLName",
            "DataMixedWithSchemaMigration",
            "NonAtomicMigration",
            "RunPythonMissingReverse",
            "TestWithoutAssertion",
            "HardcodedStaticPath",
        }
        self.assertTrue(expected.issubset(rules), expected - rules)
        self.assertIn("DJ-ORM-003", rule_ids)
        self.assertEqual(
            next(issue for issue in issues if issue["rule"] == "DjangoDebugEnabled")["rule_id"],
            "DJ-ST-001",
        )
        django = result["statistics"]["django_analysis"]
        self.assertEqual(django["metrics"]["django_version"], "4.2.11")
        self.assertGreater(django["metrics"]["orm"]["n_plus_one_risk"], 0)
        self.assertGreater(django["metrics"]["views"]["app/views.py"]["view_count"], 0)
        self.assertGreater(django["metrics"]["templates"]["templates/index.html"]["static_uses"], 0)
        self.assertGreater(django["metrics"]["architecture"]["app_count"], 0)
        self.assertEqual(
            django["summary"]["total_issues"],
            sum(issue["rule_id"].startswith("DJ-") for issue in issues),
        )
        finding = next(issue for issue in issues if issue["rule_id"] == "DJ-ORM-003")
        self.assertEqual(finding["layer"], "ORM")
        self.assertTrue(finding["django_version_aware"])

    def test_django_analysis_does_not_run_for_python_stack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "settings.py").write_text("DEBUG = True\n", encoding="utf-8")
            python_project = ProjectScanner(str(project_dir), stack="python").scan()
            DebtEngine(stack="python").analyze(python_project)
            self.assertNotIn("django_analysis", python_project.statistics)

    def test_ai_context_includes_web_metrics_and_rule_metadata(self):
        from ai_assistant.context_builder import build_project_context
        from ai_assistant.orchestrator import AIChatOrchestrator
        from ai_assistant.tools import get_project_summary

        web_analysis = {
            "summary": {"debt_score": 12.5},
            "metrics": {
                "html": {"totals": {"elements": 12}},
                "css": {"totals": {"rules": 4}},
                "javascript": {"totals": {"loc": 20}},
                "coupling": {},
            },
        }
        scan = {
            "project_name": "ExampleWeb",
            "statistics": {
                "stack": "web",
                "language": "HTML, CSS, JavaScript",
                "languages": ["html", "css", "javascript"],
                "web_analysis": web_analysis,
                "django_analysis": {
                    "summary": {"debt_score": 17.0, "apps": 2},
                    "metrics": {
                        "orm": {"n_plus_one_risk": 1},
                        "views": {},
                        "templates": {},
                        "architecture": {"app_count": 2},
                        "django_version": "4.2.11",
                    },
                },
            },
            "debt_report": {
                "issues": [{
                    "rule": "MissingImageAlt",
                    "rule_id": "WEB-HT-001",
                    "category": "ACCESSIBILITY",
                    "language": "HTML",
                    "severity": "high",
                    "class_name": "index.html",
                    "message": "Image is missing an alt attribute.",
                    "estimated_fix_minutes": 2,
                }],
            },
        }

        context = build_project_context(scan)
        self.assertEqual(context["project"]["stack"], "web")
        self.assertEqual(context["project"]["language"], "HTML, CSS, JavaScript")
        self.assertEqual(context["findings"][0]["rule_id"], "WEB-HT-001")
        self.assertEqual(context["technical_debt"]["web_analysis"]["summary"], web_analysis["summary"])
        self.assertEqual(
            context["technical_debt"]["web_analysis"]["metrics"]["html"]["elements"],
            12,
        )
        self.assertEqual(get_project_summary(scan)["web_analysis"], web_analysis["summary"])
        self.assertEqual(
            get_project_summary(scan)["django_analysis"]["debt_score"],
            17.0,
        )
        self.assertEqual(
            context["technical_debt"]["django_analysis"]["metrics"]["orm"]["n_plus_one_risk"],
            1,
        )

        prompt = AIChatOrchestrator()._build_prompt(
            "Explain the web metrics.",
            {"scan_result": scan},
        )
        self.assertIn("HTML, CSS, JavaScript projects", prompt)
        self.assertIn("Web Stack Metrics", prompt)
        self.assertIn('"elements": 12', prompt)
        self.assertIn("Django Framework Metrics", prompt)
        self.assertIn('"app_count": 2', prompt)


if __name__ == "__main__":
    unittest.main()
