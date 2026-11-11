"""Node.js project checks and framework metrics."""

import json
import re
from pathlib import Path

from debt_analyzer.models import DebtIssue
from debt_analyzer.rules.base_rule import BaseRule
from scanner.config import IGNORE_DIRS


SEVERITY_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0.5}
JS_EXTENSIONS = {".js", ".mjs", ".cjs", ".ts"}
TEMPLATE_EXTENSIONS = {".html", ".ejs", ".hbs", ".pug"}
ENTRY_NAMES = {"app.js", "server.js", "index.js", "main.js"}
FRAMEWORK_NAMES = {
    "express": "express",
    "@nestjs/core": "nest",
    "fastify": "fastify",
    "koa": "koa",
}


class NodeProjectAnalysisRule(BaseRule):
    """Analyze Node projects using project/package context and source paths."""

    name = "NodeFrameworkAnalysis"

    def analyze(self, context):
        root = Path(context.project.project_path).resolve()
        if not root.is_dir():
            return []

        files = list(self._project_files(root))
        package_path = root / "package.json"
        package_data = self._read_package(package_path) if package_path.is_file() else {}
        valid_package_data = isinstance(package_data, dict)
        package_data = package_data if valid_package_data else {}
        dependencies = {
            **(package_data.get("dependencies") or {}),
            **(package_data.get("devDependencies") or {}),
        }
        framework = next(
            (name for dependency, name in FRAMEWORK_NAMES.items() if dependency in dependencies),
            "none",
        )
        lockfile = next(
            (
                name for name in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")
                if (root / name).is_file()
            ),
            None,
        )
        has_env_example = (root / ".env.example").is_file()
        context_info = {
            "framework": framework,
            "dependencies": dependencies,
            "has_lockfile": lockfile is not None,
            "has_env_example": has_env_example,
        }
        issues = []
        package_metrics = self._package_metrics(package_data, lockfile)
        dependency_metrics = self._dependency_metrics(package_data)
        async_metrics = {}
        security_metrics = {}
        route_metrics = {}
        source_text = {}

        if package_path.is_file():
            try:
                package_source = package_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                package_source = ""
            if not valid_package_data:
                issues.append(self._issue(
                    "ND-PK-003", "InvalidPackageManifest", "high", "PACKAGE", "PACKAGE",
                    "package.json", 1,
                    "package.json could not be parsed as a JSON object.",
                    "Fix the JSON syntax and validate the manifest before installing dependencies.",
                ))
            else:
                runtime_parts = []
                for source_path in files:
                    if source_path.suffix.lower() not in JS_EXTENSIONS:
                        continue
                    try:
                        runtime_parts.append(
                            source_path.read_text(encoding="utf-8", errors="ignore")
                        )
                    except OSError:
                        continue
                issues.extend(self._package_issues(
                    package_data, package_source, context_info, "\n".join(runtime_parts)
                ))

        for path in files:
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            source_text[path] = source

            if path.suffix.lower() in JS_EXTENSIONS:
                line_map = self._line_map(source)
                normalized_relative = relative.lower()
                in_frontend = any(
                    segment in normalized_relative.split("/")
                    for segment in ("public", "client", "frontend", "static")
                )
                is_server = not in_frontend and (
                    any(segment in normalized_relative.split("/") for segment in
                        ("server", "routes", "controllers", "middleware", "api"))
                    or path.name.lower() in ENTRY_NAMES
                    or framework != "none"
                )
                async_metrics[relative] = self._async_metrics(source)
                security_metrics[relative] = self._security_metrics(source)
                if framework in {"express", "koa", "fastify"}:
                    route_metrics[relative] = self._route_metrics(source, framework)
                issues.extend(self._javascript_issues(
                    path, relative, source, line_map,
                    framework, is_server, in_frontend,
                ))
            elif path.name == "package.json":
                continue
            elif path.suffix.lower() in TEMPLATE_EXTENSIONS:
                issues.extend(self._template_issues(relative, source))

        issues.extend(self._project_config_issues(root, files, context_info, source_text))
        issues.extend(self._circular_require_issues(root, files, source_text))
        total_weight = sum(SEVERITY_WEIGHT.get(issue.severity.lower(), 1) for issue in issues)
        code_files = sum(path.suffix.lower() in JS_EXTENSIONS for path in files)
        summary = {
            "total_issues": len(issues),
            "critical": sum(issue.severity.lower() == "critical" for issue in issues),
            "high": sum(issue.severity.lower() == "high" for issue in issues),
            "medium": sum(issue.severity.lower() == "medium" for issue in issues),
            "low": sum(issue.severity.lower() == "low" for issue in issues),
            "debt_score": round(min(100, total_weight / max(code_files, 1) * 5), 2),
            "framework": framework,
        }
        context.project.statistics["node_analysis"] = {
            "stack": "nodejs",
            "framework": framework,
            "summary": summary,
            "metrics": {
                "packages": package_metrics,
                "async": async_metrics,
                "dependencies": dependency_metrics,
                "routes": route_metrics,
                "security": security_metrics,
            },
        }
        return issues

    @staticmethod
    def _project_files(root):
        for path in root.rglob("*"):
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
                continue
            normalized = {part.lower() for part in path.parts}
            if normalized.intersection({"dist", "coverage", ".next", "vendor"}):
                continue
            if path.suffix.lower() in JS_EXTENSIONS | TEMPLATE_EXTENSIONS or path.name in {
                "package.json", ".env", ".env.local",
            }:
                yield path

    @staticmethod
    def _read_package(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _issue(rule_id, rule, severity, category, layer, path, line, message, suggestion,
               *, column=0, metric_value=None, threshold=None, framework=None, fix_minutes=10,
               snippet=""):
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
            language="Node.js",
            code_snippet=snippet,
            refactoring_pattern=suggestion,
            estimated_fix_minutes=fix_minutes,
            layer=layer,
            node_version_aware=True,
            framework=framework,
        )

    def _package_issues(self, package, source, ctx, runtime_source):
        path = "package.json"
        issues = []
        line = lambda pattern: self._line_number(source, pattern)

        if not ctx["has_lockfile"]:
            issues.append(self._issue(
                "ND-PK-001", "MissingLockfile", "high", "PACKAGE", "PACKAGE",
                path, 1, "No npm, Yarn, or pnpm lockfile was found.",
                "Commit the package manager lockfile to make installs reproducible.",
            ))
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for dependency, version in (package.get(section) or {}).items():
                if not isinstance(version, str):
                    continue
                if version in {"*", "latest", ""} or version.startswith(">"):
                    issues.append(self._issue(
                        "ND-PK-002", "WildcardDependency", "high", "PACKAGE", "PACKAGE",
                        path, line(re.escape(dependency)),
                        f"Dependency '{dependency}' uses non-reproducible version '{version}'.",
                        "Use a deliberate semver range and commit the lockfile.",
                        snippet=f"{dependency}: {version}",
                    ))
        scripts = package.get("scripts") or {}
        missing = [name for name in ("test", "start") if name not in scripts]
        if missing:
            issues.append(self._issue(
                "ND-PK-003", "MissingTestScript", "medium", "PACKAGE", "PACKAGE",
                path, 1, f"package.json is missing scripts: {', '.join(missing)}.",
                "Define the expected project test/start scripts or document the alternative workflow.",
            ))
        if not package.get("engines", {}).get("node"):
            issues.append(self._issue(
                "ND-PK-004", "MissingEnginesField", "low", "PACKAGE", "PACKAGE",
                path, 1, "package.json does not declare a supported Node.js version.",
                "Declare the Node.js range tested by CI in package.json engines.node.",
            ))
        production_names = set((package.get("dependencies") or {}).keys())
        dev_names = set((package.get("devDependencies") or {}).keys())
        runtime_imports = {
            name
            for name in production_names & dev_names
            if re.search(rf"""(?:require\s*\(\s*['"]{re.escape(name)}['"]|from\s+['"]{re.escape(name)}['"])""", runtime_source)
        }
        for dependency in sorted(runtime_imports):
            issues.append(self._issue(
                "ND-PK-005", "DevDependencyInProduction", "high", "PACKAGE", "PACKAGE",
                path, line(re.escape(dependency)),
                f"Runtime source imports '{dependency}', but it is declared as a development dependency.",
                "Move runtime dependencies to dependencies so production installations include them.",
            ))

        known_vulnerable = {
            "lodash": ("4.17.21", "Prototype pollution is reported in older lodash versions."),
            "minimist": ("1.2.6", "Prototype pollution is reported in older minimist versions."),
            "minimatch": ("3.0.5", "Regular-expression denial-of-service is reported in older minimatch versions."),
            "axios": ("0.21.1", "Security fixes are missing from older axios versions."),
        }
        for dependency, version in (package.get("dependencies") or {}).items():
            if dependency not in known_vulnerable or not isinstance(version, str):
                continue
            fixed, message = known_vulnerable[dependency]
            parsed = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
            if parsed and tuple(map(int, parsed.groups())) < tuple(map(int, fixed.split("."))):
                issues.append(self._issue(
                    "ND-PK-006", "KnownVulnerablePackage", "high", "PACKAGE", "PACKAGE",
                    path, line(re.escape(dependency)),
                    f"{dependency}@{version} may be below the known fixed version {fixed}: {message}",
                    "Confirm against an up-to-date advisory database and upgrade to a supported patched release.",
                ))
        return issues

    @staticmethod
    def _package_metrics(package, lockfile):
        return {
            "dependencies": len(package.get("dependencies") or {}),
            "devDependencies": len(package.get("devDependencies") or {}),
            "peerDependencies": len(package.get("peerDependencies") or {}),
            "scripts": sorted((package.get("scripts") or {}).keys()),
            "engines": package.get("engines") or {},
            "lockfile": lockfile,
        }

    @staticmethod
    def _dependency_metrics(package):
        production = package.get("dependencies") or {}
        development = package.get("devDependencies") or {}
        dev_names = set(development)
        return {
            "total": len(production) + len(development),
            "production": len(production),
            "dev": len(development),
            "ratio_dev_to_prod": round(len(development) / max(len(production), 1), 2),
            "has_typescript": "typescript" in dev_names,
            "has_eslint": "eslint" in dev_names,
            "has_prettier": "prettier" in dev_names,
            "has_test_runner": bool(dev_names & {"jest", "mocha", "vitest", "ava"}),
        }

    def _javascript_issues(self, path, relative, source, lines, framework,
                           is_server, in_frontend):
        issues = []
        route_pattern = r"\b(?:app|router)\.(?:get|post|put|patch|delete)\s*\("
        is_express_entry = path.name.lower() in ENTRY_NAMES

        def add(rule_id, rule, severity, category, layer, pattern, message, suggestion,
                *, threshold=None, fix=10, flags=re.IGNORECASE):
            matches = list(re.finditer(pattern, source, flags))
            for match in matches:
                line_number = source.count("\n", 0, match.start()) + 1
                snippet = lines[line_number - 1].strip() if line_number <= len(lines) else ""
                issues.append(self._issue(
                    rule_id, rule, severity, category, layer, relative, line_number,
                    message, suggestion, column=match.start() - source.rfind("\n", 0, match.start()) - 1,
                    threshold=threshold, framework=framework, fix_minutes=fix, snippet=snippet,
                ))

        if re.search(r"\beval\s*\(|new\s+Function\s*\(", source):
            add("ND-SC-002", "UnsafeEval", "high", "SECURITY", "MODULE",
                r"\beval\s*\(|new\s+Function\s*\(",
                "Dynamic code execution is difficult to validate and can execute attacker-controlled input.",
                "Replace eval/Function with explicit, validated logic.")
        add("ND-SC-001", "UnsafeChildProcess", "critical", "SECURITY", "SERVER",
            r"\b(?:exec|execSync)\s*\(\s*[^,)]*(?:\$\{|['\"].*\+)",
            "Shell command is assembled from dynamic content.",
            "Use execFile/spawn with a fixed executable and validated argument array.")
        add("ND-SC-003", "WeakJWTSecret", "critical", "SECURITY", "SERVER",
            r"""jwt\.sign\s*\([^;\n]*,\s*['"][^'"]{1,31}['"]""",
            "JWT signing appears to use a short hardcoded secret.",
            "Load a high-entropy signing key from a managed secret store.")
        add("ND-SC-004", "WeakHashAlgorithm", "high", "SECURITY", "SERVER",
            r"""createHash\s*\(\s*['"](?:md5|sha1)['"]""",
            "MD5/SHA-1 is used for hashing and is unsuitable for security-sensitive integrity.",
            "Use a modern cryptographic hash for integrity; use a password-specific KDF for passwords.")
        add("ND-SC-005", "HardcodedCredentials", "critical", "SECURITY", "SERVER",
            r"""(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['"][^'"]{4,}['"]""",
            "A credential-like literal is present in source code.",
            "Move credentials to a secret manager or environment configuration.")
        add("ND-SC-006", "NoSQLInjectionRisk", "high", "SECURITY", "DATABASE",
            r"""(?:find|findOne|updateOne|deleteOne)\s*\(\s*\{\s*[\w$.]+\s*:\s*(?:req\.(?:body|query|params)|\$\{)""",
            "Unvalidated request data is used directly in a NoSQL query object.",
            "Validate and allowlist query fields and scalar values before building database filters.")
        add("ND-SC-007", "SQLInjectionRisk", "critical", "SECURITY", "DATABASE",
            r"""\.query\s*\(\s*(?:`[^`]*\$\{|['"][^'"]*['"]\s*\+)""",
            "SQL query text is dynamically interpolated or concatenated.",
            "Use parameterized query placeholders for all data values.")
        add("ND-SC-008", "InsecureRandomness", "medium", "SECURITY", "SERVER",
            r"\bMath\.random\s*\(",
            "Math.random() is not cryptographically secure.",
            "Use crypto.randomBytes() or crypto.randomInt() for tokens and security-sensitive values.")

        if is_server:
            if framework == "express":
                if is_express_entry:
                    route_count = len(list(re.finditer(route_pattern, source, re.I)))
                    if route_count and route_count > 10:
                        issues.append(self._issue(
                            "ND-EX-001", "FatRouteHandler", "high", "EXPRESS", "ROUTE",
                            relative, 1, f"Entry module declares {route_count} HTTP routes.",
                            "Move related endpoints into focused routers/controllers.",
                            metric_value=route_count, threshold=10, framework=framework,
                        ))
                    if route_count and not re.search(r"\b(?:express\.Router|router\s*=)", source):
                        issues.append(self._issue(
                            "ND-EX-002", "NoRouterSeparation", "medium", "EXPRESS", "ROUTE",
                            relative, 1, "Routes are declared in the application entry module.",
                            "Extract route groups into Express Router modules.", framework=framework,
                        ))
                for match in re.finditer(route_pattern, source, re.I):
                    route_tail = source[match.start():match.start() + 700]
                    route_line = source.count("\n", 0, match.start()) + 1
                    if re.search(r"\breq\.(?:body|query|params)\b", route_tail[:500]) and not re.search(
                        r"\b(?:validate|validator|schema|zod|joi|yup|express-validator)\b", route_tail[:500], re.I
                    ):
                        issues.append(self._issue(
                            "ND-EX-003", "RouteWithoutValidation", "high", "EXPRESS", "ROUTE",
                            relative, route_line, "Route consumes request data without evident input validation.",
                            "Validate route parameters and request bodies with an explicit schema.",
                            framework=framework,
                        ))
                    if re.search(r"=>\s*\{", route_tail[:200]):
                        issues.append(self._issue(
                            "ND-EX-006", "InlineRouteHandler", "low", "EXPRESS", "ROUTE",
                            relative, route_line, "Route handler logic is defined inline.",
                            "Extract non-trivial handlers into named controller functions.",
                            framework=framework,
                        ))
                if is_express_entry and not re.search(r"\bhelmet\s*\(", source):
                    issues.append(self._issue(
                        "ND-EX-004", "MissingSecurityHeaders", "high", "SECURITY", "MIDDLEWARE",
                        relative, 1, "Express app does not appear to install Helmet security headers.",
                        "Install and configure Helmet with application-appropriate policies.",
                        framework=framework,
                    ))
                if is_express_entry and not re.search(r"\bcors\s*\(", source):
                    issues.append(self._issue(
                        "ND-EX-005", "MissingCORSConfig", "medium", "SECURITY", "MIDDLEWARE",
                        relative, 1, "Express app has no explicit CORS middleware configuration.",
                        "Configure CORS for specific trusted origins if cross-origin access is required.",
                        framework=framework,
                    ))
                if is_express_entry and not re.search(r"(?:app|server)\.use\s*\(\s*(?:async\s*)?\(?\s*(?:err|error)\b|function\s*\(\s*(?:err|error)\b", source):
                    issues.append(self._issue(
                        "ND-MW-001", "MissingErrorMiddleware", "high", "ERROR", "MIDDLEWARE",
                        relative, 1, "Express app has no recognizable four-argument error middleware.",
                        "Add centralized (err, req, res, next) error handling after routes.",
                        framework=framework,
                    ))
                middleware_positions = [
                    source.find(token) for token in ("express.static", "app.use")
                    if source.find(token) >= 0
                ] if is_express_entry else []
                if is_express_entry and len(middleware_positions) > 1 and "express.static" in source and source.find("express.static") < source.find("app.use"):
                    issues.append(self._issue(
                        "ND-MW-002", "SuspiciousMiddlewareOrder", "low", "MIDDLEWARE", "MIDDLEWARE",
                        relative, source.count("\n", 0, source.find("express.static")) + 1,
                        "Static middleware is mounted before other app middleware; verify intended security and logging order.",
                        "Review middleware ordering and keep security, logging, and route behavior explicit.",
                        framework=framework,
                    ))
                if is_express_entry and not re.search(r"\b(?:rateLimit|rateLimiter|slowDown)\s*\(", source):
                    issues.append(self._issue(
                        "ND-MW-003", "MissingRateLimit", "medium", "SECURITY", "MIDDLEWARE",
                        relative, 1, "No rate-limiting middleware is visible in this Express module.",
                        "Apply configurable rate limits to authentication and other abuse-sensitive routes.",
                        framework=framework,
                    ))
                if is_express_entry and re.search(r"express\.(?:json|urlencoded)\s*\(\s*\)", source):
                    issues.append(self._issue(
                        "ND-MW-004", "UnboundedBodyParser", "medium", "PERFORMANCE", "MIDDLEWARE",
                        relative, self._line_number(source, r"express\.(?:json|urlencoded)"),
                        "Body parser is configured without an explicit payload limit.",
                        "Set a request-size limit appropriate to the API's upload contract.",
                        framework=framework,
                    ))
                if is_express_entry and "compression" not in source:
                    issues.append(self._issue(
                        "ND-MW-005", "MissingCompression", "low", "PERFORMANCE", "MIDDLEWARE",
                        relative, 1, "No response compression middleware is visible.",
                        "Consider compression at the app or reverse-proxy layer after measuring payloads.",
                        framework=framework,
                    ))

            if re.search(r"\basync\s+(?:function\b|[\w$]+\s*=>|\([^)]*\)\s*=>)", source):
                if not re.search(r"\btry\s*\{", source) and not re.search(r"\.catch\s*\(", source):
                    add("ND-AS-003", "AsyncWithoutTryCatch", "medium", "ASYNC", "SERVER",
                        r"\basync\s+(?:function\b|[\w$]+\s*=>|\([^)]*\)\s*=>)",
                        "Async code has no visible rejection handling in this source file.",
                        "Handle rejected promises at the operation boundary or in centralized middleware.")
            add("ND-AS-001", "UnhandledPromise", "high", "ASYNC", "SERVER",
                r"\.then\s*\([^;\n]*(?:;|\n|$)(?!\s*\.catch)",
                "Promise chain may not handle rejection.",
                "Add a rejection handler or return/await the promise into a handled boundary.")
            add("ND-AS-002", "FloatingPromise", "medium", "ASYNC", "SERVER",
                r"(?m)^\s*(?!return\b|await\b|void\b)(?:[\w$.]+\([^;\n]*\))\.then\s*\(",
                "Promise chain is started without an evident await/return at the call site.",
                "Return or await the promise, or explicitly handle intentional fire-and-forget work.")
            callback_depth = self._callback_depth(source)
            if callback_depth > 3:
                issues.append(self._issue(
                    "ND-AS-004", "CallbackHell", "medium", "ASYNC", "SERVER", relative, 1,
                    f"Callback nesting reaches depth {callback_depth}.",
                    "Flatten control flow with promises or async/await.",
                    metric_value=callback_depth, threshold=3, framework=framework,
                ))
            add("ND-AS-005", "BlockingCallOnEventLoop", "high", "ASYNC", "SERVER",
                r"\b(?:readFileSync|writeFileSync|appendFileSync|existsSync|readdirSync|execSync|pbkdf2Sync)\s*\(",
                "Synchronous I/O or computation can block the Node.js event loop.",
                "Use the asynchronous API or move CPU-heavy work to a worker thread.")
            add("ND-AS-006", "SequentialAwaitInLoop", "medium", "ASYNC", "SERVER",
                r"(?s)\b(?:for|while)\s*\([^)]*\)\s*\{[^{}]*\bawait\b",
                "Await inside a loop serializes independent asynchronous work.",
                "Use bounded concurrency or Promise.all when operations are independent.")

            if re.search(r"\b(?:find|findOne)\s*\(", source) and "mongoose" in source.lower() and ".lean(" not in source:
                add("ND-DB-001", "MongooseWithoutLean", "low", "DATABASE", "DATABASE",
                    r"\.(?:find|findOne)\s*\(",
                    "Read-only Mongoose queries may be hydrating full documents.",
                    "Use .lean() for read-only results when document methods and middleware are not needed.")
            if re.search(r"\b(?:for|while)\s*\(", source) and re.search(r"\b(?:await\s+)?[\w$.]+\.(?:find|findOne|query|save|create)\s*\(", source):
                add("ND-DB-002", "QueryInsideLoop", "high", "DATABASE", "DATABASE",
                    r"\b(?:for|while)\s*\(",
                    "Database operations appear inside a loop and may create N+1 query behavior.",
                    "Batch the operation or fetch the required records in one query.")
            if len(re.findall(r"\.(?:save|create|updateOne|updateMany|deleteOne|deleteMany)\s*\(", source)) > 1 and "transaction" not in source.lower():
                add("ND-DB-003", "MissingTransaction", "medium", "DATABASE", "DATABASE",
                    r"\.(?:save|create|updateOne|updateMany|deleteOne|deleteMany)\s*\(",
                    "Multiple database writes have no evident transaction boundary.",
                    "Use a transaction when these writes must commit or roll back together.")
            add("ND-DB-004", "UnboundedFind", "medium", "DATABASE", "DATABASE",
                r"\.(?:find|findMany)\s*\(\s*(?:\{\s*\})?\s*\)(?![\s\S]{0,100}\.(?:limit|take)\s*\()",
                "Database find query has no visible result bound.",
                "Add pagination or an explicit result limit for potentially large collections.")

            if "require(" in source and "from " in source and "import " in source:
                add("ND-MO-002", "MixedModuleSystems", "low", "MODULE", "MODULE",
                    r"\brequire\s*\(",
                    "CommonJS require and ES module imports coexist in one module.",
                    "Standardize on the package's declared module system.")
            add("ND-MO-003", "DeepRelativeImport", "low", "MODULE", "MODULE",
                r"""(?:from\s+|require\s*\(\s*)['"](?:\.\./){3,}""",
                "Deep relative import traverses several directory levels.",
                "Use a stable package alias or reorganize module boundaries.")
            add("ND-MO-004", "RequireInsideFunction", "low", "MODULE", "MODULE",
                r"\bfunction\b[^{]*\{[\s\S]{0,300}\brequire\s*\(",
                "require() is nested inside a function body.",
                "Move static imports to module scope unless lazy loading is intentional.")

            for match in re.finditer(r"\bcatch\s*\([^)]*\)\s*\{\s*\}", source):
                issues.append(self._issue(
                    "ND-ER-001", "EmptyCatchBlock", "high", "ERROR", "SERVER",
                    relative, source.count("\n", 0, match.start()) + 1,
                    "Exception is caught and silently discarded.",
                    "Handle the failure, add useful context to logs, or rethrow it.",
                    framework=framework,
                ))
            add("ND-ER-002", "ConsoleErrorInsteadOfLogger", "low", "LOGGING", "SERVER",
                r"\bconsole\.error\s*\(",
                "Direct console.error bypasses structured application logging.",
                "Use the service logger with contextual fields and appropriate severity.")
            add("ND-ER-003", "ThrowNonError", "medium", "ERROR", "SERVER",
                r"\bthrow\s+['\"`]",
                "A string is thrown instead of an Error object.",
                "Throw Error or a typed error subclass to preserve stack and metadata.")
            if re.search(r"\bprocess\.exit\s*\(", source) and path.name.lower() not in ENTRY_NAMES:
                add("ND-ER-004", "ProcessExitInLibrary", "high", "ERROR", "MODULE",
                    r"\bprocess\.exit\s*\(",
                    "Library or non-entry module terminates the whole process.",
                    "Propagate the error and let the application entry point decide how to shut down.")
            if is_server and path.name.lower() in ENTRY_NAMES and not re.search(r"process\.on\s*\(\s*['\"](?:uncaughtException|unhandledRejection)", source):
                issues.append(self._issue(
                    "ND-ER-005", "NoUncaughtHandlers", "medium", "ERROR", "SERVER",
                    relative, 1, "Entry module has no explicit process-level rejection/exception shutdown policy.",
                    "Define a safe process-level logging and graceful-shutdown policy; do not resume after corrupted state.",
                    framework=framework,
                ))

            add("ND-PF-001", "JsonParseInLoop", "medium", "PERFORMANCE", "SERVER",
                r"(?s)\b(?:for|while)\s*\([^)]*\)\s*\{[^{}]*JSON\.parse\s*\(",
                "JSON parsing occurs inside a loop.",
                "Parse once before iteration or reduce repeated serialization work.")
            add("ND-PF-002", "RegexCompiledInLoop", "low", "PERFORMANCE", "SERVER",
                r"(?s)\b(?:for|while)\s*\([^)]*\)\s*\{[^{}]*new\s+RegExp\s*\(",
                "Regular expression is constructed inside a loop.",
                "Create the regular expression once outside the loop.")
            add("ND-PF-003", "JsonDeepClone", "low", "PERFORMANCE", "SERVER",
                r"JSON\.parse\s*\(\s*JSON\.stringify\s*\(",
                "JSON stringify/parse is used as a deep-clone operation.",
                "Use structuredClone where supported or a domain-specific copy function.")
            if is_server and re.search(r"\b(?:readFileSync|writeFileSync|readdirSync|existsSync)\s*\(", source):
                add("ND-PF-004", "SyncIoInRequestPath", "high", "PERFORMANCE", "SERVER",
                    r"\b(?:readFileSync|writeFileSync|readdirSync|existsSync)\s*\(",
                    "Synchronous filesystem I/O may block request handling.",
                    "Use asynchronous I/O or perform file access outside the request path.")

            env_reads = len(re.findall(r"\bprocess\.env\.[A-Za-z_]\w*", source))
            if env_reads > 5:
                issues.append(self._issue(
                    "ND-CF-003", "ScatteredProcessEnvAccess", "medium", "CONFIG", "CONFIG",
                    relative, 1, f"{env_reads} direct process.env reads are spread through this module.",
                    "Validate environment configuration once at startup and inject typed settings.",
                    metric_value=env_reads, threshold=5, framework=framework,
                ))
            if in_frontend and path.parent.name.lower() == "public":
                console_count = len(re.findall(r"\bconsole\.(?:log|debug|info)\s*\(", source))
                if console_count > 3:
                    issues.append(self._issue(
                        "ND-FE-003", "FrontendConsoleLeft", "low", "FRONTEND", "FRONTEND",
                        relative, 1, f"{console_count} debug console statements remain in a public JavaScript asset.",
                        "Remove debugging output or strip it from production builds.",
                        metric_value=console_count, threshold=3, framework=framework,
                    ))
        return issues

    def _template_issues(self, relative, source):
        issues = []
        inline_pattern = r"<script\b(?![^>]*\bsrc\s*=)[^>]*>|<style\b[^>]*>|\sstyle\s*="
        if re.search(inline_pattern, source, re.I):
            match = re.search(inline_pattern, source, re.I)
            issues.append(self._issue(
                "ND-FE-001", "InlineStyleAndScript", "medium", "FRONTEND", "FRONTEND",
                relative, source.count("\n", 0, match.start()) + 1,
                "Template contains inline JavaScript or CSS styling.",
                "Move reusable scripts and styles to static assets.",
            ))
        return issues

    def _project_config_issues(self, root, files, ctx, sources):
        issues = []
        env_path = next(
            (root / name for name in (".env", ".env.local") if (root / name).is_file()),
            None,
        )
        if env_path:
            gitignore = root / ".gitignore"
            ignored = False
            if gitignore.is_file():
                try:
                    ignored = bool(re.search(r"(?m)^\s*\.env(?:\*|$)", gitignore.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    ignored = False
            if not ignored:
                issues.append(self._issue(
                    "ND-CF-001", "EnvFileCommitted", "critical", "CONFIG", "CONFIG",
                    env_path.name, 1,
                    "Environment file exists and is not excluded by a .gitignore rule.",
                    "Ignore the environment file, verify it is not tracked, and rotate any exposed secrets.",
                ))
        if any(path.name == "package.json" for path in files) and not ctx["has_env_example"]:
            issues.append(self._issue(
                "ND-CF-002", "MissingEnvExample", "low", "CONFIG", "CONFIG",
                "package.json", 1, "No .env.example documents required environment variable names.",
                "Provide a secret-free .env.example with required keys and safe placeholders.",
            ))
        html_files = [path for path in files if path.suffix.lower() in TEMPLATE_EXTENSIONS]
        if html_files and re.search(r"\bexpress\.static\s*\(", "\n".join(sources.values())):
            path = html_files[0]
            static_server = "\n".join(
                text for file_path, text in sources.items()
                if file_path.name.lower() in ENTRY_NAMES
            )
            if "maxAge" not in static_server and "max-age" not in static_server:
                relative = path.relative_to(root).as_posix()
                issues.append(self._issue(
                    "ND-FE-002", "MissingStaticCacheHeaders", "medium", "FRONTEND", "MIDDLEWARE",
                    relative, 1, "Static assets are served without evident cache headers.",
                    "Set an appropriate static asset maxAge/cache policy, using content hashes for long-lived caching.",
                ))
        return issues

    def _circular_require_issues(self, root, files, sources):
        modules = {
            path.resolve(): path.relative_to(root).as_posix()
            for path in files if path.suffix.lower() in JS_EXTENSIONS
        }
        graph = {}
        for path in modules:
            source = sources.get(path, "")
            targets = set()
            for specifier in re.findall(r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)""", source):
                candidate = (path.parent / specifier).resolve()
                choices = [candidate, *(candidate.with_suffix(ext) for ext in JS_EXTENSIONS)]
                target = next((choice for choice in choices if choice in modules), None)
                if target:
                    targets.add(target)
            graph[path] = targets

        issues = []
        emitted = set()
        for origin, targets in graph.items():
            for target in targets:
                if target in graph.get(origin, set()) and origin in graph.get(target, set()):
                    pair = frozenset((origin, target))
                    if pair in emitted:
                        continue
                    emitted.add(pair)
                    issues.append(self._issue(
                        "ND-MO-001", "CircularDependency", "high", "MODULE", "MODULE",
                        modules[origin], 1,
                        f"Relative imports form a circular module dependency with {modules[target]}.",
                        "Extract shared contracts or move responsibilities to remove the cycle.",
                    ))
        return issues

    @staticmethod
    def _line_map(source):
        return source.splitlines()

    @staticmethod
    def _line_number(source, pattern):
        match = re.search(pattern, source, re.I)
        return source.count("\n", 0, match.start()) + 1 if match else 1

    @staticmethod
    def _callback_depth(source):
        depth = maximum = 0
        for line in source.splitlines():
            if re.search(r"=>\s*\{|function\s*\([^)]*\)\s*\{", line):
                depth += len(re.findall(r"=>\s*\{|function\s*\([^)]*\)\s*\{", line))
                maximum = max(maximum, depth)
            depth = max(0, depth - line.count("}"))
        return maximum

    @staticmethod
    def _async_metrics(source):
        return {
            "await_count": len(re.findall(r"\bawait\b", source)),
            "async_functions": len(re.findall(r"\basync\s+(?:function\b|[\w$]+\s*=>|\()", source)),
            "then_count": len(re.findall(r"\.then\s*\(", source)),
            "catch_count": len(re.findall(r"\.catch\s*\(", source)),
            "promise_all": len(re.findall(r"\bPromise\.all\s*\(", source)),
            "promise_race": len(re.findall(r"\bPromise\.race\s*\(", source)),
            "callback_nesting_max": NodeProjectAnalysisRule._callback_depth(source),
            "try_catch_blocks": len(re.findall(r"\btry\s*\{", source)),
            "throw_count": len(re.findall(r"\bthrow\s+", source)),
        }

    @staticmethod
    def _security_metrics(source):
        return {
            "eval_calls": len(re.findall(r"\beval\s*\(", source)),
            "innerHTML": len(re.findall(r"\.innerHTML\s*=", source)),
            "exec_calls": len(re.findall(r"\b(?:child_process\.)?(?:exec|execSync)\s*\(", source)),
            "raw_sql": len(re.findall(r"\.query\s*\(\s*`[^`]*\$\{", source)),
            "hardcoded_secrets": len(re.findall(
                r"""(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['"][^'"]{4,}['"]""",
                source, re.I,
            )),
            "jwt_signs": len(re.findall(r"\bjwt\.sign\s*\(", source)),
            "crypto_md5_sha1": len(re.findall(r"""createHash\s*\(\s*['"](?:md5|sha1)['"]""", source)),
            "process_env": len(re.findall(r"\bprocess\.env\.", source)),
        }

    @staticmethod
    def _route_metrics(source, framework):
        methods = re.findall(
            r"\b(?:app|router|fastify)\.(get|post|put|patch|delete)\s*\(",
            source, re.I,
        )
        return {
            "route_count": len(methods),
            "gets": sum(method.lower() == "get" for method in methods),
            "writes": sum(method.lower() in {"post", "put", "patch", "delete"} for method in methods),
            "middleware_count": len(re.findall(r"\b(?:app|router)\.use\s*\(", source)),
            "framework": framework,
        }
