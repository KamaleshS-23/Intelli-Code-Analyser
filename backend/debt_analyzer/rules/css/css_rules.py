import re
from collections import Counter
from pathlib import Path

from debt_analyzer.rules.base_rule import BaseRule
from debt_analyzer.rules.web_common import (
    css_rule_blocks,
    debt_issue,
    read_source,
    source_files,
)


CSS_EXTENSIONS = {".css"}
COLOR_PATTERN = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\s*\(",
    re.I,
)


class CssRules(BaseRule):
    name = "CssWebRules"

    def analyze(self, context):
        root = Path(context.project.project_path)
        issues = []
        for path in source_files(context, CSS_EXTENSIONS):
            source = read_source(path)
            clean = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
            important_count = len(re.findall(r"!important\b", clean, re.I))
            if important_count > 5:
                issues.append(debt_issue(
                    "ExcessiveImportant", "medium", path, root, 1,
                    f"!important is used {important_count} times.",
                    "Correct selector specificity or component ownership instead.",
                    metric_value=important_count,
                    metric_threshold=5,
                ))

            for line, text in enumerate(clean.splitlines(), start=1):
                if COLOR_PATTERN.search(text):
                    issues.append(debt_issue(
                        "HardcodedColor", "low", path, root, line,
                        "Hardcoded color value found in CSS.",
                        "Use a CSS custom property for shared colors.",
                    ))

            selectors = Counter()
            for selector, _, line in css_rule_blocks(source):
                normalized = re.sub(r"\s+", " ", selector).strip()
                selectors[normalized] += 1
                if len(re.findall(r"\s+|[>+~]", normalized)) >= 4:
                    issues.append(debt_issue(
                        "DeepSelectorNesting", "low", path, root, line,
                        f"Selector has deeply nested specificity: {normalized[:70]}.",
                        "Flatten the selector and prefer component or utility classes.",
                        metric_value=len(re.findall(r"\s+|[>+~]", normalized)),
                        metric_threshold=4,
                    ))
            for selector, count in selectors.items():
                if count > 1:
                    line = next(
                        rule_line for rule, _, rule_line in css_rule_blocks(source)
                        if re.sub(r"\s+", " ", rule).strip() == selector
                    )
                    issues.append(debt_issue(
                        "DuplicateSelector", "medium", path, root, line,
                        f"Selector '{selector}' is declared {count} times.",
                        "Merge the selector declarations or remove redundant rules.",
                        metric_value=count,
                        metric_threshold=1,
                    ))
        return issues
