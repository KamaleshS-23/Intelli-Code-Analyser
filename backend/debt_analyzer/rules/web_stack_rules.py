from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.css.css_rules import CssRules
from debt_analyzer.rules.html.html_rules import HtmlRules
from debt_analyzer.rules.js.javascript_rules import JavaScriptRules
from debt_analyzer.rules.web_cross_rules import WebCrossLanguageRules
from debt_analyzer.web_metrics import analyze_web_metrics


class WebStackAnalysisRule(BaseRule):
    name = "WebStackAnalysis"

    def analyze(self, context):
        issues = []
        for rule in (
            HtmlRules(),
            CssRules(),
            JavaScriptRules(),
            WebCrossLanguageRules(),
        ):
            issues.extend(rule.analyze(context))
        context.project.statistics["web_analysis"] = analyze_web_metrics(context, issues)
        return issues
