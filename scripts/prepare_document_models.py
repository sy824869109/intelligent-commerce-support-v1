"""Prefetch bounded Docling PDF/table/Chinese OCR assets into the project, with hashes."""

from __future__ import annotations

from http.client import IncompleteRead
import json
from pathlib import Path
import shutil
import time
import urllib.request

from prepare_local_models import digest, git_blob, safe_target

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "_local_artifacts/models/docling"
LOCK = ROOT / "deploy/dev-environment/document-models.lock.json"
REPOS = {
    "docling-project/docling-layout-heron": (
        "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
        ["README.md", "config.json", "preprocessor_config.json", "model.safetensors"],
    ),
    "docling-project/docling-models": (
        "fc0f2d45e2218ea24bce5045f58a389aed16dc23",
        [
            "README.md",
            "model_artifacts/tableformer/accurate/tm_config.json",
            "model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
        ],
    ),
}
OCR_FILES = [
    "torch/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.pth",
    "torch/PP-OCRv4/cls/ch_ptocr_mobile_v2.0_cls_mobile.pth",
    "torch/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile.pth",
    "paddle/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile/ppocr_keys_v1.txt",
    "resources/fonts/FZYTK.TTF",
]


def remote_json(url):
    # Callers construct only fixed official public model URLs, never user input.
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310
                return json.load(response)
        except (OSError, IncompleteRead):
            if attempt == 4:
                raise
            time.sleep(2)


def transfer(entry):
    expected_urls = {
        repo.replace("/", "--")
        + "/"
        + name: f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        for repo, (revision, names) in REPOS.items()
        for name in names
    }
    expected_urls.update(
        {
            "RapidOcr/" + name: "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/"
            + name
            for name in OCR_FILES
        }
    )
    if expected_urls.get(entry["path"]) != entry["url"]:
        raise ValueError("Unexpected document model publisher or file")
    target = safe_target(BASE, entry["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = safe_target(BASE, entry["path"] + ".download")
    if not target.exists():
        for attempt in range(5):
            offset = partial.stat().st_size if partial.exists() else 0
            if offset == entry["size"]:
                break
            try:
                # Some CDNs cache a ranged response under the bare URL. Separate
                # offsets in the cache key; bytes still must match upstream SHA-256.
                fetch_url = entry["url"] + f"?download=true&ics_offset={offset}"
                req = urllib.request.Request(
                    fetch_url, headers={"Range": f"bytes={offset}-"} if offset else {}
                )
                with urllib.request.urlopen(req, timeout=90) as response:  # nosec B310
                    append = offset > 0 and response.status == 206
                    # ModelScope's download endpoint may return 200 for a Range
                    # response. Accept only the exact remaining byte count; the
                    # final upstream SHA-256 remains mandatory before activation.
                    if (
                        offset > 0
                        and response.status == 200
                        and response.headers.get("Content-Length") == str(entry["size"] - offset)
                    ):
                        append = True
                    if response.status == 206 and not response.headers.get(
                        "Content-Range", ""
                    ).startswith(f"bytes {offset}-"):
                        raise ValueError("Unexpected document model initial range")
                    if (
                        append
                        and response.status == 206
                        and not response.headers.get("Content-Range", "").startswith(
                            f"bytes {offset}-"
                        )
                    ):
                        raise ValueError("Unexpected document model range")
                    with partial.open("ab" if append else "wb") as output:
                        shutil.copyfileobj(response, output, 1024 * 1024)
            except (OSError, IncompleteRead):
                if attempt == 4:
                    raise
                time.sleep(2)
        candidate = partial
    else:
        candidate = target
    if candidate.stat().st_size != entry["size"]:
        raise ValueError("Document model transfer incomplete")
    checksum = digest(candidate)
    if entry.get("sha256") and checksum != entry["sha256"]:
        raise ValueError("Document model SHA-256 mismatch")
    if entry.get("git_blob") and git_blob(candidate) != entry["git_blob"]:
        raise ValueError("Document model upstream blob mismatch")
    if candidate != target:
        candidate.rename(target)
    entry["sha256"] = checksum
    print("Document asset verified: " + entry["path"], flush=True)


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        entries = json.loads(LOCK.read_text(encoding="utf-8"))["files"]
    else:
        entries = []
        for repo, (revision, names) in REPOS.items():
            tree = remote_json(
                f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
            )
            by_name = {item["path"]: item for item in tree}
            for name in names:
                item = by_name[name]
                entries.append(
                    {
                        "path": repo.replace("/", "--") + "/" + name,
                        "size": item["size"],
                        "url": f"https://huggingface.co/{repo}/resolve/{revision}/{name}",
                        "sha256": item.get("lfs", {}).get("oid"),
                        "git_blob": None if item.get("lfs") else item["oid"],
                    }
                )
        tree = remote_json(
            "https://www.modelscope.cn/api/v1/models/RapidAI/RapidOCR/repo/files?Revision=v3.8.0&Recursive=true"
        )
        by_name = {item["Path"]: item for item in tree["Data"]["Files"]}
        for name in OCR_FILES:
            item = by_name[name]
            if len(item["Sha256"]) != 64:
                raise ValueError("Upstream OCR hash missing")
            entries.append(
                {
                    "path": "RapidOcr/" + name,
                    "size": item["Size"],
                    "sha256": item["Sha256"],
                    "url": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/"
                    + name,
                }
            )
    if shutil.disk_usage(BASE).free < 5 * 1024**3:
        raise ValueError("Keep at least five GiB free")
    for entry in entries:
        transfer(entry)
    LOCK.write_text(
        json.dumps({"schema_version": 1, "files": entries}, indent=2) + "\n", encoding="utf-8"
    )
    print("Document models PASS", flush=True)


if __name__ == "__main__":
    main()
