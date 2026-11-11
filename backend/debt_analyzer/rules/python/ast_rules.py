import ast
from collections import defaultdict
from pathlib import Path

from debt_analyzer.models import DebtIssue
from debt_analyzer.rules.base_rule import BaseRule
from scanner.utils.file_utils import get_python_files, read_source
from scanner.utils.logger import logger


def get_python_ast_files(context):
    cached = context.python_ast_cache.get("files")
    if cached is not None:
        return cached

    root = Path(context.project.project_path)
    files = []
    for path in get_python_files(root):
        source = read_source(path)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            logger.warning(f"Python AST analysis: cannot analyze {path}: {exc}")
            continue
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        files.append((path, tree, parents))

    context.python_ast_cache["files"] = files
    return files


class PythonAstRule(BaseRule):
    """Base for Python rules that need the source AST, including module functions."""

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        for path, tree, parents in get_python_ast_files(context):
            issues.extend(self.analyze_file(tree, path, root, parents))
        return issues

    def analyze_file(self, _tree, _path, _root, _parents):
        _ = (_tree, _path, _root, _parents)
        raise NotImplementedError

    def _issue(self, path, root, node, parents, message, suggestion, severity="medium",
               metric_value=None, metric_threshold=None):
        relative_path = str(path.relative_to(root))
        method_name = None
        owner_name = relative_path
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_name = node.name
        elif isinstance(node, ast.ClassDef):
            owner_name = node.name
        current = node
        while current in parents:
            current = parents[current]
            if method_name is None and isinstance(
                current, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                method_name = current.name
            if isinstance(current, ast.ClassDef):
                owner_name = current.name
                break

        return DebtIssue(
            rule=self.name,
            severity=severity,
            class_name=owner_name,
            file_path=relative_path,
            method_name=method_name,
            line_number=getattr(node, "lineno", 1),
            message=message,
            suggestion=suggestion,
            metric_value=metric_value,
            metric_threshold=metric_threshold,
        )


class PythonTooManyParametersRule(PythonAstRule):
    name = "ExcessiveParameterList"
    threshold = 5

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            count = sum(arg.arg not in {"self", "cls"} for arg in (
                args.posonlyargs + args.args + args.kwonlyargs
            ))
            count += bool(args.vararg)
            count += bool(args.kwarg)
            if count > self.threshold:
                issues.append(self._issue(
                    path, root, node, parents,
                    f"Function '{node.name}' has {count} parameters (limit {self.threshold}).",
                    "Group related arguments in a typed configuration/dataclass object.",
                    severity="high" if count >= 8 else "medium",
                    metric_value=count,
                    metric_threshold=self.threshold,
                ))
        return issues


class PythonEmptyExceptRule(PythonAstRule):
    name = "EmptyExceptBlock"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = node.body
            is_docstring_only = (
                len(body) == 1
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            )
            if len(body) == 1 and (
                isinstance(body[0], ast.Pass)
                or isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and body[0].value.value is Ellipsis
                or is_docstring_only
            ):
                issues.append(self._issue(
                    path, root, node, parents,
                    "Exception handler is empty and discards the failure.",
                    "Log useful context, recover explicitly, or re-raise the exception.",
                    severity="high",
                ))
        return issues


class PythonBroadExceptRule(PythonAstRule):
    name = "BroadExceptionHandling"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            catches_everything = node.type is None or (
                isinstance(node.type, ast.Name) and node.type.id == "Exception"
            )
            if catches_everything:
                issues.append(self._issue(
                    path, root, node, parents,
                    "Broad exception handler can hide unrelated programming errors.",
                    "Catch the specific exceptions this code can recover from.",
                    severity="medium",
                ))
        return issues


class PythonUnsafeEvalRule(PythonAstRule):
    name = "UnsafeDynamicExecution"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec"}:
                    issues.append(self._issue(
                        path, root, node, parents,
                        f"Dynamic code execution via {node.func.id}() can execute untrusted input.",
                        "Replace dynamic execution with explicit parsing and validated operations.",
                        severity="critical",
                    ))
        return issues


class PythonSqlInjectionRule(PythonAstRule):
    name = "SqlInjection"
    SQL_MARKERS = ("select ", "insert ", "update ", "delete ", "where ")

    def analyze_file(self, tree, path, root, parents):
        issues = []
        dynamic_sql_names = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            value = node.value
            if not isinstance(value, (ast.JoinedStr, ast.BinOp)):
                continue
            query_text = " ".join(
                child.value.lower()
                for child in ast.walk(value)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )
            if any(marker in query_text for marker in self.SQL_MARKERS):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        dynamic_sql_names[target.id] = query_text

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute", "executemany"}
                and node.args
            ):
                continue
            query = node.args[0]
            is_dynamic = isinstance(query, ast.JoinedStr) or (
                isinstance(query, ast.BinOp) and isinstance(query.op, ast.Add)
            ) or isinstance(query, ast.Name) and query.id in dynamic_sql_names
            if not is_dynamic:
                continue
            query_text = dynamic_sql_names.get(query.id, "") if isinstance(query, ast.Name) else " ".join(
                child.value.lower()
                for child in ast.walk(query)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )
            if any(marker in query_text for marker in self.SQL_MARKERS):
                issues.append(self._issue(
                    path, root, node, parents,
                    "SQL query is assembled dynamically and may allow SQL injection.",
                    "Use parameterized query placeholders for all values.",
                    severity="critical",
                ))
        return issues


