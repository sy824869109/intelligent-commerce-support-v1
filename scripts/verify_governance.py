"""验证 M00.3 定义的治理文件和最小内容契约。"""

from __future__ import annotations

import re
from pathlib import Path


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
VALID_ADR_STATUSES = {"Proposed", "Accepted", "Deprecated", "Rejected"}
REQUIRED_ADR_SECTIONS = (
    "## 背景",
    "## 决策驱动因素",
    "## 决策",
    "## 备选方案",
    "## 结果与影响",
    "## 安全与数据影响",
    "## 运维与回滚",
    "## 验证方式",
)


def read_text(path: Path) -> str:
    """统一使用 UTF-8 读取治理文件，编码错误应直接阻断提交。"""

    return path.read_text(encoding="utf-8")


def validate_version(root: Path, errors: list[str]) -> str:
    """校验产品版本，并返回供 CHANGELOG 交叉检查的版本号。"""

    version = read_text(root / "VERSION").strip()
    if not SEMVER_PATTERN.fullmatch(version):
        errors.append(f"VERSION is not valid semantic versioning: {version!r}")
    return version


def validate_changelog(root: Path, version: str, errors: list[str]) -> None:
    """确保当前版本已经进入变更日志且保留 Unreleased 区域。"""

    changelog = read_text(root / "CHANGELOG.md")
    if "## [Unreleased]" not in changelog:
        errors.append("CHANGELOG.md is missing [Unreleased]")
    if f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md is missing current version [{version}]")


def validate_adrs(root: Path, errors: list[str]) -> None:
    """校验正式 ADR 的状态元数据和长期维护所需章节。"""

    decision_dir = root / "docs" / "decisions"
    adrs = sorted(decision_dir.glob("ADR-[0-9][0-9][0-9][0-9]-*.md"))
    formal_adrs = [path for path in adrs if path.name != "ADR-0000-template.md"]
    if not formal_adrs:
        errors.append("No formal ADR found")
        return

    for path in formal_adrs:
        content = read_text(path)
        status_match = re.search(r"^- 状态[：:]\s*(.+)$", content, re.MULTILINE)
        if status_match is None:
            errors.append(f"{path.name} is missing status metadata")
        else:
            status = status_match.group(1).strip()
            is_superseded = status.startswith("Superseded by ADR-")
            if status not in VALID_ADR_STATUSES and not is_superseded:
                errors.append(f"{path.name} has unsupported status: {status}")

        for section in REQUIRED_ADR_SECTIONS:
            if section not in content:
                errors.append(f"{path.name} is missing section: {section}")


def validate_delivery_rules(root: Path, errors: list[str]) -> None:
    """检查 PR 与完成定义包含不可省略的交付门禁。"""

    pull_request = read_text(root / ".github" / "pull_request_template.md")
    done = read_text(root / "docs" / "testing" / "definition-of-done.md")
    required_pr_terms = ("验证证据", "安全", "回滚", "KF RAG")
    for term in required_pr_terms:
        if term not in pull_request:
            errors.append(f"Pull request template is missing term: {term}")
    if "推送 GitHub" not in done:
        errors.append("Definition of Done does not require a GitHub push")


def main() -> int:
    """执行治理检查；只报告问题，不修改任何文件。"""

    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    version = validate_version(root, errors)
    validate_changelog(root, version, errors)
    validate_adrs(root, errors)
    validate_delivery_rules(root, errors)

    if errors:
        print("governance-check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("governance-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
