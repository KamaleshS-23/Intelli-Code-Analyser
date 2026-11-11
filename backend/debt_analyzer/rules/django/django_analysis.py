"""Framework-aware Django rules and project metrics."""

import ast
import re
from pathlib import Path

from debt_analyzer.models import DebtIssue
from debt_analyzer.rules.base_rule import BaseRule
from scanner.config import IGNORE_DIRS


SEVERITY_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0.5}
SENSITIVE_VIEW_NAMES = (
    "dashboard", "profile", "admin", "settings", "account", "delete",
    "edit", "create", "update", "checkout", "payment",
)
DATABASE_WRITE_CALLS = {
    "save", "delete", "create", "update", "bulk_create", "bulk_update",
}
QUERY_READ_CALLS = {
    "all", "filter", "exclude", "get", "get_or_create", "update_or_create",
    "count", "exists", "first", "last", "raw",
}
AUTH_DECORATORS = {
    "login_required", "permission_required", "user_passes_test",
    "LoginRequiredMixin", "PermissionRequiredMixin",
}
MODEL_FIELDS = {
    "BooleanField", "CharField", "DateField", "DateTimeField", "DecimalField",
    "EmailField", "FileField", "ForeignKey", "ImageField", "IntegerField",
    "ManyToManyField", "OneToOneField", "SlugField", "TextField", "URLField",
}
STATIC_SUFFIXES = {
    ".css", ".js", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".otf",
}


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _source(node):
    try:
        return ast.unparse(node)
    except (AttributeError, TypeError, ValueError):
        return ""


def _decorator_names(function):
    return {_call_name(decorator) for decorator in function.decorator_list}


def _is_test_file(path):
    return path.name.startswith("test_") or path.name == "tests.py" or "tests" in path.parts