class PythonWeakHashRule(PythonAstRule):
    name = "WeakHashAlgorithm"
    weak_hashes = {"md5", "sha1"}

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr.lower()
            elif isinstance(node.func, ast.Name):
                name = node.func.id.lower()
            if name in self.weak_hashes or (
                name == "new" and node.args
                and isinstance(node.args[0], ast.Constant)
                and str(node.args[0].value).lower() in self.weak_hashes
            ):
                issues.append(self._issue(
                    path, root, node, parents,
                    f"Weak hash algorithm '{name}' is used.",
                    "Use a modern cryptographic hash; use a password-hashing algorithm for passwords.",
                    severity="high",
                ))
        return issues


class PythonUnclosedResourceRule(PythonAstRule):
    name = "UnclosedResource"

    def analyze_file(self, tree, path, root, parents):
        managed_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    managed_calls.update(
                        child for child in ast.walk(item.context_expr)
                        if isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "open"
                    )

        issues = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
                and node not in managed_calls
            ):
                issues.append(self._issue(
                    path, root, node, parents,
                    "File opened without a context manager may not be closed on every path.",
                    "Use 'with open(...) as file:' so the file is always closed.",
                    severity="medium",
                ))
        return issues


class PythonMutableDefaultRule(PythonAstRule):
    name = "MutableDefaultArgument"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defaults = node.args.defaults + [
                default for default in node.args.kw_defaults if default is not None
            ]
            mutable_call_names = {"list", "dict", "set"}
            if any(
                isinstance(default, (ast.List, ast.Dict, ast.Set))
                or isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id in mutable_call_names
                for default in defaults
            ):
                issues.append(self._issue(
                    path, root, node, parents,
                    f"Function '{node.name}' uses a mutable default argument.",
                    "Use None as the default and create a new mutable value inside the function.",
                    severity="high",
                ))
        return issues


class PythonMissingDocstringRule(PythonAstRule):
    name = "MissingDocstring"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Module):
                continue
            if not isinstance(node, (
                ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef
            )):
                continue
            if node.name.startswith("_") or ast.get_docstring(node):
                continue
            issues.append(self._issue(
                path, root, node, parents,
                f"Public {type(node).__name__.replace('Def', '').lower()} '{node.name}' has no docstring.",
                "Add a concise docstring describing purpose, inputs, and behavior.",
                severity="low",
            ))
        return issues


class PythonMutableClassAttributeRule(PythonAstRule):
    name = "MutableClassAttribute"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        mutable_calls = {"list", "dict", "set"}
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            for node in cls.body:
                value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
                if value is None:
                    continue
                mutable_value = isinstance(value, (ast.List, ast.Dict, ast.Set)) or (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in mutable_calls
                )
                if mutable_value:
                    issues.append(self._issue(
                        path, root, node, parents,
                        f"Class '{cls.name}' has mutable class-level state.",
                        "Initialize mutable state per instance or make shared state intentional and immutable.",
                        severity="medium",
                    ))
        return issues


class PythonListMembershipRule(PythonAstRule):
    name = "InefficientLookup"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            in_loop = False
            current = node
            while current in parents:
                current = parents[current]
                if isinstance(current, (ast.For, ast.AsyncFor, ast.While)):
                    in_loop = True
                    break
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    break
            if not in_loop:
                continue
            if any(
                isinstance(operator, (ast.In, ast.NotIn))
                and isinstance(comparator, ast.List)
                for operator, comparator in zip(node.ops, node.comparators)
            ):
                issues.append(self._issue(
                    path, root, node, parents,
                    "Membership is checked against a list literal inside a loop.",
                    "Create a set once before the loop for repeated membership checks.",
                    severity="low",
                ))
        return issues


