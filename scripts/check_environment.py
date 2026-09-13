"""Consolidated V1 environment checks; NOT a business/RAG acceptance suite."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import importlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess  # nosec B404 - fixed current-interpreter pip check; no shell or user command.
import sys
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "_local_artifacts/environment"
V1 = Path("F:/heima/ai/python/day01/Anaconda/envs/intelligent-commerce-support-v1/python.exe")


def runtime():
    if os.name == "nt" and Path(sys.executable).resolve() != V1.resolve():
        raise ValueError("Use the user-selected intelligent-commerce-support-v1 interpreter")
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, cwd=ROOT)  # nosec B603
    if result.returncode:
        raise ValueError("Dependency conflicts")
    for module in (
        "fastapi",
        "sqlalchemy",
        "alembic",
        "redis",
        "boto3",
        "pymilvus",
        "langchain_core",
        "langchain_openai",
        "langchain_milvus",
        "langchain_huggingface",
        "torch",
        "sentence_transformers",
        "docling.document_converter",
        "pypdf",
    ):
        importlib.import_module(module)
    return {
        "interpreter": str(Path(sys.executable)),
        "python": sys.version.split()[0],
        "torch": importlib.metadata.version("torch"),
        "langchain": importlib.metadata.version("langchain"),
    }


def models():
    from prepare_local_models import digest, LOCK, DESTINATION, MODELS, FILES, safe_target
    from langchain_huggingface import HuggingFaceEmbeddings
    from sentence_transformers import CrossEncoder
    import numpy as np
    import torch

    record = json.loads(LOCK.read_text(encoding="utf-8"))
    if set(record["models"]) != set(MODELS):
        raise ValueError("Model scope mismatch")
    for name, info in record["models"].items():
        if (info["repo"], info["revision"], info["license"]) != MODELS[name]:
            raise ValueError("Model revision mismatch")
        if {entry["path"] for entry in info["files"]} != set(FILES[name]):
            raise ValueError("Model files changed")
        for entry in info["files"]:
            if digest(safe_target(DESTINATION / name, entry["path"])) != entry["sha256"]:
                raise ValueError("Model hash mismatch")
    torch.set_num_threads(4)
    documents = ["订单签收后七天内可以申请退货，商品须完好。", "耳机支持蓝牙连接和主动降噪。"]
    query = "收到商品后怎么退货？"
    embed = HuggingFaceEmbeddings(
        model_name=str(DESTINATION / "bge-m3"),
        model_kwargs={"device": "cpu", "local_files_only": True, "trust_remote_code": False},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 2},
    )
    vectors = embed.embed_documents(documents)
    query_vector = embed.embed_query(query)
    array = np.asarray(vectors)
    if array.shape != (2, 1024) or not np.isfinite(array).all():
        raise ValueError("Embedding output invalid")
    if not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-4):
        raise ValueError("Embedding normalization invalid")
    # Release one model before loading the other on a 32 GiB development laptop.
    del embed
    rerank = CrossEncoder(
        str(DESTINATION / "bge-reranker-v2-m3"),
        device="cpu",
        local_files_only=True,
        trust_remote_code=False,
        max_length=256,
    )
    scores = rerank.predict([(query, document) for document in documents], batch_size=2)
    if not np.isfinite(scores).all() or scores[0] <= scores[1]:
        raise ValueError("Synthetic reranking sanity check failed")
    del rerank
    # Exercise the actual KF-style LangChain -> Milvus dense + server BM25 adapter.
    from langchain_core.embeddings import Embeddings
    from langchain_milvus import Milvus, BM25BuiltInFunction
    from pymilvus import MilvusClient
    import local_infra as infra
    from database_local import load_database

    database = (
        load_database()
    )  # Verifies dev project, endpoint, image and ownership before secrets.
    database.close()
    config = infra.validate_local_files()
    credentials = infra.storage_credentials()
    collection = "env_probe_" + uuid.uuid4().hex

    class SyntheticEmbeddings(Embeddings):
        def embed_documents(self, texts):
            if list(texts) != documents:
                raise ValueError("Probe is limited to its synthetic documents")
            return vectors

        def embed_query(self, text):
            if text != query:
                raise ValueError("Probe query scope changed")
            return query_vector

    connection = {
        "uri": f"http://127.0.0.1:{config['MILVUS_PORT']}",
        "token": credentials.milvus_token,
    }
    client = MilvusClient(**connection)
    created = False
    try:
        if client.has_collection(collection):
            raise ValueError("Unexpected probe name collision")
        store = Milvus(
            embedding_function=SyntheticEmbeddings(),
            connection_args=connection,
            collection_name=collection,
            builtin_function=BM25BuiltInFunction(),
            vector_field=["dense", "sparse"],
            consistency_level="Strong",
            auto_id=True,
        )
        created = True
        store.add_texts(documents)
        hits = store.similarity_search(
            query, k=2, ranker_type="weighted", ranker_params={"weights": [0.55, 0.45]}
        )
        if not hits or hits[0].page_content != documents[0]:
            raise ValueError("Hybrid search sanity check failed")
    finally:
        if created and client.has_collection(collection):
            client.drop_collection(collection)
        client.close()
    return {
        "dimension": 1024,
        "device": "cpu",
        "hybrid_search": "PASS",
        "synthetic_cleanup": "PASS",
        "quality_golden_set": "NOT_RUN",
    }


def request(url, payload=None):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or parsed.port not in {24318, 29090, 23200, 23100}
    ):
        raise ValueError("Probe requests are limited to reviewed loopback telemetry ports")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310 - validated local HTTP above.
        return json.load(response)


def telemetry():
    from environment_services import health

    health()
    now = time.time_ns()
    probe = uuid.uuid4().hex
    resource = {"attributes": [{"key": "service.name", "value": {"stringValue": "ics-env-probe"}}]}
    trace = {
        "resourceSpans": [
            {
                "resource": resource,
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": probe,
                                "spanId": probe[:16],
                                "name": "environment-smoke",
                                "kind": 1,
                                "startTimeUnixNano": str(now),
                                "endTimeUnixNano": str(now + 1000000),
                            }
                        ]
                    }
                ],
            }
        ]
    }
    metric = {
        "resourceMetrics": [
            {
                "resource": resource,
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "ics_environment_probe",
                                "gauge": {"dataPoints": [{"timeUnixNano": str(now), "asInt": "1"}]},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    logs = {
        "resourceLogs": [
            {
                "resource": resource,
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "timeUnixNano": str(now),
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "body": {"stringValue": "synthetic environment probe " + probe},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    for name, payload in (("traces", trace), ("metrics", metric), ("logs", logs)):
        response = request(f"http://127.0.0.1:24318/v1/{name}", payload)
        if response.get("partialSuccess"):
            raise ValueError("Collector partially rejected probe")
    for attempt in range(20):
        try:
            result = request("http://127.0.0.1:29090/api/v1/query?query=ics_environment_probe")
            if not result["data"]["result"]:
                raise ValueError("Metric not persisted")
            trace_result = request(f"http://127.0.0.1:23200/api/traces/{probe}")
            if not trace_result:
                raise ValueError("Trace not persisted")
            query = urllib.parse.urlencode(
                {
                    "query": '{service_name="ics-env-probe"} |= "' + probe + '"',
                    "start": str(now - 1000000000),
                    "end": str(time.time_ns()),
                }
            )
            if not request("http://127.0.0.1:23100/loki/api/v1/query_range?" + query)["data"][
                "result"
            ]:
                raise ValueError("Log not persisted")
            return {"trace_id": probe, "metrics": "PASS", "traces": "PASS", "logs": "PASS"}
        except (OSError, KeyError, ValueError):
            if attempt == 19:
                raise
            time.sleep(2)


def cloud_config():
    from dotenv import dotenv_values

    path = LOCAL / "model.env"
    if not path.exists():
        return {"status": "NEEDS_PRIVATE_CONFIGURATION", "live_call": "NOT_RUN"}
    if path.is_symlink():
        raise ValueError("Cloud configuration cannot be a link")
    config = dotenv_values(path, interpolate=False)
    required = [config.get(name) for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")]
    if not all(required):
        return {"status": "NEEDS_PRIVATE_CONFIGURATION", "live_call": "NOT_RUN"}
    url = urllib.parse.urlsplit(required[0])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Cloud endpoint must be credential-free HTTPS")
    return {"status": "CONFIGURED_NOT_CALLED", "live_call": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", choices=["runtime", "models", "telemetry", "cloud", "all"])
    args = parser.parse_args()
    LOCAL.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["LANGSMITH_TRACING"] = "false"
    # Avoid SDK exception logging printing authentication material on failed probes.
    logging.disable(logging.CRITICAL)
    checks = {"runtime": runtime, "models": models, "telemetry": telemetry, "cloud": cloud_config}
    result = {"checked_at": datetime.now(UTC).isoformat(), "checks": {}}
    failed = False
    pending = False
    for name, check in checks.items():
        if args.section not in (name, "all"):
            continue
        try:
            detail = check()
            state = (
                "PENDING"
                if detail.get("status") in {"NEEDS_PRIVATE_CONFIGURATION", "CONFIGURED_NOT_CALLED"}
                else "PASS"
            )
            pending = pending or state == "PENDING"
            result["checks"][name] = {"status": state, "details": detail}
            print(
                f"{name}: {state} ({detail.get('status', 'synthetic environment check')})",
                flush=True,
            )
        except Exception as exc:
            failed = True
            result["checks"][name] = {"status": "FAILED", "error_type": type(exc).__name__}
            print(f"{name}: FAILED ({type(exc).__name__}; SDK details withheld)", flush=True)
    (LOCAL / f"check-{args.section}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return 1 if failed else 2 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
