"""Read-only consistency checks for the four V1 implementation standards.

This checks documentation structure, not business behavior or runtime contracts.
It must never mark an acceptance case as passed or change implementation status.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


STANDARD_DIR = Path("docs/implementation-standards/v1")
STANDARD_FILES = {
    "C": "01_会话状态_打断与人工接管.md",
    "B": "02_混合业务决策_用户确认.md",
    "E": "03_接口事件_幂等与失败恢复.md",
    "A": "04_业务RAG安全与灾备_验收矩阵.md",
}
RULE_COUNTS = {"C": 11, "B": 12, "E": 11, "A": 14}
CASE_COUNTS = {"C": 13, "B": 18, "R": 14, "E": 13, "S": 12, "U": 7, "O": 10, "L": 6}
RULE_DEFINITION = re.compile(r"^## ([CBEA]-\d{2})\s", re.MULTILINE)
RULE_REFERENCE = re.compile(r"\b([CBEA]-\d{2})\b")
CASE_ROW = re.compile(r"^\| (AT-([CBRESUOL])(\d{2})) \| (P[012]) \|", re.MULTILINE)
JSON_BLOCK = re.compile(r"^```json\s*\n(.*?)\n```", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")


def check_markdown(path: Path, content: str, errors: list[str]) -> None:
    """Check fenced-block balance and table shape without executing examples."""
    in_fence = False
    table_width: int | None = None
    for line_number, line in enumerate(content.splitlines(), start=1):
        if line.startswith("```"):
            in_fence = not in_fence
            table_width = None
            continue
        if in_fence:
            continue
        if line.startswith("|") and line.endswith("|"):
            width = len(re.split(r"(?<!\\)\|", line)) - 2
            if table_width is not None and table_width != width:
                errors.append(f"{path}:{line_number}: inconsistent table column count")
            table_width = width
        else:
            table_width = None
    if in_fence:
        errors.append(f"{path}: unclosed fenced block")


def validate_documents(root: Path, contents: dict[Path, str]) -> tuple[list[str], dict[str, int]]:
    """Accept in-memory contents so negative cases can be checked without edits."""
    errors: list[str] = []
    definitions: list[str] = []
    referenced: set[str] = set()
    json_count = 0
    for relative, content in contents.items():
        if not content.strip():
            errors.append(f"{relative}: empty document")
        check_markdown(relative, content, errors)
        definitions.extend(RULE_DEFINITION.findall(content))
        referenced.update(RULE_REFERENCE.findall(content))
        for block in JSON_BLOCK.findall(content):
            json_count += 1
            try:
                example = json.loads(block)
                if not isinstance(example, dict):
                    errors.append(f"{relative}: JSON example must be an object")
            except json.JSONDecodeError as exc:
                errors.append(f"{relative}: invalid JSON example: {exc.msg}")
        for target in LINK.findall(content):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target_path = unquote(target.split("#", 1)[0])
            resolved = (root / relative.parent / target_path).resolve()
            if not resolved.is_relative_to(root.resolve()):
                errors.append(f"{relative}: local link leaves repository: {target}")
            elif not resolved.exists():
                errors.append(f"{relative}: missing local link: {target}")
    for rule, count in Counter(definitions).items():
        if count > 1:
            errors.append(f"Duplicate rule definition: {rule}")
    for rule in sorted(referenced - set(definitions)):
        errors.append(f"Undefined rule reference: {rule}")
    for prefix, count in RULE_COUNTS.items():
        expected = {f"{prefix}-{number:02}" for number in range(1, count + 1)}
        actual = {rule for rule in definitions if rule.startswith(prefix + "-")}
        if actual != expected:
            errors.append(f"Rule sequence mismatch for {prefix}: expected {count}")
    matrix_path = STANDARD_DIR / STANDARD_FILES["A"]
    matrix = contents.get(matrix_path, "")
    cases = CASE_ROW.findall(matrix)
    case_ids = [case[0] for case in cases]
    for case_id, count in Counter(case_ids).items():
        if count > 1:
            errors.append(f"Duplicate acceptance case: {case_id}")
    for prefix, count in CASE_COUNTS.items():
        expected = {f"AT-{prefix}{number:02}" for number in range(1, count + 1)}
        actual = {case_id for case_id in case_ids if case_id.startswith("AT-" + prefix)}
        if actual != expected:
            errors.append(f"Acceptance sequence mismatch for {prefix}: expected {count}")
    for line in matrix.splitlines():
        if CASE_ROW.match(line) and not RULE_REFERENCE.search(line):
            errors.append(f"Acceptance case lacks rule references: {line.split('|')[1].strip()}")
    if "NOT_RUN" not in matrix or "已执行数 0、通过数 0" not in matrix:
        errors.append("Matrix must distinguish this unexecuted baseline from a runtime report")
    if json_count < 5:
        errors.append("Expected at least five valid JSON examples across the standards")
    scope = contents.get(STANDARD_DIR / "业务范围与验收映射.md", "")
    scope_ids = re.findall(r"^\| (BS-\d{2}) ", scope, re.MULTILINE)
    if sorted(scope_ids) != [f"BS-{number:02}" for number in range(1, 15)]:
        errors.append("Business scope must map each of BS-01 through BS-14 exactly once")
    for case_id in set(re.findall(r"\bAT-[CBRESUOL]\d{2}\b", "\n".join(contents.values()))):
        if case_id not in case_ids:
            errors.append(f"Undefined acceptance reference: {case_id}")
    business = contents.get(STANDARD_DIR / STANDARD_FILES["B"], "")
    scenarios = re.findall(r"^\| (SCN-\d{2}) \|", business, re.MULTILINE)
    if sorted(scenarios) != [f"SCN-{number:02}" for number in range(1, 23)]:
        errors.append("Business scenario sequence must be SCN-01 through SCN-22")
    return errors, {
        "rules": len(definitions),
        "acceptance_cases": len(cases),
        "json_examples": json_count,
    }


def load_documents(root: Path) -> dict[Path, str]:
    """Load only this documentation set and explicitly maintained indexes."""
    paths = [STANDARD_DIR / "README.md", STANDARD_DIR / "业务范围与验收映射.md"]
    paths.extend(STANDARD_DIR / filename for filename in STANDARD_FILES.values())
    paths.extend(
        Path(name)
        for name in (
            "docs/README.md",
            "docs/api/README.md",
            "docs/architecture/README.md",
            "docs/testing/README.md",
            "tests/README.md",
            "packages/contracts/README.md",
        )
    )
    return {path: (root / path).read_text(encoding="utf-8") for path in paths}


def main() -> int:
    """Report structural evidence without creating files or mutating tests."""
    root = Path(__file__).resolve().parents[1]
    try:
        errors, counts = validate_documents(root, load_documents(root))
    except (OSError, UnicodeError) as exc:
        print(f"implementation-standards-check: FAILED ({exc})")
        return 1
    if errors:
        print("implementation-standards-check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("implementation-standards-check: OK " + json.dumps(counts, ensure_ascii=True))
    print("Documentation validation only; runtime acceptance cases remain NOT_RUN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
