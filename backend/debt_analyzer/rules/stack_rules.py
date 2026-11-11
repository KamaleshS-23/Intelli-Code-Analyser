import re
from pathlib import Path

from debt_analyzer.models import DebtIssue
from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.web_stack_rules import WebStackAnalysisRule
from scanner.config import IGNORE_DIRS


JS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs"}
WEB_EXTENSIONS = JS_EXTENSIONS | {".html", ".htm", ".css"}
DJANGO_EXTENSIONS = WEB_EXTENSIONS | {".py"}


class SourceFileRule(BaseRule):
    extensions = WEB_EXTENSIONS

    def files(self, context):
        root = Path(context.project.project_path)
        if not root.exists():
            return
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.extensions:
                if not any(part in IGNORE_DIRS for part in path.parts):
                    yield path

    def issue(self, path, root, line_number, message, suggestion, severity="medium"):
        relative_path = str(path.relative_to(root))
        return DebtIssue(
            rule=self.name,
            severity=severity,
            class_name=relative_path,
            file_path=relative_path,
            line_number=line_number,
            message=message,
            suggestion=suggestion,
        )


class TodoCommentRule(SourceFileRule):
    name = "UnresolvedTodo"

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\b(?:TODO|FIXME|HACK)\b", re.IGNORECASE)
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Unresolved TODO/FIXME/HACK comment found.",
                        "Resolve the task or create a tracked issue and remove the marker.",
                        severity="low",
                    ))
        return issues


class JavaScriptConsoleRule(SourceFileRule):
    name = "ConsoleStatement"
    extensions = JS_EXTENSIONS

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\bconsole\.(?:log|debug|info)\s*\(")
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Debug console statement found in application code.",
                        "Use the project's logger or remove the debug statement.",
                        severity="low",
                    ))
        return issues


class JavaScriptHardcodedSecretRule(SourceFileRule):
    name = "HardcodedCredentials"
    extensions = JS_EXTENSIONS

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(
            r"""(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*["'][^"']{4,}["']""",
            re.IGNORECASE,
        )
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "A credential-like value appears to be hardcoded.",
                        "Load secrets from environment variables or a secrets manager.",
                        severity="critical",
                    ))
        return issues


class HtmlInlineStyleRule(SourceFileRule):
    name = "InlineHtmlStyle"
    extensions = {".html", ".htm"}

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\sstyle\s*=", re.IGNORECASE)
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Inline styling couples presentation to HTML markup.",
                        "Move reusable styling into a CSS class or stylesheet.",
                        severity="low",
                    ))
        return issues


class CssImportantRule(SourceFileRule):
    name = "CssImportantOverride"
    extensions = {".css"}

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"!important\b", re.IGNORECASE)
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "CSS !important may be masking selector specificity or cascade problems.",
                        "Review selector specificity and stylesheet order before overriding the cascade.",
                        severity="low",
                    ))
        return issues


class DjangoDebugEnabledRule(SourceFileRule):
    name = "DjangoDebugEnabled"
    extensions = {".py"}

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"^\s*DEBUG\s*=\s*True\b")
        for path in self.files(context):
            if path.name.lower() != "settings.py":
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Django DEBUG is enabled in settings.py.",
                        "Set DEBUG from environment-specific configuration and disable it in production.",
                        severity="high",
                    ))
        return issues


class DjangoHardcodedSecretRule(SourceFileRule):
    name = "DjangoHardcodedSecret"
    extensions = {".py"}

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"^\s*SECRET_KEY\s*=\s*(['\"])(.{8,}?)\1\s*(?:#.*)?$")
        for path in self.files(context):
            if path.name.lower() != "settings.py":
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "A literal Django SECRET_KEY is stored in settings.py.",
                        "Load SECRET_KEY from an environment variable or secret manager.",
                        severity="critical",
                    ))
        return issues


class DjangoRawSqlRule(SourceFileRule):
    name = "DjangoRawSql"
    extensions = {".py"}

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\.(?:raw|extra)\s*\(|\bcursor\.execute\s*\(")
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Raw SQL access bypasses some Django ORM safeguards.",
                        "Prefer ORM queries; parameterize values if raw SQL is necessary.",
                        severity="medium",
                    ))
        return issues


class NodeSynchronousIoRule(SourceFileRule):
    name = "NodeSynchronousIo"
    extensions = JS_EXTENSIONS

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\b(?:readFileSync|writeFileSync|appendFileSync|existsSync|readdirSync)\s*\(")
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Synchronous filesystem I/O can block the Node.js event loop.",
                        "Use the asynchronous fs API where blocking is not required.",
                        severity="medium",
                    ))
        return issues


class NodeEvalRule(SourceFileRule):
    name = "DynamicCodeExecution"
    extensions = JS_EXTENSIONS

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        pattern = re.compile(r"\beval\s*\(|new\s+Function\s*\(")
        for path in self.files(context):
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    issues.append(self.issue(
                        path, root, line_number,
                        "Dynamic code execution makes behavior difficult to analyze and maintain.",
                        "Replace eval/Function construction with explicit, validated control flow.",
                        severity="high",
                    ))
        return issues


def get_web_stack_rules(stack):
    rules = [
        TodoCommentRule(),
        JavaScriptHardcodedSecretRule(),
        WebStackAnalysisRule(),
    ]
    if stack == "nodejs":
        rules.append(NodeSynchronousIoRule())
    return rules
