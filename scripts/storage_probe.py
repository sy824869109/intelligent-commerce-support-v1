"""M01 合成数据探针；可导入，不启动服务，不读取环境凭据，不接触业务数据。

运行依赖由调用方锁定：boto3==1.43.89、pymilvus==2.5.18。
SDK 仅在执行时导入；HTTP/S3、Milvus 均须为调用方已授权的开发实例。
仅删除本探针 UUID 对象或集合，绝不清空桶、枚举删除历史集合或直删 Milvus 文件。
SDK 参考：Milvus v2.5.x MilvusClient create_index/flush/search/describe_collection；
AWS Boto3 S3 put/get/head/list_objects_v2 与 multipart API 官方文档。
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import logging
import re
import struct
import time
from typing import Any, Callable, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
import zlib


KNOWLEDGE_BUCKET = "ics-knowledge"
MILVUS_BUCKET = "ics-milvus"
RPC_TIMEOUT = 60
_VECTOR = [1.0, 0.0, 0.0, 0.0]
_ROW_ID = 101
_ROW_COUNT = 2048
_INDEX_NAME = "probe_hnsw"
_SYNTHETIC = b"M01 synthetic storage contract; no customer data.\n"


class ProbeFailure(RuntimeError):
    """仅暴露固定检查阶段码，不携带底层异常、凭据、请求或响应正文。"""


def _require(condition: bool) -> None:
    if not condition:
        raise ProbeFailure("ASSERTION_FAILED")


def _step(results: dict, name: str, operation: Callable[[], Any]) -> Any:
    try:
        value = operation()
    except Exception:
        raise ProbeFailure(name) from None
    results[name] = "PASS"
    return value


@contextmanager
def _quiet_sdks() -> Iterator[None]:
    """探针为单进程串行诊断；暂时禁用已加载 SDK 日志，避免异常打印请求。"""
    prefixes = ("pymilvus", "boto3", "botocore", "urllib3", "grpc")
    names = set(prefixes)
    names.update(
        name
        for name in logging.Logger.manager.loggerDict
        if name.startswith(tuple(prefix + "." for prefix in prefixes))
    )
    original = {name: logging.getLogger(name).disabled for name in names}
    try:
        for name in names:
            logging.getLogger(name).disabled = True
        yield
    finally:
        for name, disabled in original.items():
            logging.getLogger(name).disabled = disabled


def _sdk() -> tuple:
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        from botocore.exceptions import ClientError
        from pymilvus import DataType, MilvusClient
    except Exception:
        raise ProbeFailure("SDK_IMPORT") from None
    return boto3, UNSIGNED, Config, ClientError, DataType, MilvusClient


def _s3(sdk: tuple, endpoint: str, credentials: dict | None) -> Any:
    boto3, unsigned, config, *_ = sdk
    options = {
        "endpoint_url": endpoint,
        "region_name": "us-east-1",
        "config": config(
            signature_version="s3v4" if credentials is not None else unsigned,
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"total_max_attempts": 2, "mode": "standard"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    }
    if credentials is not None:
        options["aws_access_key_id"] = credentials["access_key"]
        options["aws_secret_access_key"] = credentials["secret_key"]
    return boto3.client("s3", **options)


def _read(response: dict) -> bytes:
    body = response["Body"]
    try:
        return body.read()
    finally:
        body.close()


def _denied(operation: Callable[[], Any], error_type: type) -> None:
    try:
        result = operation()
    except error_type as exc:
        # Only an authentication/authorization denial counts. A 404 or network error
        # would give false confidence that the bucket boundary actually works.
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = str(exc.response.get("Error", {}).get("Code", ""))
        _require(status in (401, 403))
        _require(
            code
            in {
                "AccessDenied",
                "InvalidAccessKeyId",
                "SignatureDoesNotMatch",
                "InvalidToken",
                "Unauthorized",
                "Forbidden",
                "401",
                "403",
            }
        )
        return
    if isinstance(result, dict) and "Body" in result:
        result["Body"].close()
    raise ProbeFailure("EXPECTED_AUTHORIZATION_DENIAL")


def _absent(operation: Callable[[], Any], error_type: type) -> None:
    try:
        operation()
    except error_type as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = str(exc.response.get("Error", {}).get("Code", ""))
        _require(status == 404 and code in {"404", "NoSuchKey", "NotFound", "NoSuchUpload"})
        return
    raise ProbeFailure("EXPECTED_NOT_FOUND")


def _list_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    seen_tokens: set[str] = set()
    for _ in range(100):
        request = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 2}
        if token is not None:
            request["ContinuationToken"] = token
        page = client.list_objects_v2(**request)
        _require(len(page.get("Contents", [])) <= request["MaxKeys"])
        keys.extend(item["Key"] for item in page.get("Contents", []))
        if not page.get("IsTruncated", False):
            return keys
        token = page.get("NextContinuationToken")
        _require(bool(token) and token not in seen_tokens)
        seen_tokens.add(token)
    raise ProbeFailure("PAGINATION_LIMIT")


def _create_milvus(client: Any, datatype: Any, collection: str, marker: str) -> None:
    # With custom schema pymilvus serializes schema.description; a create_collection
    # description kwarg alone is ignored and would break persistence ownership checks.
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False, description=marker)
    schema.add_field(field_name="id", datatype=datatype.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=datatype.FLOAT_VECTOR, dim=4)
    client.create_collection(
        collection_name=collection,
        schema=schema,
        description=marker,
        consistency_level="Strong",
        num_shards=1,
        timeout=RPC_TIMEOUT,
    )


def _insert_flush_index(client: Any, collection: str) -> None:
    # One 2048-row batch exceeds the baseline 1024-row indexing threshold. The
    # target is unique and separated from all other deterministic synthetic vectors.
    rows = [{"id": _ROW_ID, "vector": _VECTOR}]
    rows.extend(
        {
            "id": _ROW_ID + index,
            "vector": [
                2.0 + (index % 32) / 32,
                ((index // 32) % 32) / 32,
                (index % 17) / 17,
                (index % 13) / 13,
            ],
        }
        for index in range(1, _ROW_COUNT)
    )
    result = client.insert(
        collection_name=collection,
        data=rows,
        timeout=RPC_TIMEOUT,
    )
    _require(result.get("insert_count") == _ROW_COUNT)
    client.flush(collection_name=collection, timeout=RPC_TIMEOUT)
    index = client.prepare_index_params()
    index.add_index(
        field_name="vector",
        index_name=_INDEX_NAME,
        index_type="HNSW",
        metric_type="L2",
        params={"M": 8, "efConstruction": 64},
    )
    client.create_index(collection_name=collection, index_params=index, timeout=RPC_TIMEOUT)
    _index_ready(client, collection)


def _index_ready(client: Any, collection: str) -> None:
    """不能用索引声明存在代替构建完成；确认全部 2048 行确实完成索引。"""
    for attempt in range(20):
        description = client.describe_index(
            collection_name=collection,
            index_name=_INDEX_NAME,
            timeout=10,
        )
        _require(isinstance(description, dict))
        _require(description.get("index_type") == "HNSW")
        _require(description.get("metric_type") == "L2")
        _require(description.get("field_name") == "vector")
        _require(description.get("index_name") == _INDEX_NAME)
        _require(description.get("state") not in {"Failed", "None"})
        if (
            description.get("state") == "Finished"
            and int(description.get("indexed_rows", -1)) == _ROW_COUNT
            and int(description.get("total_rows", -1)) == _ROW_COUNT
            and int(description.get("pending_index_rows", -1)) == 0
        ):
            return
        if attempt < 19:
            time.sleep(1)
    raise ProbeFailure("MILVUS_INDEX_NOT_READY")


def _search(client: Any, collection: str) -> None:
    hits = client.search(
        collection_name=collection,
        data=[_VECTOR],
        anns_field="vector",
        limit=1,
        search_params={"metric_type": "L2", "params": {"ef": 64}},
        consistency_level="Strong",
        timeout=RPC_TIMEOUT,
    )
    _require(len(hits) == 1 and len(hits[0]) == 1)
    _require(int(hits[0][0]["id"]) == _ROW_ID)
    _require(abs(float(hits[0][0]["distance"])) < 1e-6)


def _milvus_objects(client: Any, collection_id: Any) -> None:
    """关联本集合 data log 的 segment ID 与真实 index_log；只读，绝不直删。"""
    wanted = str(collection_id)
    _require(wanted.isdecimal())
    paginator = client.get_paginator("list_objects_v2")
    data_segments: set[str] = set()
    index_segments: set[str] = set()
    for number, page in enumerate(paginator.paginate(Bucket=MILVUS_BUCKET)):
        _require(number < 100)
        for item in page.get("Contents", []):
            parts = item["Key"].split("/")
            if item.get("Size", 0) <= 0:
                continue
            # Milvus 2.5 data path: insert_log/collection/partition/segment/field/log.
            for family in ("insert_log", "stats_log"):
                if family in parts:
                    position = parts.index(family)
                    if len(parts) > position + 3 and parts[position + 1] == wanted:
                        segment = parts[position + 3]
                        _require(segment.isdecimal())
                        data_segments.add(segment)
            # Index path: index_log/build/version/partition/segment/file; it does
            # not include collection ID, so a mere nonempty bucket proves nothing.
            if "index_log" in parts:
                position = parts.index("index_log")
                if len(parts) > position + 5:
                    segment = parts[position + 4]
                    _require(segment.isdecimal())
                    index_segments.add(segment)
    _require(bool(data_segments) and bool(data_segments.intersection(index_segments)))


def _milvus_denied(factory: Any, uri: str, token: str) -> None:
    """只执行列集合；只认可结构化 gRPC 权限码，不把断网/超时当鉴权成功。"""
    client = None
    denied = False
    try:
        client = factory(uri=uri, token=token, timeout=10)
        client.list_collections(timeout=10)
    except Exception as exc:
        visited: set[int] = set()
        current: BaseException | None = exc
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            code = getattr(current, "code", None)
            if callable(code):
                code = code()
            if getattr(code, "name", None) in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
                denied = True
                break
            current = current.__cause__ or current.__context__
    finally:
        if client is not None:
            client.close()
    _require(denied)


def _small_png() -> bytes:
    """生成合法的 2×2 RGB 合成图片；不是畸形图片、资源消耗或漏洞利用载荷。"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    scanlines = (b"\x00" + b"\x20\x80\xc0" * 2) * 2
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _image_original(client: Any, bucket: str, key: str, original: bytes) -> None:
    # Unknown query parameters cannot be passed in boto3's modeled GetObject
    # arguments. Add the two harmless values before signing so this is a valid
    # authenticated GET, not a deliberately broken SigV4 request.
    event = "before-sign.s3.GetObject"
    hook_id = "m01-probe-image-" + uuid4().hex

    def add_dimensions(request: Any, **_: Any) -> None:
        parts = urlsplit(request.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({"width": "1", "height": "1"})
        request.url = urlunsplit(parts._replace(query=urlencode(query)))

    client.meta.events.register(event, add_dimensions, unique_id=hook_id)
    try:
        result = client.get_object(Bucket=bucket, Key=key)
        content = _read(result)
        _require(content == original)
    finally:
        client.meta.events.unregister(event, unique_id=hook_id)


def run_checks(
    endpoint: str,
    admin: dict,
    scoped: dict,
    milvus_uri: str,
    milvus_token: str,
) -> dict:
    """运行 S3 与 Milvus 兼容检查；仅合成数据，不启动/重启服务或初始化桶。

    两桶须由调用方预建。admin 可操作两桶，scoped 仅可读写 ics-knowledge。
    返回固定检查名称与 PASS；失败只抛可公开阶段码。finally 清理本轮生成的
    明确对象键、未完成分片和 UUID 集合；清理失败同样失败，不能算作验收通过。
    此函数的 release/load 是内存重载，不等于服务重启或灾备恢复验证。
    """
    sdk = _sdk()
    _, _, _, client_error, datatype, milvus_class = sdk
    results: dict[str, str] = {}
    identifier = uuid4().hex
    prefix = f"m01_probe/{identifier}/"
    collection = f"m01_probe_{identifier}"
    clients: list[Any] = []
    objects: set[tuple[str, str]] = set()
    uploads: set[tuple[str, str]] = set()
    milvus = None
    administrator = None
    knowledge = None
    collection_attempted = False
    failure: str | None = None
    with _quiet_sdks():
        try:
            administrator = _step(results, "S3_ADMIN_CONNECT", lambda: _s3(sdk, endpoint, admin))
            clients.append(administrator)
            knowledge = _step(results, "S3_SCOPED_CONNECT", lambda: _s3(sdk, endpoint, scoped))
            clients.append(knowledge)
            anonymous = _step(results, "S3_ANONYMOUS_CLIENT", lambda: _s3(sdk, endpoint, None))
            clients.append(anonymous)
            wrong = {"access_key": scoped["access_key"], "secret_key": uuid4().hex}
            bad_signature = _step(
                results, "S3_WRONG_SIGNATURE_CLIENT", lambda: _s3(sdk, endpoint, wrong)
            )
            clients.append(bad_signature)
            for bucket in (KNOWLEDGE_BUCKET, MILVUS_BUCKET):
                _step(
                    results,
                    f"S3_ADMIN_HEAD_{bucket.upper().replace('-', '_')}",
                    lambda bucket=bucket: administrator.head_bucket(Bucket=bucket),
                )

            key = prefix + "small.bin"
            objects.add((KNOWLEDGE_BUCKET, key))
            _step(
                results,
                "S3_PUT",
                lambda: knowledge.put_object(
                    Bucket=KNOWLEDGE_BUCKET,
                    Key=key,
                    Body=_SYNTHETIC,
                    Metadata={"probe-sha256": sha256(_SYNTHETIC).hexdigest()},
                ),
            )
            content = _step(
                results,
                "S3_GET",
                lambda: _read(knowledge.get_object(Bucket=KNOWLEDGE_BUCKET, Key=key)),
            )
            _step(
                results,
                "S3_SMALL_SHA256",
                lambda: _require(sha256(content).digest() == sha256(_SYNTHETIC).digest()),
            )
            head = _step(
                results, "S3_HEAD", lambda: knowledge.head_object(Bucket=KNOWLEDGE_BUCKET, Key=key)
            )
            _step(
                results,
                "S3_HEAD_METADATA",
                lambda: _require(
                    head["ContentLength"] == len(_SYNTHETIC)
                    and head["Metadata"].get("probe-sha256") == sha256(_SYNTHETIC).hexdigest(),
                ),
            )

            def check_range() -> None:
                response = knowledge.get_object(
                    Bucket=KNOWLEDGE_BUCKET, Key=key, Range="bytes=3-13"
                )
                body = _read(response)
                _require(response["ResponseMetadata"]["HTTPStatusCode"] == 206)
                _require(response.get("ContentRange") == f"bytes 3-13/{len(_SYNTHETIC)}")
                _require(body == _SYNTHETIC[3:14])

            _step(results, "S3_RANGE", check_range)

            page_keys = [prefix + f"page/{index}.bin" for index in range(5)]

            def check_pagination() -> None:
                for page_key in page_keys:
                    objects.add((KNOWLEDGE_BUCKET, page_key))
                    knowledge.put_object(Bucket=KNOWLEDGE_BUCKET, Key=page_key, Body=_SYNTHETIC)
                found = _list_keys(knowledge, KNOWLEDGE_BUCKET, prefix + "page/")
                _require(len(found) == len(set(found)) and set(found) == set(page_keys))

            _step(results, "S3_PAGINATION", check_pagination)

            nested_keys = [prefix + "nested/a/item.bin", prefix + "nested/b/item.bin"]

            def check_nested_tags() -> None:
                for index, nested_key in enumerate(nested_keys):
                    objects.add((KNOWLEDGE_BUCKET, nested_key))
                    knowledge.put_object(
                        Bucket=KNOWLEDGE_BUCKET, Key=nested_key, Body=_SYNTHETIC + bytes([index])
                    )
                    administrator.put_object_tagging(
                        Bucket=KNOWLEDGE_BUCKET,
                        Key=nested_key,
                        Tagging={"TagSet": [{"Key": "probe-branch", "Value": str(index)}]},
                    )
                for index, nested_key in enumerate(nested_keys):
                    response = administrator.get_object_tagging(
                        Bucket=KNOWLEDGE_BUCKET, Key=nested_key
                    )
                    _require(
                        response.get("TagSet") == [{"Key": "probe-branch", "Value": str(index)}]
                    )
                    content = _read(knowledge.get_object(Bucket=KNOWLEDGE_BUCKET, Key=nested_key))
                    _require(content == _SYNTHETIC + bytes([index]))

            _step(results, "S3_NESTED_SAME_BASENAME_TAGGING_ISOLATION", check_nested_tags)

            image_key = prefix + "small.png"
            objects.add((KNOWLEDGE_BUCKET, image_key))

            def check_original_image() -> None:
                png = _small_png()
                knowledge.put_object(
                    Bucket=KNOWLEDGE_BUCKET, Key=image_key, Body=png, ContentType="image/png"
                )
                _image_original(knowledge, KNOWLEDGE_BUCKET, image_key, png)

            _step(results, "S3_IMAGE_DIMENSIONS_RETURN_ORIGINAL_BYTES", check_original_image)

            multipart_key = prefix + "complete.bin"
            objects.add((KNOWLEDGE_BUCKET, multipart_key))

            def check_multipart() -> None:
                upload_id = knowledge.create_multipart_upload(
                    Bucket=KNOWLEDGE_BUCKET, Key=multipart_key
                )["UploadId"]
                uploads.add((multipart_key, upload_id))
                # The non-final part meets S3's 5 MiB minimum; the second part is small.
                chunks = (b"A" * (5 * 1024 * 1024), _SYNTHETIC)
                parts = []
                for number, chunk in enumerate(chunks, 1):
                    response = knowledge.upload_part(
                        Bucket=KNOWLEDGE_BUCKET,
                        Key=multipart_key,
                        UploadId=upload_id,
                        PartNumber=number,
                        Body=chunk,
                    )
                    parts.append({"PartNumber": number, "ETag": response["ETag"]})
                knowledge.complete_multipart_upload(
                    Bucket=KNOWLEDGE_BUCKET,
                    Key=multipart_key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
                uploads.discard((multipart_key, upload_id))
                actual = _read(knowledge.get_object(Bucket=KNOWLEDGE_BUCKET, Key=multipart_key))
                _require(sha256(actual).digest() == sha256(b"".join(chunks)).digest())

            _step(results, "S3_MULTIPART_COMPLETE_SHA256", check_multipart)

            abort_key = prefix + "abort.bin"
            objects.add((KNOWLEDGE_BUCKET, abort_key))

            def check_abort() -> None:
                upload_id = knowledge.create_multipart_upload(
                    Bucket=KNOWLEDGE_BUCKET, Key=abort_key
                )["UploadId"]
                uploads.add((abort_key, upload_id))
                knowledge.upload_part(
                    Bucket=KNOWLEDGE_BUCKET,
                    Key=abort_key,
                    UploadId=upload_id,
                    PartNumber=1,
                    Body=_SYNTHETIC,
                )
                knowledge.abort_multipart_upload(
                    Bucket=KNOWLEDGE_BUCKET, Key=abort_key, UploadId=upload_id
                )
                uploads.discard((abort_key, upload_id))
                _absent(
                    lambda: knowledge.list_parts(
                        Bucket=KNOWLEDGE_BUCKET, Key=abort_key, UploadId=upload_id
                    ),
                    client_error,
                )
                _absent(
                    lambda: knowledge.head_object(Bucket=KNOWLEDGE_BUCKET, Key=abort_key),
                    client_error,
                )

            _step(results, "S3_MULTIPART_ABORT", check_abort)

            _step(
                results,
                "S3_ANONYMOUS_DENIED",
                lambda: _denied(
                    lambda: anonymous.get_object(Bucket=KNOWLEDGE_BUCKET, Key=key), client_error
                ),
            )
            _step(
                results,
                "S3_ANONYMOUS_WRITE_DENIED",
                lambda: _denied(
                    lambda: anonymous.put_object(Bucket=KNOWLEDGE_BUCKET, Key=key, Body=_SYNTHETIC),
                    client_error,
                ),
            )
            _step(
                results,
                "S3_ANONYMOUS_LIST_DENIED",
                lambda: _denied(
                    lambda: anonymous.list_objects_v2(
                        Bucket=KNOWLEDGE_BUCKET, Prefix=prefix, MaxKeys=1
                    ),
                    client_error,
                ),
            )
            _step(
                results,
                "S3_WRONG_SIGNATURE_DENIED",
                lambda: _denied(
                    lambda: bad_signature.get_object(Bucket=KNOWLEDGE_BUCKET, Key=key), client_error
                ),
            )
            cross_key = prefix + "cross-bucket.bin"
            objects.add((MILVUS_BUCKET, cross_key))
            _step(
                results,
                "S3_ADMIN_SECOND_BUCKET_PUT",
                lambda: administrator.put_object(
                    Bucket=MILVUS_BUCKET, Key=cross_key, Body=_SYNTHETIC
                ),
            )
            _step(
                results,
                "S3_CROSS_BUCKET_READ_DENIED",
                lambda: _denied(
                    lambda: knowledge.get_object(Bucket=MILVUS_BUCKET, Key=cross_key), client_error
                ),
            )
            _step(
                results,
                "S3_CROSS_BUCKET_WRITE_DENIED",
                lambda: _denied(
                    lambda: knowledge.put_object(
                        Bucket=MILVUS_BUCKET, Key=cross_key, Body=_SYNTHETIC
                    ),
                    client_error,
                ),
            )
            _step(
                results,
                "S3_CROSS_BUCKET_LIST_DENIED",
                lambda: _denied(
                    lambda: knowledge.list_objects_v2(
                        Bucket=MILVUS_BUCKET, Prefix=prefix, MaxKeys=1
                    ),
                    client_error,
                ),
            )
            _step(
                results,
                "S3_CROSS_BUCKET_DELETE_DENIED",
                lambda: _denied(
                    lambda: knowledge.delete_object(Bucket=MILVUS_BUCKET, Key=cross_key),
                    client_error,
                ),
            )
            copy_key = prefix + "forbidden-copy.bin"
            objects.add((KNOWLEDGE_BUCKET, copy_key))
            _step(
                results,
                "S3_CROSS_BUCKET_COPY_SOURCE_DENIED",
                lambda: _denied(
                    lambda: knowledge.copy_object(
                        Bucket=KNOWLEDGE_BUCKET,
                        Key=copy_key,
                        CopySource={"Bucket": MILVUS_BUCKET, "Key": cross_key},
                    ),
                    client_error,
                ),
            )
            _step(
                results,
                "S3_FORBIDDEN_COPY_NOT_CREATED",
                lambda: _absent(
                    lambda: administrator.head_object(Bucket=KNOWLEDGE_BUCKET, Key=copy_key),
                    client_error,
                ),
            )

            _step(
                results,
                "S3_DELETE",
                lambda: knowledge.delete_object(Bucket=KNOWLEDGE_BUCKET, Key=key),
            )
            _step(
                results,
                "S3_DELETED_NOT_FOUND",
                lambda: _absent(
                    lambda: knowledge.head_object(Bucket=KNOWLEDGE_BUCKET, Key=key), client_error
                ),
            )

            milvus = _step(
                results,
                "MILVUS_CONNECT",
                lambda: milvus_class(uri=milvus_uri, token=milvus_token, timeout=RPC_TIMEOUT),
            )
            _step(results, "MILVUS_AUTHENTICATED_LIST", lambda: milvus.list_collections(timeout=10))
            _step(
                results,
                "MILVUS_ANONYMOUS_DENIED",
                lambda: _milvus_denied(milvus_class, milvus_uri, ""),
            )
            _step(
                results,
                "MILVUS_WRONG_ROOT_DENIED",
                lambda: _milvus_denied(milvus_class, milvus_uri, "root:" + uuid4().hex),
            )
            collection_attempted = True
            _step(
                results,
                "MILVUS_CREATE_FLOAT32_DIM4",
                lambda: _create_milvus(milvus, datatype, collection, identifier),
            )
            _step(
                results,
                "MILVUS_INSERT_FLUSH_INDEX",
                lambda: _insert_flush_index(milvus, collection),
            )
            _step(
                results, "MILVUS_HNSW_FINISHED_2048_ROWS", lambda: _index_ready(milvus, collection)
            )
            _step(
                results,
                "MILVUS_LOAD",
                lambda: milvus.load_collection(collection_name=collection, timeout=RPC_TIMEOUT),
            )
            _step(results, "MILVUS_SEARCH_TARGET_ID", lambda: _search(milvus, collection))
            _step(
                results,
                "MILVUS_RELEASE",
                lambda: milvus.release_collection(collection_name=collection, timeout=RPC_TIMEOUT),
            )
            _step(
                results,
                "MILVUS_RELOAD",
                lambda: milvus.load_collection(collection_name=collection, timeout=RPC_TIMEOUT),
            )
            _step(results, "MILVUS_RELOAD_SEARCH_TARGET_ID", lambda: _search(milvus, collection))
            description = _step(
                results,
                "MILVUS_DESCRIBE",
                lambda: milvus.describe_collection(collection_name=collection, timeout=RPC_TIMEOUT),
            )
            _step(
                results,
                "MILVUS_S3_DATA_AND_INDEX_OBJECTS",
                lambda: _milvus_objects(administrator, description["collection_id"]),
            )
        except ProbeFailure as exc:
            failure = str(exc)
        except Exception:
            failure = "PROBE_SETUP"
        finally:
            cleanup_failed = False
            if milvus is not None:
                try:
                    if collection_attempted and milvus.has_collection(
                        collection_name=collection, timeout=RPC_TIMEOUT
                    ):
                        milvus.drop_collection(collection_name=collection, timeout=RPC_TIMEOUT)
                        _require(
                            not milvus.has_collection(
                                collection_name=collection, timeout=RPC_TIMEOUT
                            )
                        )
                except Exception:
                    cleanup_failed = True
                try:
                    milvus.close()
                except Exception:
                    cleanup_failed = True
            if knowledge is not None:
                for object_key, upload_id in uploads:
                    try:
                        knowledge.abort_multipart_upload(
                            Bucket=KNOWLEDGE_BUCKET, Key=object_key, UploadId=upload_id
                        )
                    except client_error as exc:
                        if exc.response.get("Error", {}).get("Code") != "NoSuchUpload":
                            cleanup_failed = True
                    except Exception:
                        cleanup_failed = True
            if administrator is not None:
                for bucket, object_key in objects:
                    try:
                        _require(object_key.startswith(prefix))
                        administrator.delete_object(Bucket=bucket, Key=object_key)
                        _absent(
                            lambda bucket=bucket, object_key=object_key: administrator.head_object(
                                Bucket=bucket, Key=object_key
                            ),
                            client_error,
                        )
                    except Exception:
                        cleanup_failed = True
            for client in clients:
                try:
                    client.close()
                except Exception:
                    cleanup_failed = True
            if cleanup_failed:
                failure = f"{failure}+CLEANUP_FAILED" if failure else "CLEANUP_FAILED"
    if failure is not None:
        raise ProbeFailure(failure) from None
    results["OWNED_PROBE_CLEANUP"] = "PASS"
    return results


def _manifest(manifest: dict) -> tuple[str, str, str]:
    identifier = manifest.get("probe_id", "")
    _require(isinstance(identifier, str) and re.fullmatch(r"[0-9a-f]{32}", identifier) is not None)
    collection = f"m01_probe_persist_{identifier}"
    key = f"m01_probe/{identifier}/persist.bin"
    _require(manifest.get("schema_version") == 1)
    _require(manifest.get("collection_name") == collection and manifest.get("object_key") == key)
    _require(manifest.get("sha256") == sha256(_SYNTHETIC).hexdigest())
    return identifier, collection, key


def persist_prepare(endpoint: str, scoped: dict, milvus_uri: str, milvus_token: str) -> dict:
    """显式创建跨重启哨兵，不重启服务；成功时保留数据并返回无凭据的清理清单。

    调用方须保存返回值，并最终调用 persist_cleanup。不是 run_checks 的默认步骤。
    若准备失败，只尝试清理本函数 UUID 数据；清理失败会明确反映在阶段码中。
    """
    sdk = _sdk()
    *_, datatype, milvus_class = sdk
    identifier = uuid4().hex
    manifest = {
        "schema_version": 1,
        "probe_id": identifier,
        "collection_name": f"m01_probe_persist_{identifier}",
        "object_key": f"m01_probe/{identifier}/persist.bin",
        "sha256": sha256(_SYNTHETIC).hexdigest(),
    }
    knowledge = milvus = None
    attempted = False
    with _quiet_sdks():
        try:
            knowledge = _s3(sdk, endpoint, scoped)
            knowledge.put_object(
                Bucket=KNOWLEDGE_BUCKET, Key=manifest["object_key"], Body=_SYNTHETIC
            )
            milvus = milvus_class(uri=milvus_uri, token=milvus_token, timeout=RPC_TIMEOUT)
            attempted = True
            _create_milvus(milvus, datatype, manifest["collection_name"], identifier)
            _insert_flush_index(milvus, manifest["collection_name"])
            milvus.load_collection(collection_name=manifest["collection_name"], timeout=RPC_TIMEOUT)
            _search(milvus, manifest["collection_name"])
            manifest["collection_id"] = milvus.describe_collection(
                collection_name=manifest["collection_name"], timeout=RPC_TIMEOUT
            )["collection_id"]
        except Exception:
            cleanup_failed = False
            try:
                if (
                    milvus is not None
                    and attempted
                    and milvus.has_collection(
                        collection_name=manifest["collection_name"], timeout=RPC_TIMEOUT
                    )
                ):
                    milvus.drop_collection(
                        collection_name=manifest["collection_name"], timeout=RPC_TIMEOUT
                    )
            except Exception:
                cleanup_failed = True
            try:
                if knowledge is not None:
                    knowledge.delete_object(Bucket=KNOWLEDGE_BUCKET, Key=manifest["object_key"])
            except Exception:
                cleanup_failed = True
            code = "PERSIST_PREPARE+CLEANUP_FAILED" if cleanup_failed else "PERSIST_PREPARE"
            raise ProbeFailure(code) from None
        finally:
            for client in (knowledge, milvus):
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
    return manifest


def persist_verify(
    endpoint: str, scoped: dict, milvus_uri: str, milvus_token: str, manifest: dict
) -> dict:
    """调用方完成保卷重启后，验证同一对象、同一集合 ID 与向量；不删哨兵。

    本函数不会推断发生过重启；调用方必须另行保存容器重启与卷一致性证据。
    可多次验证，以覆盖 stop/start 及 down/up，但绝不能使用 down -v。
    """
    sdk = _sdk()
    milvus_class = sdk[-1]
    results: dict[str, str] = {}
    identifier, collection, key = _step(results, "PERSIST_MANIFEST", lambda: _manifest(manifest))
    knowledge = milvus = None
    with _quiet_sdks():
        try:
            knowledge = _step(results, "PERSIST_S3_CONNECT", lambda: _s3(sdk, endpoint, scoped))

            def verify_object() -> None:
                content = _read(knowledge.get_object(Bucket=KNOWLEDGE_BUCKET, Key=key))
                _require(sha256(content).hexdigest() == manifest["sha256"])

            _step(results, "PERSIST_S3_SHA256", verify_object)
            milvus = _step(
                results,
                "PERSIST_MILVUS_CONNECT",
                lambda: milvus_class(uri=milvus_uri, token=milvus_token, timeout=RPC_TIMEOUT),
            )

            def verify_identity() -> None:
                description = milvus.describe_collection(
                    collection_name=collection, timeout=RPC_TIMEOUT
                )
                _require(
                    description["collection_id"] == manifest["collection_id"]
                    and description.get("description") == identifier
                )

            _step(results, "PERSIST_SAME_COLLECTION_ID", verify_identity)
            _step(
                results, "PERSIST_HNSW_FINISHED_2048_ROWS", lambda: _index_ready(milvus, collection)
            )
            _step(
                results,
                "PERSIST_MILVUS_LOAD",
                lambda: milvus.load_collection(collection_name=collection, timeout=RPC_TIMEOUT),
            )
            _step(results, "PERSIST_MILVUS_SEARCH_TARGET_ID", lambda: _search(milvus, collection))
        finally:
            for client in (knowledge, milvus):
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
    return results


def persist_cleanup(
    endpoint: str, scoped: dict, milvus_uri: str, milvus_token: str, manifest: dict
) -> dict:
    """显式清理 prepare 返回清单；删除集合前同时核对 UUID 描述与集合 ID。"""
    sdk = _sdk()
    results: dict[str, str] = {}
    identifier, collection, key = _step(
        results, "PERSIST_CLEANUP_MANIFEST", lambda: _manifest(manifest)
    )
    knowledge = milvus = None
    with _quiet_sdks():
        try:
            milvus = _step(
                results,
                "PERSIST_CLEANUP_MILVUS_CONNECT",
                lambda: sdk[-1](uri=milvus_uri, token=milvus_token, timeout=RPC_TIMEOUT),
            )

            def remove_collection() -> None:
                if not milvus.has_collection(collection_name=collection, timeout=RPC_TIMEOUT):
                    return
                description = milvus.describe_collection(
                    collection_name=collection, timeout=RPC_TIMEOUT
                )
                _require(
                    description["collection_id"] == manifest["collection_id"]
                    and description.get("description") == identifier
                )
                milvus.drop_collection(collection_name=collection, timeout=RPC_TIMEOUT)
                _require(not milvus.has_collection(collection_name=collection, timeout=RPC_TIMEOUT))

            _step(results, "PERSIST_CLEANUP_COLLECTION", remove_collection)
            knowledge = _step(
                results, "PERSIST_CLEANUP_S3_CONNECT", lambda: _s3(sdk, endpoint, scoped)
            )

            def remove_object() -> None:
                knowledge.delete_object(Bucket=KNOWLEDGE_BUCKET, Key=key)
                _absent(lambda: knowledge.head_object(Bucket=KNOWLEDGE_BUCKET, Key=key), sdk[3])

            _step(results, "PERSIST_CLEANUP_OBJECT", remove_object)
        finally:
            for client in (knowledge, milvus):
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
    return results
