"""验证 M00.2 定义的项目骨架是否完整。"""

from __future__ import annotations

from pathlib import Path


REQUIRED_DIRECTORIES = (
    "apps/web-customer",
    "apps/web-agent",
    "apps/web-admin",
    "apps/api-gateway",
    "apps/commerce-service",
    "apps/conversation-service",
    "apps/orchestration-service",
    "apps/knowledge-service",
    "apps/ticket-service",
    "apps/worker",
    "packages/contracts",
    "packages/domain",
    "packages/observability",
    "packages/testing",
    "deploy/compose",
    "deploy/nginx",
    "deploy/mysql",
    "deploy/scripts",
    "docs/api",
    "docs/architecture",
    "docs/baseline",
    "docs/decisions",
    "docs/operations",
    "docs/progress",
    "docs/testing",
    "tests/contract",
    "tests/integration",
    "tests/e2e",
    "tests/performance",
    "tests/security",
)

REQUIRED_FILES = (
    ".editorconfig",
    ".env.example",
    ".github/pull_request_template.md",
    ".gitattributes",
    ".gitignore",
    ".node-version",
    ".python-version",
    "environment.yml",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "README.md",
    "SECURITY.md",
    "VERSION",
    "docs/decisions/ADR-0000-template.md",
    "docs/decisions/ADR-0001-modular-monorepo-and-kf-boundary.md",
    "docs/architecture/module-boundaries.md",
    "docs/architecture/project-layout.md",
    "docs/baseline/reference-assets.md",
    "docs/operations/versioning-and-release.md",
    "docs/progress/task-ledger.md",
    "docs/testing/definition-of-done.md",
    "scripts/verify_governance.py",
)


def find_missing(root: Path) -> list[str]:
    """返回缺失的目录或文件，便于本地与 CI 使用同一门禁。"""

    missing = [f"directory:{item}" for item in REQUIRED_DIRECTORIES if not (root / item).is_dir()]
    missing.extend(f"file:{item}" for item in REQUIRED_FILES if not (root / item).is_file())
    return missing


def main() -> int:
    """执行只读结构检查；此脚本不创建、删除或修改项目文件。"""

    root = Path(__file__).resolve().parents[1]
    missing = find_missing(root)
    if missing:
        print("structure-check: FAILED")
        for item in missing:
            print(f"- {item}")
        return 1

    print(f"structure-check: OK ({len(REQUIRED_DIRECTORIES)} directories, {len(REQUIRED_FILES)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
