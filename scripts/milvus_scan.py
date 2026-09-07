"""Milvus 候选镜像只读扫描验收；不构建、不启动服务、不签发 Compose 准入。

必须覆盖 Ubuntu、主程序和解析库，并绑定归档与报告的 config ID。
通过仅表示本次报告满足漏洞门禁，不替代来源、时效、ABI 和运行契约验证。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from storage_image import ImageGateError, _json, archive_identity

REQUIRED_GO_TARGETS = frozenset({"milvus/bin/milvus", "milvus/lib/libmilvus-planparser.so"})
SEVERITIES = frozenset({"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"})


def scan_findings(report: dict) -> dict[str, int]:
    """固定 Milvus 覆盖范围；缺失、重复或畸形结果均拒绝，保留低等级统计。"""
    if (
        not isinstance(report, dict)
        or report.get("SchemaVersion") != 2
        or report.get("ArtifactType") != "container_image"
        or not isinstance(report.get("Results"), list)
        or not report["Results"]
    ):
        raise ImageGateError("Milvus vulnerability report is incomplete")
    covered_go = set()
    covered_os = False
    seen = set()
    counts = dict.fromkeys(sorted(SEVERITIES), 0)
    for target in report["Results"]:
        if not isinstance(target, dict):
            raise ImageGateError("Invalid Milvus scan target")
        name, category, kind = (target.get(key) for key in ("Target", "Class", "Type"))
        if not all(isinstance(value, str) and value for value in (name, category, kind)):
            raise ImageGateError("Invalid Milvus scan target identity")
        identity = (name, category, kind)
        if identity in seen:
            raise ImageGateError("Duplicate Milvus scan target")
        seen.add(identity)
        if category == "os-pkgs" and kind == "ubuntu":
            covered_os = True
        if category == "lang-pkgs" and kind == "gobinary":
            covered_go.add(name)
        findings = target.get("Vulnerabilities")
        if findings is None:
            findings = []  # Trivy omits or emits null for a clean target.
        if not isinstance(findings, list):
            raise ImageGateError("Invalid Milvus vulnerability list")
        for finding in findings:
            if not isinstance(finding, dict):
                raise ImageGateError("Invalid Milvus vulnerability entry")
            severity = finding.get("Severity", "UNKNOWN")
            if not isinstance(severity, str) or severity not in SEVERITIES:
                raise ImageGateError("Invalid Milvus vulnerability severity")
            counts[severity] += 1
    if not covered_os or not REQUIRED_GO_TARGETS <= covered_go:
        raise ImageGateError("Milvus scan must cover Ubuntu and both Go artifacts")
    if counts["HIGH"] or counts["CRITICAL"]:
        raise ImageGateError("Milvus candidate still has HIGH/CRITICAL findings")
    return counts


def verify_report(archive: Path, report_path: Path, image_id: str) -> dict:
    """校验归档内容链及报告对象；从不把候选 tag 或文件存在当作通过。"""
    identity = archive_identity(archive, image_id)
    data = report_path.read_bytes()
    report = _json(data)
    if (
        not isinstance(report, dict)
        or not isinstance(report.get("Metadata"), dict)
        or report["Metadata"].get("ImageID") != identity["config_id"]
    ):
        raise ImageGateError("Milvus report does not match archive-bound config ID")
    counts = scan_findings(report)
    return {
        "scope": "candidate_archive_scan_only",
        "image_id": image_id,
        **identity,
        "report_sha256": hashlib.sha256(data).hexdigest(),
        "findings": counts,
        "compose_admitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    try:
        result = verify_report(args.archive, args.report, args.image_id)
    except (ImageGateError, OSError, ValueError, TypeError) as exc:
        detail = str(exc) if isinstance(exc, ImageGateError) else type(exc).__name__
        print(f"milvus-scan FAILED: {detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
