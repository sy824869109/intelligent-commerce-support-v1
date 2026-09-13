"""Fetch only pinned public model files; never import or change the KF reference project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "_local_artifacts/models"
LOCK = ROOT / "deploy/dev-environment/models.lock.json"
MODELS = {
    "bge-m3": ("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181", "mit"),
    "bge-reranker-v2-m3": (
        "BAAI/bge-reranker-v2-m3",
        "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        "apache-2.0",
    ),
}
FILES = {
    "bge-m3": (
        "README.md",
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
        "pytorch_model.bin",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ),
    "bge-reranker-v2-m3": (
        "README.md",
        "config.json",
        "model.safetensors",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ),
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_target(base: Path, relative: str) -> Path:
    path = base / relative
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(base.resolve())
        or not path.resolve().is_relative_to(ROOT.resolve())
    ):
        raise ValueError("Model path escapes its owned directory")
    return path


def remote_json(url):
    if not url.startswith("https://huggingface.co/api/models/BAAI/"):
        raise ValueError("Metadata source outside fixed publisher")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310 - fixed HTTPS publisher.
                return json.load(response)
        except OSError:
            if attempt == 3:
                raise
            print("Model metadata request interrupted; retrying fixed source", flush=True)
            time.sleep(2)


def git_blob(path: Path) -> str:
    # Git SHA-1 is used only to match small upstream blobs; the delivery lock uses SHA-256.
    content = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content, usedforsecurity=False
    ).hexdigest()


def download(url: str, temporary: Path, size: int):
    """Resume only this fixed-revision owned temporary file, then validate its full hash."""
    if not url.startswith("https://huggingface.co/BAAI/") or urlsplit(url).scheme != "https":
        raise ValueError("Model download outside fixed HTTPS publisher")
    for attempt in range(4):
        offset = temporary.stat().st_size if temporary.exists() else 0
        request = urllib.request.Request(
            url, headers={"Range": f"bytes={offset}-"} if offset else {}
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310 - pinned public HTTPS artifacts, SHA-256 checked.
                append = offset > 0 and response.status == 206
                if append and not response.headers.get("Content-Range", "").startswith(
                    f"bytes {offset}-"
                ):
                    raise ValueError("Unexpected model resume range")
                with temporary.open("ab" if append else "wb") as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            if temporary.stat().st_size == size:
                return
            if temporary.stat().st_size > size:
                raise ValueError("Model transfer larger than upstream size")
            if attempt == 3:
                raise ValueError("Model transfer incomplete; preserved for resume")
            print("Partial transfer preserved; continuing pinned model download", flush=True)
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
            print("Model transfer interrupted; retrying the pinned file", flush=True)
            time.sleep(2)


def prepare(refresh_lock: bool = False):
    if LOCK.exists() and not refresh_lock:
        record = json.loads(LOCK.read_text(encoding="utf-8"))
    elif refresh_lock:
        record = {"schema_version": 1, "models": {}}
        for name, (repo, revision, license_name) in MODELS.items():
            tree = remote_json(
                f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
            )
            metadata = {item["path"]: item for item in tree}
            entries = []
            for relative in FILES[name]:
                item = metadata[relative]
                entries.append(
                    {
                        "path": relative,
                        "size": item["size"],
                        "git_blob": item["oid"],
                        "sha256": item.get("lfs", {}).get("oid"),
                    }
                )
            record["models"][name] = {
                "repo": repo,
                "revision": revision,
                "license": license_name,
                "files": entries,
            }
    else:
        raise ValueError("Reviewed model lock missing; use --create-lock explicitly")
    for name, model in record["models"].items():
        if (
            name not in MODELS
            or (model["repo"], model["revision"], model["license"]) != MODELS[name]
        ):
            raise ValueError("Model identity changed")
        if {item["path"] for item in model["files"]} != set(FILES[name]):
            raise ValueError("Model file scope changed")
        for item in model["files"]:
            relative = item["path"]
            target = safe_target(DESTINATION / name, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = item["sha256"]
            if target.exists():
                actual = digest(target)
                if target.stat().st_size != item["size"] or (expected and expected != actual):
                    raise ValueError("Existing model file mismatched; not overwritten")
            else:
                # Only these known read-only reference weights can be reused, after hashing.
                reference = Path("F:/heima/knowforge-rag-platform02/models") / name / relative
                temporary = target.with_suffix(target.suffix + ".download")
                if reference.is_file() and (
                    (expected and digest(reference) == expected)
                    or (not expected and git_blob(reference) == item["git_blob"])
                ):
                    shutil.copyfile(reference, temporary)
                else:
                    if shutil.disk_usage(ROOT).free < item["size"] + 5 * 1024**3:
                        raise ValueError("Preserve at least 5 GiB free on project disk")
                    url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{relative}"
                    download(url, temporary, item["size"])
                actual = digest(temporary)
                if temporary.stat().st_size != item["size"] or (expected and expected != actual):
                    raise ValueError("Downloaded model hash/size mismatch; not activated")
                temporary.rename(target)
            item["sha256"] = actual
            print(f"Model file verified: {name}/{relative}", flush=True)
    if refresh_lock:
        LOCK.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Pinned model files ready; this is not a RAG quality evaluation.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-lock", action="store_true")
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    prepare(args.create_lock)


if __name__ == "__main__":
    main()