class DjangoProjectAnalysisRule(BaseRule):
    """Run Django-aware checks across Python, templates, and static assets."""

    name = "DjangoFrameworkAnalysis"

    def analyze(self, context):
        root = Path(context.project.project_path).resolve()
        if not root.is_dir():
            return []

        issues = []
        metrics = {
            "orm": {"queries_per_function": {}, "n_plus_one_risk": 0},
            "views": {},
            "templates": {},
            "architecture": {},
            "django_version": self._django_version(root),
            "django_version_aware": True,
        }
        files = list(self._project_files(root))

        for path in files:
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if path.suffix.lower() == ".py":
                try:
                    tree = ast.parse(source, filename=relative)
                except SyntaxError:
                    continue
                file_issues, file_metrics = self._analyze_python(
                    path, relative, source, tree, root
                )
                issues.extend(file_issues)
                metrics["orm"]["queries_per_function"].update(
                    file_metrics["queries_per_function"]
                )
                metrics["orm"]["n_plus_one_risk"] += file_metrics["n_plus_one_risk"]
                if path.name == "views.py":
                    metrics["views"][relative] = file_metrics["views"]
            elif path.suffix.lower() in {".html", ".htm"}:
                issues.extend(self._analyze_template(path, relative, source))
                metrics["templates"][relative] = self._template_metrics(source)
            elif path.suffix.lower() in STATIC_SUFFIXES:
                if path.stat().st_size > 500 * 1024:
                    issues.append(self._issue(
                        "DJ-SF-001", "LargeStaticAsset", "medium", "STATIC", "STATIC",
                        relative, 1, "Static asset exceeds 500 KB.",
                        "Compress, resize, or split the asset; use modern formats where practical.",
                        metric_value=round(path.stat().st_size / 1024, 1),
                        threshold=500,
                        fix_minutes=30,
                    ))

        metrics["architecture"] = self._architecture_metrics(root, files)
        weight = sum(SEVERITY_WEIGHT.get(issue.severity.lower(), 1) for issue in issues)
        source_count = sum(
            path.suffix.lower() in {".py", ".html", ".htm"} for path in files
        )
        summary = {
            "total_issues": len(issues),
            "critical": sum(issue.severity.lower() == "critical" for issue in issues),
            "high": sum(issue.severity.lower() == "high" for issue in issues),
            "medium": sum(issue.severity.lower() == "medium" for issue in issues),
            "low": sum(issue.severity.lower() == "low" for issue in issues),
            "debt_score": round(min(100, weight / max(source_count, 1) * 10), 2),
            "apps": metrics["architecture"]["app_count"],
        }
        context.project.statistics["django_analysis"] = {
            "stack": "django",
            "summary": summary,
            "metrics": metrics,
        }
        return issues

    @staticmethod
    def _project_files(root):
        for path in root.rglob("*"):
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in STATIC_SUFFIXES | {".py", ".html", ".htm"}:
                yield path

    @staticmethod
    def _django_version(root):
        candidates = [root / "requirements.txt", root / "pyproject.toml", root / "Pipfile"]
        version_pattern = re.compile(
            r"(?i)\bdjango(?:\s*[=<>!~]+\s*|\s*=\s*[\"'])(\d+(?:\.\d+){1,2})"
        )
        for path in candidates:
            if not path.is_file():
                continue
            try:
                match = version_pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _issue(
        rule_id, rule, severity, category, layer, path, line, message, suggestion,
        *, column=0, metric_value=None, threshold=None, fix_minutes=10, snippet="",
    ):
        return DebtIssue(
            rule=rule,
            severity=severity,
            class_name=path,
            file_path=path,
            line_number=max(1, line),
            column=column,
            message=message,
            suggestion=suggestion,
            metric_value=metric_value,
            metric_threshold=threshold,
            threshold=threshold,
            rule_id=rule_id,
            category=category,
            language="django",
            code_snippet=snippet,
            refactoring_pattern=suggestion,
            estimated_fix_minutes=fix_minutes,
            layer=layer,
            django_version_aware=True,
        )

    def _analyze_python(self, path, relative, source, tree, root):
        issues = []
        lines = source.splitlines()
        lower_path = relative.lower()
        is_settings = path.name.lower() in {"settings.py", "base.py", "production.py"} and (
            "settings" in lower_path or path.name.lower() == "settings.py"
        )
        is_models = path.name == "models.py"
        is_views = path.name == "views.py"
        is_urls = path.name == "urls.py"
        is_forms = path.name == "forms.py"
        is_migration = "migrations" in path.parts
        is_tests = _is_test_file(path)
        queries_per_function = {}
        n_plus_one_risk = 0

        def add(rule_id, rule, severity, category, layer, node, message, suggestion, **kwargs):
            line = getattr(node, "lineno", 1)
            snippet = lines[line - 1].strip() if 0 < line <= len(lines) else ""
            issues.append(self._issue(
                rule_id, rule, severity, category, layer, relative, line,
                message, suggestion, column=getattr(node, "col_offset", 0),
                snippet=snippet, **kwargs
            ))

        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        secured_class_methods = {
            method
            for cls in classes
            if {_call_name(base) for base in cls.bases} & AUTH_DECORATORS
            for method in cls.body
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for cls in classes:
            class_methods = [
                node for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if is_models:
                model_fields = [
                    child for child in cls.body
                    if isinstance(child, (ast.Assign, ast.AnnAssign))
                    and any(
                        isinstance(call, ast.Call) and _call_name(call) in MODEL_FIELDS
                        for call in ast.walk(child)
                    )
                ]
                if model_fields and not any(
                    isinstance(child, ast.ClassDef) and child.name == "Meta"
                    for child in cls.body
                ):
                    add("DJ-MD-001", "ModelMissingMeta", "low", "MODELS", "MODEL", cls,
                        f"Model '{cls.name}' has no inner Meta class.",
                        "Add Meta for explicit ordering, constraints, indexes, or table metadata.")
                if model_fields and not any(method.name == "__str__" for method in class_methods):
                    add("DJ-MD-002", "ModelMissingStr", "low", "MODELS", "MODEL", cls,
                        f"Model '{cls.name}' has no __str__ method.",
                        "Add a readable __str__ method for admin and log output.")
                class_loc = (getattr(cls, "end_lineno", cls.lineno) - cls.lineno + 1)
                if class_loc > 300:
                    add("DJ-MD-003", "FatModel", "high", "MODELS", "MODEL", cls,
                        f"Model class '{cls.name}' is {class_loc} lines long.",
                        "Extract domain services, managers, or related models.",
                        metric_value=class_loc, threshold=300, fix_minutes=60)
                for method in class_methods:
                    method_source = _source(method)
                    if ".objects." in method_source:
                        add("DJ-MD-004", "QueryInModelMethod", "medium", "MODELS", "MODEL", method,
                            f"Model method '{method.name}' performs ORM queries.",
                            "Move reusable query logic to a custom QuerySet or Manager.")
                model_source = _source(cls)
                if re.search(r"\bdb_index\s*=\s*False\b", model_source):
                    add("DJ-MD-005", "MissingDbIndex", "low", "MODELS", "MODEL", cls,
                        "A model field disables its default database index.",
                        "Disable a field index only after checking query plans and usage patterns.")
                for field in model_fields:
                    field_source = _source(field)
                    call = next(
                        (child for child in ast.walk(field)
                         if isinstance(child, ast.Call) and _call_name(child) in MODEL_FIELDS),
                        None,
                    )
                    if call is None:
                        continue
                    field_name = _call_name(call)
                    if field_name == "BooleanField" and re.search(r"\bnull\s*=\s*True", field_source):
                        add("DJ-MD-006", "NullableBooleanField", "medium", "MODELS", "MODEL", field,
                            "BooleanField uses null=True, introducing a third state.",
                            "Use null=False with an explicit default unless the unknown state is meaningful.")
                    if field_name == "CharField" and not any(
                        keyword.arg == "max_length" for keyword in call.keywords
                    ):
                        add("DJ-MD-007", "CharFieldWithoutMaxLength", "high", "MODELS", "MODEL", field,
                            "CharField has no max_length argument.",
                            "Set a domain-appropriate max_length or use TextField.")

            if is_views:
                for method in class_methods:
                    bases = {_call_name(base) for base in cls.bases}
                    if bases.intersection({"UpdateView", "CreateView", "DeleteView"}) and not (
                        bases & AUTH_DECORATORS
                    ):
                        add("DJ-VW-005", "CBVMissingMixin", "high", "SECURITY", "VIEW", method,
                            f"Class-based view '{cls.name}' may lack an authentication/permission mixin.",
                            "Add LoginRequiredMixin or a more specific permission mixin.")
                # Scan methods below with module-level functions.

        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            function_source = _source(function)
            calls = [
                node for node in ast.walk(function)
                if isinstance(node, ast.Call)
            ]
            query_calls = [
                call for call in calls
                if (
                    ".objects." in _source(call)
                    and _call_name(call) in QUERY_READ_CALLS | DATABASE_WRITE_CALLS
                ) or _call_name(call) in {"raw", "execute"}
            ]
            key = f"{relative}:{function.name}:{function.lineno}"
            queries_per_function[key] = len({call.lineno for call in query_calls})

            if is_views:
                loc = getattr(function, "end_lineno", function.lineno) - function.lineno + 1
                if loc > 60:
                    add("DJ-VW-001", "FatView", "high", "VIEWS", "VIEW", function,
                        f"View '{function.name}' is {loc} lines long.",
                        "Extract business logic into services, forms, or dedicated helpers.",
                        metric_value=loc, threshold=60, fix_minutes=loc)
                if any(name in function.name.lower() for name in SENSITIVE_VIEW_NAMES) and not (
                    _decorator_names(function) & AUTH_DECORATORS
                ) and function not in secured_class_methods:
                    add("DJ-VW-002", "MissingLoginRequired", "critical", "SECURITY", "VIEW", function,
                        f"Potentially sensitive view '{function.name}' has no recognized auth guard.",
                        "Require authentication and enforce the relevant object-level permission.")
                if "csrf_exempt" in _decorator_names(function):
                    add("DJ-VW-003", "CsrfExemptUsage", "high", "SECURITY", "VIEW", function,
                        f"View '{function.name}' disables CSRF protection.",
                        "Remove csrf_exempt unless an alternative request-authentication control is documented.")
                for call in calls:
                    if _call_name(call) == "render" and call.args and isinstance(call.args[-1], ast.Dict):
                        context_size = len(call.args[-1].keys)
                        if context_size > 8:
                            add("DJ-VW-004", "DirectRenderWithManyLocals", "medium", "VIEWS", "VIEW", call,
                                f"render() supplies {context_size} context values.",
                                "Extract context construction or split the view responsibility.",
                                metric_value=context_size, threshold=8)
                if re.search(r"DoesNotExist", function_source) and ".objects.get(" in function_source:
                    add("DJ-VW-006", "ManualGetObject404", "medium", "VIEWS", "VIEW", function,
                        "Manual DoesNotExist handling around objects.get() duplicates Django's helper.",
                        "Use get_object_or_404() for a concise and consistent 404 response.")

            for loop in (node for node in ast.walk(function) if isinstance(node, (ast.For, ast.AsyncFor, ast.While))):
                loop_source = _source(loop)
                body_db_calls = [
                    node for node in ast.walk(loop)
                    if isinstance(node, ast.Call) and (
                        (
                            ".objects." in _source(node)
                            and _call_name(node) in QUERY_READ_CALLS | DATABASE_WRITE_CALLS
                        )
                        or _call_name(node) in DATABASE_WRITE_CALLS
                        or _call_name(node) == "execute"
                    )
                ]
                loop_target = _source(loop.target) if isinstance(loop, (ast.For, ast.AsyncFor)) else ""
                loop_iter = _source(loop.iter) if isinstance(loop, (ast.For, ast.AsyncFor)) else ""
                loop_has_queryset = ".objects." in loop_iter or (
                    isinstance(loop, (ast.For, ast.AsyncFor))
                    and isinstance(loop.iter, ast.Name)
                    and re.search(
                        rf"\b{re.escape(loop.iter.id)}\s*=\s*[^;\n]*\.objects\.",
                        function_source,
                    ) is not None
                )
                relation_access = bool(loop_target) and re.search(
                    rf"\b{re.escape(loop_target)}\.[A-Za-z_]\w*", loop_source
                )
                if body_db_calls:
                    n_plus_one_risk += 1
                    query_in_loop = any(
                        _call_name(call) in QUERY_READ_CALLS
                        for call in body_db_calls
                    )
                    if query_in_loop:
                        add("DJ-ORM-001", "N1QueryProblem", "high", "ORM", "ORM", loop,
                            "An ORM query runs inside a loop and may issue one query per item.",
                            "Fetch related data before iteration or batch the query.")
                    else:
                        add("DJ-ORM-002", "QueryInsideLoop", "high", "ORM", "ORM", loop,
                            "Database writes or cursor operations occur inside a loop.",
                            "Batch the operation or use bulk_create/bulk_update.")
                if loop_has_queryset and relation_access and "select_related" not in function_source and "prefetch_related" not in function_source:
                    n_plus_one_risk += 1
                    add("DJ-ORM-003", "MissingSelectRelated", "medium", "ORM", "ORM", loop,
                        "A queryset loop accesses object attributes without eager-loading relations.",
                        "Use select_related() for single-valued relations or prefetch_related() for collections.")

            for call in calls:
                call_source = _source(call)
                if ".objects.all(" in call_source and not any(
                    marker in function_source for marker in ("Paginator", "[:", ".iterator(")
                ):
                    add("DJ-ORM-004", "UnboundedQueryset", "high", "ORM", "ORM", call,
                        "Queryset loads all rows without an evident bound.",
                        "Paginate the queryset or apply a deliberate limit.")
                if _call_name(call) in {"raw", "execute"} and (
                    _call_name(call) == "raw" or "cursor" in call_source or "execute" in call_source
                ):
                    add("DJ-ORM-005", "DjangoRawSql", "critical", "SECURITY", "ORM", call,
                        "Raw SQL execution bypasses normal ORM protections.",
                        "Prefer ORM queries; parameterize every value if raw SQL is required.")
                if "__contains" in call_source or "__icontains" in call_source:
                    add("DJ-ORM-008", "InefficientStrFilter", "low", "ORM", "ORM", call,
                        "Contains lookup can require a costly scan on large tables.",
                        "Measure query performance; add suitable indexes or full-text search when appropriate.")
                if ".order_by(" in call_source:
                    add("DJ-ORM-009", "OrderByWithoutIndex", "low", "ORM", "ORM", call,
                        "Review whether the ordered columns are indexed for this query workload.",
                        "Use query plans and add an index only when measurements justify it.")

            write_calls = [
                call for call in calls
                if _call_name(call) in DATABASE_WRITE_CALLS
            ]
            if len(write_calls) >= 2 and "atomic" not in function_source and not is_migration:
                add("DJ-ORM-006", "MissingAtomicTransaction", "medium", "ORM", "ORM", function,
                    f"Function '{function.name}' performs multiple database writes without an atomic block.",
                    "Wrap logically related writes in transaction.atomic().")
            if "objects.get(" in function_source and "except" in function_source and "objects.create(" in function_source:
                add("DJ-ORM-007", "GetOrCreateRaceCondition", "medium", "ORM", "ORM", function,
                    "Manual get-then-create flow can race under concurrent requests.",
                    "Use get_or_create() or update_or_create() with a database uniqueness constraint.")
            if is_tests and function.name.startswith("test_"):
                has_assertion = any(
                    isinstance(node, ast.Assert)
                    or (isinstance(node, ast.Call) and _call_name(node).startswith("assert"))
                    for node in ast.walk(function)
                )
                if not has_assertion:
                    add("DJ-TS-002", "TestWithoutAssertion", "medium", "TESTS", "VIEW", function,
                        f"Test '{function.name}' contains no assertion.",
                        "Assert the expected response, state change, or raised exception.")

        if is_models:
            # The field definitions and the query sites together make this a
            # heuristic review prompt rather than an assertion that every FK needs an index.
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and ".filter(" in _source(node):
                    if "__contains" not in _source(node) and "__icontains" not in _source(node):
                        continue

        if is_settings:
            settings_rules = [
                ("DJ-ST-001", "DjangoDebugEnabled", "critical", r"^\s*DEBUG\s*=\s*True\b",
                 "Django DEBUG is enabled.", "Read DEBUG from environment and default it to False."),
                ("DJ-ST-002", "DjangoHardcodedSecret", "critical", r"^\s*SECRET_KEY\s*=\s*(['\"])(?!\$\{)(.{8,}?)\1",
                 "A literal SECRET_KEY is stored in settings.", "Load SECRET_KEY from environment or a secret manager."),
                ("DJ-ST-003", "AllowedHostsWildcard", "high", r"ALLOWED_HOSTS\s*=\s*\[\s*['\"]\*['\"]",
                 "ALLOWED_HOSTS accepts every host.", "Restrict ALLOWED_HOSTS to the application's known hostnames."),
                ("DJ-ST-004", "CorsAllowAll", "high", r"CORS_ALLOW_ALL_ORIGINS\s*=\s*True\b",
                 "CORS allows requests from every origin.", "Allow only the trusted frontend origins."),
                ("DJ-ST-006", "InsecureSessionCookie", "high", r"SESSION_COOKIE_SECURE\s*=\s*False\b",
                 "Session cookies are explicitly allowed over HTTP.", "Set SESSION_COOKIE_SECURE=True in production."),
            ]
            for rule_id, rule, severity, pattern, message, suggestion in settings_rules:
                for line_number, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        issues.append(self._issue(
                            rule_id, rule, severity, "SECURITY", "SETTINGS", relative,
                            line_number, message, suggestion, snippet=line.strip()
                        ))
            if not any(re.match(r"\s*SESSION_COOKIE_SECURE\s*=", line) for line in lines):
                issues.append(self._issue(
                    "DJ-ST-006", "InsecureSessionCookie", "high", "SECURITY", "SETTINGS",
                    relative, 1, "SESSION_COOKIE_SECURE is not explicitly configured.",
                    "Set SESSION_COOKIE_SECURE=True in production settings.",
                ))
            middleware = next(
                (node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "MIDDLEWARE" for target in node.targets)),
                None,
            )
            if middleware is None or "SecurityMiddleware" not in _source(middleware):
                add("DJ-ST-005", "MissingSecurityMiddleware", "high", "SETTINGS", "SETTINGS", middleware or tree,
                    "MIDDLEWARE does not include Django SecurityMiddleware.",
                    "Add django.middleware.security.SecurityMiddleware near the start of MIDDLEWARE.")
            validators = next(
                (node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "AUTH_PASSWORD_VALIDATORS" for target in node.targets)),
                None,
            )
            if validators is None or len([n for n in ast.walk(validators) if isinstance(n, ast.Dict)]) < 3:
                add("DJ-SC-003", "WeakPasswordValidators", "critical", "SECURITY", "SETTINGS", tree,
                    "AUTH_PASSWORD_VALIDATORS is absent or not configured as a list of validators.",
                    "Enable Django's password validators and verify the production settings module.")

        if is_urls:
            for line_number, line in enumerate(lines, 1):
                if re.search(r"""(?:href|action)=["']/(?!/)[^"'{}]+["']""", line):
                    issues.append(self._issue(
                        "DJ-UR-001", "HardcodedURL", "medium", "URLS", "TEMPLATE",
                        relative, line_number, "Hardcoded local URL bypasses Django URL reversing.",
                        "Use the {% url %} template tag or reverse()/reverse_lazy().", snippet=line.strip()
                    ))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _call_name(node) in {"path", "re_path", "url"}:
                    pattern = _source(node.args[0]) if node.args else ""
                    if re.search(r"""['"].*(?:\.\*|\.\+|<path:.*>).*['"]""", pattern):
                        add("DJ-UR-003", "DangerousWildcardURL", "medium", "SECURITY", "URL", node,
                            "URL route uses a broad wildcard/path converter.",
                            "Constrain the route pattern and validate captured values.")
                    name_keyword = next(
                        (keyword.value for keyword in node.keywords if keyword.arg == "name"),
                        node.args[3] if len(node.args) > 3 else None,
                    )
                    route_name = _source(name_keyword).strip("'\"") if name_keyword else ""
                    if not route_name or route_name in {"url", "path", "view"}:
                        add("DJ-UR-002", "NonDescriptiveURLName", "low", "URLS", "URL", node,
                            "URL route name is missing or generic.",
                            "Assign a stable, descriptive name for reverse URL resolution.")

        if is_forms:
            for cls in classes:
                cls_src = _source(cls)
                if "ModelForm" not in cls_src:
                    continue
                if re.search(r"\bfields\s*=\s*['\"]__all__['\"]", cls_src):
                    add("DJ-FM-001", "FieldsAllRisk", "high", "SECURITY", "FORM", cls,
                        "ModelForm exposes fields='__all__', so future model fields may become writable.",
                        "Explicitly whitelist the fields intended for user input.")
                if not any(
                    isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and method.name.startswith("clean")
                    for method in cls.body
                ):
                    add("DJ-FM-002", "MissingFormValidation", "medium", "FORMS", "FORM", cls,
                        f"Form '{cls.name}' has no custom clean method.",
                        "Add field- or form-level validation for domain-specific input constraints.")

        if is_migration:
            has_runpython = "RunPython" in source
            has_schema_ops = any(token in source for token in (
                "AddField(", "RemoveField(", "AlterField(", "CreateModel(", "DeleteModel(",
            ))
            if has_runpython and has_schema_ops:
                add("DJ-MG-001", "DataMixedWithSchemaMigration", "medium", "MIGRATIONS", "MODEL", tree,
                    "Migration combines data changes and schema operations.",
                    "Separate data migrations from schema changes to simplify rollback and deployment.")
            if re.search(r"\batomic\s*=\s*False\b", source):
                add("DJ-MG-002", "NonAtomicMigration", "medium", "MIGRATIONS", "MODEL", tree,
                    "Migration disables atomic execution.",
                    "Keep migrations atomic unless operation size or backend constraints require otherwise.")
            if has_runpython and "reverse_code" not in source:
                add("DJ-MG-003", "RunPythonMissingReverse", "high", "MIGRATIONS", "MODEL", tree,
                    "RunPython migration has no reverse_code.",
                    "Provide a reverse operation or migrations.RunPython.noop when safe.")

        if is_views:
            adjacent_tests = path.with_name("tests.py").is_file() or (path.parent / "tests").is_dir()
            root_tests = (root / "tests").is_dir()
            if not adjacent_tests and not root_tests:
                add("DJ-TS-001", "MissingTestsForViews", "medium", "TESTS", "VIEW", tree,
                    "Views file has no adjacent tests.py/tests directory or project-level tests directory.",
                    "Add request/permission tests for the project's views.", fix_minutes=60)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if name == "mark_safe":
                    add("DJ-SC-001", "SafeFilterUsage", "high", "SECURITY", "PYTHON", node,
                        "mark_safe() disables HTML escaping for its value.",
                        "Keep autoescaping enabled or sanitize untrusted HTML with a vetted allowlist.")
                if name == "HttpResponse" and node.args and not any(
                    _call_name(child) in {"escape", "conditional_escape"}
                    for arg in node.args for child in ast.walk(arg)
                ):
                    add("DJ-SC-002", "UnescapedHttpResponse", "medium", "SECURITY", "VIEW", node,
                        "HttpResponse is constructed directly; dynamic content may be unescaped.",
                        "Use render() for templates or escape untrusted text before returning it.")

        return issues, {
            "queries_per_function": queries_per_function,
            "n_plus_one_risk": n_plus_one_risk,
            "views": self._view_metrics(tree) if is_views else {},
        }

    def _analyze_template(self, path, relative, source):
        issues = []
        lines = source.splitlines()

        def report(rule_id, rule, severity, category, line_number, message, suggestion, **kwargs):
            snippet = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
            issues.append(self._issue(
                rule_id, rule, severity, category, "TEMPLATE", relative,
                line_number, message, suggestion, snippet=snippet, **kwargs
            ))

        if path.name.lower() not in {"urls.py"}:
            for line_number, line in enumerate(lines, 1):
                if re.search(r"\{\{[^}]*[+\-*/][^}]*\}\}", line):
                    report("DJ-TP-001", "BusinessLogicInTemplate", "low", "TEMPLATES",
                           line_number, "Arithmetic or computation is embedded in a template expression.",
                           "Move computation into the view or a model property.")
                if "|safe" in line or "{% autoescape off" in line:
                    report("DJ-TP-006", "UnsafeMarkSafe", "critical", "SECURITY", line_number,
                           "Template disables automatic HTML escaping.",
                           "Remove the safe filter/autoescape override or sanitize trusted HTML explicitly.")
                if re.search(r"""(?:src|href)=["']/static/""", line) and "{% static" not in line:
                    report("DJ-TP-004", "HardcodedStaticPath", "medium", "TEMPLATES", line_number,
                           "Template hardcodes a /static/ URL.",
                           "Use {% load static %} and the {% static '...' %} tag.")
            depth = 0
            for line_number, line in enumerate(lines, 1):
                depth += len(re.findall(r"\{%\s*if\b", line))
                depth -= len(re.findall(r"\{%\s*endif\b", line))
                if depth > 3:
                    report("DJ-TP-002", "DeepNestingInTemplate", "medium", "TEMPLATES",
                           line_number, f"Template conditional nesting reaches depth {depth}.",
                           "Move decision logic into the view or an inclusion tag.",
                           metric_value=depth, threshold=3)
                    depth = 3
            for match in re.finditer(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>", source, re.IGNORECASE):
                line_number = source.count("\n", 0, match.start()) + 1
                report("DJ-TP-003", "InlineJavascriptInTemplate", "medium", "TEMPLATES",
                       line_number, "Inline JavaScript is embedded in a Django template.",
                       "Move JavaScript into a static asset and pass data using json_script.")
            if "{% static " in source and "{% load static" not in source:
                report("DJ-TP-005", "MissingLoadStatic", "medium", "TEMPLATES", 1,
                       "{% static %} is used without loading the static template library.",
                       "Add {% load static %} before using the static tag.")
            if re.search(r"""(?:href|action)=["']/(?!/)[^"'{}]+["']""", source):
                for line_number, line in enumerate(lines, 1):
                    if re.search(r"""(?:href|action)=["']/(?!/)[^"'{}]+["']""", line):
                        report("DJ-UR-001", "HardcodedURL", "medium", "URLS", line_number,
                               "Template hardcodes an internal URL.",
                               "Use the {% url %} tag so route changes do not break links.")
        return issues

    @staticmethod
    def _view_metrics(tree):
        views = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        lengths = [getattr(node, "end_lineno", node.lineno) - node.lineno + 1 for node in views]
        return {
            "view_count": len(views),
            "avg_view_loc": round(sum(lengths) / max(len(lengths), 1), 2),
            "max_view_loc": max(lengths, default=0),
            "views_without_decorator": sum(not node.decorator_list for node in views),
        }

    @staticmethod
    def _template_metrics(source):
        return {
            "lines": len(source.splitlines()),
            "if_blocks": len(re.findall(r"\{%\s*if\b", source)),
            "for_blocks": len(re.findall(r"\{%\s*for\b", source)),
            "include_tags": len(re.findall(r"\{%\s*include\b", source)),
            "extends_tags": len(re.findall(r"\{%\s*extends\b", source)),
            "blocks": len(re.findall(r"\{%\s*block\b", source)),
            "static_uses": len(re.findall(r"\{%\s*static\b", source)),
            "url_uses": len(re.findall(r"\{%\s*url\b", source)),
            "safe_filters": len(re.findall(r"\|safe\b", source)),
            "inline_scripts": len(re.findall(r"<script\b(?![^>]*\bsrc\s*=)", source, re.IGNORECASE)),
            "inline_styles": len(re.findall(r"<style\b", source, re.IGNORECASE)),
        }

    @staticmethod
    def _architecture_metrics(root, files):
        apps = sorted(
            path.parent.name for path in files
            if path.name == "apps.py" and path.parent != root
        )
        fat_models = 0
        fat_views = 0
        for app in apps:
            for filename, threshold, key in (
                ("models.py", 300, "fat_models"),
                ("views.py", 500, "fat_views"),
            ):
                path = root / app / filename
                if path.is_file():
                    try:
                        if len(path.read_text(encoding="utf-8", errors="ignore").splitlines()) > threshold:
                            if key == "fat_models":
                                fat_models += 1
                            else:
                                fat_views += 1
                    except OSError:
                        continue
        return {
            "apps": apps,
            "app_count": len(apps),
            "fat_models": fat_models,
            "fat_views": fat_views,
        }
