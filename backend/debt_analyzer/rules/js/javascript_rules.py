import re
from pathlib import Path

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.web_common import (
    debt_issue,
    line_number,
    matching_brace,
    mask_js,
    read_source,
    source_files,
)


JS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs"}
FUNCTION_PATTERNS = (
    re.compile(r"\bfunction\s*([\w$]*)\s*\([^)]*\)\s*\{"),
    re.compile(
        r"\b(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?"
        r"(?:\([^)]*\)|[\w$]+)\s*=>\s*\{"
    ),
)
CALLBACK_PATTERNS = (
    re.compile(r"\bfunction\s*[\w$]*\s*\([^)]*\)\s*\{"),
    re.compile(r"(?:\([^)]*\)|[\w$]+)\s*=>\s*\{"),
)


class JavaScriptRules(BaseRule):
    name = "JavaScriptWebRules"

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        for path in source_files(context, JS_EXTENSIONS):
            source = read_source(path)
            masked = mask_js(source)
            lines = source.splitlines()

            for pattern, rule, message, suggestion in (
                (re.compile(r"\bvar\s+[\w$]+"), "VarInsteadOfLetConst",
                 "'var' is function-scoped and can introduce hoisting bugs.",
                 "Use const by default and let only when reassignment is needed."),
                (re.compile(r"(?<![=!])==(?![=])|(?<![!])!=(?!=)"),
                 "LooseEquality", "Loose equality can introduce coercion bugs.",
                 "Use === or !== unless coercion is intentional."),
                (re.compile(r"\b(?:eval\s*\(|new\s+Function\s*\()"),
                 "UnsafeEval", "Dynamic code execution can enable code injection.",
                 "Replace eval/Function construction with explicit validated logic."),
                (re.compile(r"\.\s*innerHTML\s*="), "UnsafeInnerHTML",
                 "innerHTML assignment can expose the page to cross-site scripting.",
                 "Use textContent for plain text, or sanitize trusted HTML."),
            ):
                for match in pattern.finditer(masked):
                    line = line_number(source, match.start())
                    issues.append(debt_issue(
                        rule, "critical" if rule == "UnsafeEval" else
                        ("high" if rule == "UnsafeInnerHTML" else "medium"),
                        path, root, line, message, suggestion,
                    ))

            console_matches = list(re.finditer(
                r"\bconsole\.(?:log|debug|info|warn|error)\s*\(", masked
            ))
            if len(console_matches) > 3:
                issues.append(debt_issue(
                    "ConsoleLogInProduction", "low", path, root,
                    line_number(source, console_matches[0].start()),
                    f"{len(console_matches)} console statements remain in application code.",
                    "Remove temporary logs or route diagnostics through the project logger.",
                    metric_value=len(console_matches),
                    metric_threshold=3,
                ))

            for match in re.finditer(r"(?m)^\s*([A-Za-z_$][\w$]*)\s*=(?!=|>)", masked):
                prefix = masked[:match.start()]
                depth = prefix.count("{") - prefix.count("}")
                preceding = prefix.rstrip().splitlines()[-1:] or [""]
                if depth <= 0 and not re.search(
                    r"\b(?:let|const|var|function|class|import|export)\s+$",
                    preceding[0],
                ):
                    issues.append(debt_issue(
                        "GlobalVariablePollution", "medium", path, root,
                        line_number(source, match.start()),
                        f"'{match.group(1)}' is assigned without a declaration at module scope.",
                        "Declare the variable or encapsulate the state in a module/function.",
                    ))

            for pattern in FUNCTION_PATTERNS:
                for match in pattern.finditer(masked):
                    opening = masked.find("{", match.start(), match.end())
                    closing = matching_brace(source, masked, opening)
                    length = source.count("\n", opening, closing) + 1
                    if length > 50:
                        name = match.group(1) or "<anonymous>"
                        issues.append(debt_issue(
                            "LongFunction", "high", path, root,
                            line_number(source, match.start()),
                            f"Function '{name}' spans {length} lines.",
                            "Extract focused helper functions and reduce each function's responsibilities.",
                            metric_value=length,
                            metric_threshold=50,
                        ))

            callback_matches = sorted(
                (
                    match
                    for pattern in CALLBACK_PATTERNS
                    for match in pattern.finditer(masked)
                ),
                key=lambda match: match.start(),
            )
            active_callback_ends = []
            for match in callback_matches:
                while active_callback_ends and match.start() > active_callback_ends[-1]:
                    active_callback_ends.pop()
                opening = masked.find("{", match.start(), match.end())
                closing = matching_brace(source, masked, opening)
                active_callback_ends.append(closing)
                if len(active_callback_ends) > 3:
                    issues.append(debt_issue(
                        "CallbackHell", "high", path, root,
                        line_number(source, match.start()),
                        "More than three nested callback/function levels were detected.",
                        "Extract callbacks or use promises and async/await.",
                        metric_value=len(active_callback_ends),
                        metric_threshold=3,
                    ))
                    break
        return issues
