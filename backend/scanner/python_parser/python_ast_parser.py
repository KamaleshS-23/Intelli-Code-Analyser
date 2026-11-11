import ast
from pathlib import Path

from scanner.models.project_model import ClassModel, FieldModel, MethodModel, ParameterModel
from scanner.utils.file_utils import read_source


def _annotation_to_type(annotation):
    if annotation is None:
        return "unknown"
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return f"{_annotation_to_type(annotation.value)}.{annotation.attr}"
    if isinstance(annotation, ast.Subscript):
        return _annotation_to_type(annotation.value)
    if isinstance(annotation, ast.Constant):
        return str(annotation.value)
    return ast.unparse(annotation)


def _extract_assign_target_name(target):
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _method_cyclomatic_complexity(node):
    count = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Assert, ast.IfExp, ast.ExceptHandler)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.Compare):
            count += len(child.ops)
        elif isinstance(child, ast.Try):
            count += len(child.handlers)
    return count


def _method_max_nesting_depth(node):
    def walk(child, current_depth):
        max_depth = current_depth
        for sub in ast.iter_child_nodes(child):
            if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.IfExp, ast.BoolOp, ast.Compare, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                max_depth = max(max_depth, walk(sub, current_depth + 1))
            else:
                max_depth = max(max_depth, walk(sub, current_depth))
        return max_depth
    return walk(node, 0)


def _collect_magic_numbers(node):
    magic_numbers = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)) and not isinstance(child.value, bool):
            if child.value == 0 and isinstance(node, ast.Module):
                continue
            magic_numbers.append({"line": child.lineno, "value": child.value})
    return magic_numbers


def _collect_unused_local_vars(node):
    assigned_names = set()
    used_names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                name = _extract_assign_target_name(target)
                if name:
                    assigned_names.add(name)
        elif isinstance(child, ast.AnnAssign):
            name = _extract_assign_target_name(child.target)
            if name:
                assigned_names.add(name)
        elif isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Store):
                assigned_names.add(child.id)
            elif isinstance(child.ctx, ast.Load):
                used_names.add(child.id)
    unused = sorted(assigned_names - used_names - {"self"})
    return [{"name": name, "line": node.lineno} for name in unused]


def _collect_hardcoded_credentials(node):
    matches = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            text = child.value.lower()
            if any(token in text for token in ("password", "secret", "token", "apikey", "api_key")):
                matches.append({"line": child.lineno, "value": child.value})
    return matches


def _collect_string_concat_in_loop(node):
    for child in ast.walk(node):
        if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
            for sub in ast.walk(child):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Add):
                    return sub.lineno
    return 0


def _collect_exception_handling_lines(node):
    for child in ast.walk(node):
        if isinstance(child, ast.ExceptHandler):
            if child.body:
                continue
            return child.lineno
    return 0


def _parse_method(node, class_name, module_path):
    params = []
    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
        params.append(
            ParameterModel(
                name=arg.arg,
                datatype=_annotation_to_type(arg.annotation) if arg.annotation else "object",
            )
        )
    if node.args.vararg:
        params.append(ParameterModel(name=node.args.vararg.arg, datatype="*args"))
    if node.args.kwarg:
        params.append(ParameterModel(name=node.args.kwarg.arg, datatype="**kwargs"))

    method = MethodModel(
        name=node.name,
        return_type=_annotation_to_type(node.returns) if node.returns else "None",
        parameters=params,
        modifiers=["public" if node.name != "__init__" else "public"],
        line_number=node.lineno,
        line_count=max(node.end_lineno - node.lineno + 1, 1),
        cyclomatic_complexity=_method_cyclomatic_complexity(node),
        max_nesting_depth=_method_max_nesting_depth(node),
        magic_numbers=_collect_magic_numbers(node),
        unused_local_vars=_collect_unused_local_vars(node),
        string_concat_in_loop_line=_collect_string_concat_in_loop(node),
        hardcoded_credential_lines=_collect_hardcoded_credentials(node),
    )
    method.empty_catch_lines = [line for line in [ _collect_exception_handling_lines(node) ] if line]
    return method


def _parse_class(node, file_path, project_root):
    package = ""
    if project_root is not None:
        rel_path = Path(file_path).resolve().relative_to(Path(project_root).resolve())
        if len(rel_path.parts) > 1:
            package = ".".join(rel_path.parts[:-1])
    parent_names = [
        _annotation_to_type(base)
        for base in node.bases
        if not isinstance(base, ast.Call)
    ]
    class_model = ClassModel(
        name=node.name,
        package=package,
        file_path=str(file_path),
        class_type="class",
        modifiers=["public"],
        imports=[],
        fields=[],
        methods=[],
        extends=", ".join(parent_names) if parent_names else "",
        implements=[],
        annotations=[]
    )

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name != "__init__":
            class_model.methods.append(_parse_method(item, node.name, package))
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                field_name = _extract_assign_target_name(target)
                if field_name:
                    class_model.fields.append(FieldModel(name=field_name, datatype="unknown", line_number=item.lineno))
        elif isinstance(item, ast.AnnAssign):
            field_name = _extract_assign_target_name(item.target)
            if field_name:
                class_model.fields.append(FieldModel(name=field_name, datatype=_annotation_to_type(item.annotation) if item.annotation else "unknown", line_number=item.lineno))

    init_fn = next((item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__"), None)
    if init_fn:
        class_model.methods.insert(0, _parse_method(init_fn, node.name, package))

    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        class_model.line_count = max(1, sum(1 for _ in fh))
    return class_model


def parse_python_file(file_path, project_root=None):
    try:
        source = read_source(file_path)
        tree = ast.parse(source)
    except Exception as exc:
        return [], str(exc)

    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(_parse_class(node, file_path, project_root or str(Path(file_path).resolve().parent.parent)))

    return classes, None