class PythonLargeClassRule(PythonAstRule):
    name = "LargeClass"
    threshold = 20

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            methods = [
                node for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if len(methods) > self.threshold:
                issues.append(self._issue(
                    path, root, cls, parents,
                    f"Class '{cls.name}' has {len(methods)} methods (limit {self.threshold}).",
                    "Split independent responsibilities into focused collaborating classes.",
                    severity="high",
                    metric_value=len(methods),
                    metric_threshold=self.threshold,
                ))
        return issues


class PythonGodClassRule(PythonAstRule):
    name = "GodClass"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            methods = [
                node for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            attributes = {
                child.attr
                for method in methods
                for child in ast.walk(method)
                if isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == "self"
            }
            line_count = (cls.end_lineno or cls.lineno) - cls.lineno + 1
            if len(methods) > 20 and len(attributes) > 10 and line_count > 400:
                issues.append(self._issue(
                    path, root, cls, parents,
                    f"Class '{cls.name}' combines {len(methods)} methods, "
                    f"{len(attributes)} instance attributes, and {line_count} lines.",
                    "Split the class by responsibility and move related state and methods together.",
                    severity="critical",
                    metric_value=len(methods),
                    metric_threshold=20,
                ))
        return issues


class PythonFeatureEnvyRule(PythonAstRule):
    name = "FeatureEnvy"

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for method in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            if not any(
                isinstance(ancestor, ast.ClassDef)
                for ancestor in self._ancestors(method, parents)
            ):
                continue
            self_accesses = 0
            other_accesses = 0
            for child in ast.walk(method):
                if not isinstance(child, ast.Attribute) or not isinstance(child.value, ast.Name):
                    continue
                if child.value.id in {"self", "cls"}:
                    self_accesses += 1
                else:
                    other_accesses += 1
            if other_accesses >= 5 and other_accesses > self_accesses * 2:
                issues.append(self._issue(
                    path, root, method, parents,
                    f"Method '{method.name}' accesses other objects substantially more than its own state.",
                    "Consider moving cohesive behavior closer to the data it primarily uses.",
                    severity="medium",
                    metric_value=other_accesses,
                    metric_threshold=self_accesses * 2,
                ))
        return issues

    @staticmethod
    def _ancestors(node, parents):
        while node in parents:
            node = parents[node]
            yield node


class PythonHighCouplingRule(PythonAstRule):
    name = "HighCoupling"
    threshold = 10

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            dependencies = set()
            for child in ast.walk(cls):
                if isinstance(child, ast.Import):
                    dependencies.update(alias.name.split(".")[0] for alias in child.names)
                elif isinstance(child, ast.ImportFrom) and child.module:
                    dependencies.add(child.module.split(".")[0])
                elif isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        dependencies.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        dependencies.add(child.func.attr)
            if len(dependencies) > self.threshold:
                issues.append(self._issue(
                    path, root, cls, parents,
                    f"Class '{cls.name}' references {len(dependencies)} distinct dependencies.",
                    "Reduce direct dependencies and inject focused interfaces where practical.",
                    severity="high",
                    metric_value=len(dependencies),
                    metric_threshold=self.threshold,
                ))
        return issues


class PythonDeepInheritanceRule(PythonAstRule):
    name = "DeepInheritance"
    threshold = 3

    def analyze_file(self, tree, path, root, parents):
        classes = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        depths = {}

        def depth_of(cls, active):
            if cls.name in depths:
                return depths[cls.name]
            if cls.name in active:
                return 0
            local_parents = [
                classes[base.id]
                for base in cls.bases
                if isinstance(base, ast.Name) and base.id in classes
            ]
            depth = max(
                (1 + depth_of(parent, active | {cls.name}) for parent in local_parents),
                default=0,
            )
            depths[cls.name] = depth
            return depth

        issues = []
        for cls in classes.values():
            depth = depth_of(cls, set())
            if depth > self.threshold:
                issues.append(self._issue(
                    path, root, cls, parents,
                    f"Class '{cls.name}' has an inheritance depth of {depth}.",
                    "Prefer composition or flatten the hierarchy where practical.",
                    severity="medium",
                    metric_value=depth,
                    metric_threshold=self.threshold,
                ))
        return issues


class PythonImportCycleRule(PythonAstRule):
    name = "CircularDependency"

    def analyze(self, context):
        root = Path(context.project.project_path)
        files = get_python_ast_files(context)
        module_paths = {}
        for path, _, _ in files:
            relative = path.relative_to(root).with_suffix("")
            parts = list(relative.parts)
            if parts[-1] == "__init__":
                parts.pop()
            module_name = ".".join(parts)
            if module_name:
                module_paths[module_name] = path

        modules = set(module_paths)
        graph = {module: set() for module in modules}
        for path, tree, _ in files:
            relative = path.relative_to(root).with_suffix("")
            parts = list(relative.parts)
            if parts[-1] == "__init__":
                parts.pop()
            current_module = ".".join(parts)
            if not current_module:
                continue
            current_package = current_module if path.stem == "__init__" else current_module.rpartition(".")[0]
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    graph[current_module].update(
                        alias.name for alias in node.names if alias.name in modules
                    )
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        package_parts = current_package.split(".") if current_package else []
                        base_parts = package_parts[:max(0, len(package_parts) - node.level + 1)]
                        imported_parts = base_parts + (node.module.split(".") if node.module else [])
                        imported_module = ".".join(imported_parts)
                    else:
                        imported_module = node.module or ""

                    if imported_module in modules:
                        graph[current_module].add(imported_module)
                    elif imported_module:
                        graph[current_module].update(
                            f"{imported_module}.{alias.name}"
                            for alias in node.names
                            if f"{imported_module}.{alias.name}" in modules
                        )

        visited = set()
        active = []
        active_positions = {}
        reported_cycles = set()
        issues = []

        def visit(module):
            visited.add(module)
            active_positions[module] = len(active)
            active.append(module)
            for dependency in sorted(graph[module]):
                if dependency in active_positions:
                    cycle = active[active_positions[dependency]:]
                    key = frozenset(cycle)
                    if key not in reported_cycles:
                        reported_cycles.add(key)
                        path = module_paths[module]
                        issues.append(DebtIssue(
                            rule=self.name,
                            severity="high",
                            class_name=module,
                            file_path=str(path.relative_to(root)),
                            line_number=1,
                            message=f"Python import cycle detected: {' -> '.join(cycle + [dependency])}.",
                            suggestion="Move shared definitions into a lower-level module to break the cycle.",
                        ))
                elif dependency not in visited:
                    visit(dependency)
            active.pop()
            active_positions.pop(module)

        for module in sorted(graph):
            if module not in visited:
                visit(module)
        return issues

class PythonSourceCredentialRule(PythonAstRule):
    name = "HardcodedCredentials"
    credential_names = {
        "password", "passwd", "pwd", "secret", "secret_key",
        "api_key", "apikey", "token", "access_key",
    }

    def analyze_file(self, tree, path, root, parents):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = target.id if isinstance(target, ast.Name) else (
                    target.attr if isinstance(target, ast.Attribute) else ""
                )
                if name.lower() in self.credential_names and value.value:
                    issues.append(self._issue(
                        path, root, node, parents,
                        f"Credential-like value is hardcoded in '{name}'.",
                        "Load the value from environment-specific configuration or a secret manager.",
                        severity="critical",
                    ))
                    break
        return issues


class PythonDuplicateCodeRule(PythonAstRule):
    name = "DuplicateCode"

    def analyze(self, context):
        root = Path(context.project.project_path)
        duplicates = defaultdict(list)
        for path, tree, parents in get_python_ast_files(context):
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if len(node.body) < 3 or (node.end_lineno or node.lineno) - node.lineno < 3:
                    continue
                body = ast.Module(body=node.body, type_ignores=[])
                fingerprint = ast.dump(body, annotate_fields=False, include_attributes=False)
                duplicates[fingerprint].append((node, path, parents))

        issues = []
        for matches in duplicates.values():
            if len(matches) < 2:
                continue
            for node, path, parents in matches:
                issues.append(self._issue(
                    path, root, node, parents,
                    f"Function '{node.name}' duplicates a function body elsewhere in the project.",
                    "Extract the common behavior into one shared, reusable function.",
                    severity="high",
                    metric_value=len(matches),
                    metric_threshold=1,
                ))
        return issues


PYTHON_AST_RULES = [
    PythonTooManyParametersRule(),
    PythonEmptyExceptRule(),
    PythonBroadExceptRule(),
    PythonUnsafeEvalRule(),
    PythonSqlInjectionRule(),
    PythonWeakHashRule(),
    PythonUnclosedResourceRule(),
    PythonMutableDefaultRule(),
    PythonMissingDocstringRule(),
    PythonMutableClassAttributeRule(),
    PythonListMembershipRule(),
    PythonLargeClassRule(),
    PythonGodClassRule(),
    PythonFeatureEnvyRule(),
    PythonHighCouplingRule(),
    PythonDeepInheritanceRule(),
    PythonImportCycleRule(),
    PythonSourceCredentialRule(),
    PythonDuplicateCodeRule(),
]
