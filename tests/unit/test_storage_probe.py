"""S3/Milvus 探针的离线契约测试；不依赖 SDK、Docker、网络或真实凭据。

Fake 验证探针自身不会把错误、空索引、跨桶访问或清理失败记作 PASS；
本文件通过不代表真实存储兼容测试通过，运行验收必须调用实际 SDK 探针。
"""

from __future__ import annotations

from enum import Enum
import importlib
import io
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import storage_probe as probe  # noqa: E402


class FakeClientError(Exception):
    def __init__(self, status=403, code="AccessDenied"):
        super().__init__("synthetic request details must remain private")
        self.response = {
            "ResponseMetadata": {"HTTPStatusCode": status},
            "Error": {"Code": code},
        }


class FakeStatus(Enum):
    UNAUTHENTICATED = 16
    PERMISSION_DENIED = 7
    UNAVAILABLE = 14
    DEADLINE_EXCEEDED = 4


class FakeRpcError(Exception):
    def __init__(self, status):
        super().__init__("synthetic transport details must remain private")
        self.status = status

    def code(self):
        return self.status


class FakeEvents:
    def __init__(self):
        self.hooks = {}

    def register(self, event, callback, unique_id):
        self.hooks[event, unique_id] = callback

    def unregister(self, event, unique_id):
        self.hooks.pop((event, unique_id))


class FakeState:
    def __init__(self):
        self.objects = {}
        self.metadata = {}
        self.tags = {}
        self.uploads = {}
        self.collections = {}
        self.clients = []
        self.close_count = 0
        self.serial = 0
        self.requests = []
        self.deleted = []
        self.fail_search = False
        self.fail_delete = False
        self.allow_cross_copy = False
        self.rewrite_image = False
        self.tag_basename_collision = False
        self.emit_index = True
        self.index_rows = probe._ROW_COUNT
        self.index_state = "Finished"
        self.reject_status = FakeStatus.UNAUTHENTICATED

    def s3(self, sdk, endpoint, credentials):
        if credentials == ADMIN:
            role = "admin"
        elif credentials == SCOPED:
            role = "knowledge"
        else:
            role = "unauthorized"
        client = FakeS3(self, role)
        self.clients.append(client)
        return client

    def milvus(self, **kwargs):
        return FakeMilvus(self, kwargs.get("token"))


class FakeS3:
    def __init__(self, state, role):
        self.state = state
        self.role = role
        self.meta = SimpleNamespace(events=FakeEvents())

    def guard(self, bucket):
        if self.role == "unauthorized" or (self.role != "admin" and bucket == probe.MILVUS_BUCKET):
            raise FakeClientError()

    def head_bucket(self, Bucket):
        self.guard(Bucket)

    def put_object(self, Bucket, Key, Body, Metadata=None, **kwargs):
        self.guard(Bucket)
        self.state.objects[Bucket, Key] = Body
        self.state.metadata[Bucket, Key] = Metadata or {}
        return {}

    def get_object(self, Bucket, Key, Range=None):
        self.guard(Bucket)
        if (Bucket, Key) not in self.state.objects:
            raise FakeClientError(404, "NoSuchKey")
        request = SimpleNamespace(url=f"http://synthetic.invalid/{Bucket}/{Key}")
        for callback in self.meta.events.hooks.values():
            callback(request=request)
        self.state.requests.append(request.url)
        body = self.state.objects[Bucket, Key]
        if "width=" in request.url and self.state.rewrite_image:
            body = b"unexpected image transformation"
        if Range:
            return {
                "Body": io.BytesIO(body[3:14]),
                "ContentRange": f"bytes 3-13/{len(body)}",
                "ResponseMetadata": {"HTTPStatusCode": 206},
            }
        return {"Body": io.BytesIO(body)}

    def head_object(self, Bucket, Key):
        self.guard(Bucket)
        if (Bucket, Key) not in self.state.objects:
            raise FakeClientError(404, "NoSuchKey")
        return {
            "ContentLength": len(self.state.objects[Bucket, Key]),
            "Metadata": self.state.metadata.get((Bucket, Key), {}),
        }

    def delete_object(self, Bucket, Key):
        self.guard(Bucket)
        if self.state.fail_delete:
            raise FakeClientError(500, "InternalError")
        self.state.deleted.append((Bucket, Key))
        self.state.objects.pop((Bucket, Key), None)
        self.state.tags.pop((Bucket, Key), None)

    def list_objects_v2(self, Bucket, Prefix="", MaxKeys=1000, ContinuationToken=None):
        self.guard(Bucket)
        keys = sorted(
            key for bucket, key in self.state.objects if bucket == Bucket and key.startswith(Prefix)
        )
        offset = int(ContinuationToken or 0)
        selected = keys[offset : offset + MaxKeys]
        page = {
            "Contents": [
                {"Key": key, "Size": len(self.state.objects[Bucket, key])} for key in selected
            ],
            "IsTruncated": offset + MaxKeys < len(keys),
        }
        if page["IsTruncated"]:
            page["NextContinuationToken"] = str(offset + MaxKeys)
        return page

    def put_object_tagging(self, Bucket, Key, Tagging):
        self.guard(Bucket)
        actual_key = Key.split("/")[-1] if self.state.tag_basename_collision else Key
        self.state.tags[Bucket, actual_key] = Tagging["TagSet"]

    def get_object_tagging(self, Bucket, Key):
        self.guard(Bucket)
        actual_key = Key.split("/")[-1] if self.state.tag_basename_collision else Key
        return {"TagSet": self.state.tags[Bucket, actual_key]}

    def copy_object(self, Bucket, Key, CopySource):
        self.guard(Bucket)
        if not self.state.allow_cross_copy:
            self.guard(CopySource["Bucket"])
        self.state.objects[Bucket, Key] = self.state.objects[
            CopySource["Bucket"], CopySource["Key"]
        ]
        return {}

    def create_multipart_upload(self, Bucket, Key):
        self.guard(Bucket)
        identifier = probe.uuid4().hex
        self.state.uploads[identifier] = {}
        return {"UploadId": identifier}

    def upload_part(self, Bucket, Key, UploadId, PartNumber, Body):
        self.guard(Bucket)
        self.state.uploads[UploadId][PartNumber] = Body
        return {"ETag": str(PartNumber)}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        self.guard(Bucket)
        self.state.objects[Bucket, Key] = b"".join(
            self.state.uploads[UploadId][part["PartNumber"]] for part in MultipartUpload["Parts"]
        )
        self.state.uploads.pop(UploadId)

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.guard(Bucket)
        self.state.uploads.pop(UploadId, None)

    def list_parts(self, Bucket, Key, UploadId):
        self.guard(Bucket)
        if UploadId not in self.state.uploads:
            raise FakeClientError(404, "NoSuchUpload")
        return {}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket):
        return [self.list_objects_v2(Bucket)]

    def close(self):
        self.state.close_count += 1


class FakeSchema:
    def __init__(self, **kwargs):
        self.description = kwargs["description"]
        self.fields = []

    def add_field(self, **kwargs):
        self.fields.append(kwargs)


class FakeIndex:
    def __init__(self):
        self.options = None

    def add_index(self, **kwargs):
        self.options = kwargs


class FakeMilvus:
    def __init__(self, state, token):
        self.state = state
        self.token = token

    def list_collections(self, **kwargs):
        if self.token != MILVUS_TOKEN:
            raise FakeRpcError(self.state.reject_status)
        return list(self.state.collections)

    def create_schema(self, **kwargs):
        return FakeSchema(**kwargs)

    def create_collection(self, collection_name, schema, **kwargs):
        self.state.serial += 1
        self.state.collections[collection_name] = {
            "collection_id": self.state.serial + 50000,
            "description": schema.description,
            "schema": schema.fields,
            "segment_id": self.state.serial + 70000,
            "rows": [],
        }

    def insert(self, collection_name, data, **kwargs):
        self.state.collections[collection_name]["rows"] = data
        return {"insert_count": len(data)}

    def flush(self, collection_name, **kwargs):
        collection = self.state.collections[collection_name]
        cid, sid = collection["collection_id"], collection["segment_id"]
        self.state.objects[probe.MILVUS_BUCKET, f"v1/insert_log/{cid}/60001/{sid}/101/80001"] = (
            b"synthetic data log"
        )

    def prepare_index_params(self):
        return FakeIndex()

    def create_index(self, collection_name, index_params, **kwargs):
        collection = self.state.collections[collection_name]
        collection["index"] = index_params.options
        if self.state.emit_index:
            sid = collection["segment_id"]
            self.state.objects[probe.MILVUS_BUCKET, f"v1/index_log/90001/1/60001/{sid}/index"] = (
                b"synthetic hnsw index"
            )

    def describe_index(self, collection_name, **kwargs):
        collection = self.state.collections[collection_name]
        return dict(
            collection["index"],
            state=self.state.index_state,
            indexed_rows=self.state.index_rows,
            total_rows=len(collection["rows"]),
            pending_index_rows=0,
        )

    def load_collection(self, **kwargs):
        pass

    def release_collection(self, **kwargs):
        pass

    def search(self, collection_name, **kwargs):
        if self.state.fail_search:
            return [[{"id": 102, "distance": 1.0}]]
        return [[{"id": 101, "distance": 0.0}]]

    def describe_collection(self, collection_name, **kwargs):
        return self.state.collections[collection_name]

    def has_collection(self, collection_name, **kwargs):
        return collection_name in self.state.collections

    def drop_collection(self, collection_name, **kwargs):
        self.state.collections.pop(collection_name)

    def close(self):
        self.state.close_count += 1


ADMIN = {"access_key": "synthetic-admin", "secret_key": "synthetic-admin-secret"}
SCOPED = {"access_key": "synthetic-knowledge", "secret_key": "synthetic-knowledge-secret"}
MILVUS_TOKEN = "root:synthetic-valid"


class ProbeHelperTests(unittest.TestCase):
    def test_module_import_without_runtime_sdks(self):
        with patch.dict(sys.modules, {"boto3": None, "pymilvus": None, "botocore": None}):
            importlib.reload(probe)
            with self.assertRaisesRegex(probe.ProbeFailure, "^SDK_IMPORT$"):
                probe._sdk()

    def test_safe_error_stage_hides_underlying_exception(self):
        def fail():
            raise ValueError("synthetic secret/payload")

        with self.assertRaises(probe.ProbeFailure) as captured:
            probe._step({}, "PUBLIC_STAGE", fail)
        self.assertEqual("PUBLIC_STAGE", str(captured.exception))
        self.assertTrue(captured.exception.__suppress_context__)

    def test_not_found_is_not_authorization_denial(self):
        def fail():
            raise FakeClientError(404, "NoSuchKey")

        with self.assertRaises(probe.ProbeFailure):
            probe._denied(fail, FakeClientError)

    def test_access_denied_requires_matching_status_and_code(self):
        for status, code in ((500, "AccessDenied"), (403, "InternalError")):
            with self.subTest(status=status, code=code):

                def fail():
                    raise FakeClientError(status, code)

                with self.assertRaises(probe.ProbeFailure):
                    probe._denied(fail, FakeClientError)

    def test_milvus_denial_rejects_network_and_timeout(self):
        for status in (FakeStatus.UNAVAILABLE, FakeStatus.DEADLINE_EXCEEDED):
            with self.subTest(status=status):

                def fail(**kwargs):
                    raise FakeRpcError(status)

                with self.assertRaises(probe.ProbeFailure):
                    probe._milvus_denied(fail, "synthetic", "")

    def test_milvus_constructor_permission_failure_is_valid(self):
        def fail(**kwargs):
            raise FakeRpcError(FakeStatus.UNAUTHENTICATED)

        probe._milvus_denied(fail, "synthetic", "")

    def test_milvus_nested_sdk_cause_keeps_permission_classification(self):
        def fail(**kwargs):
            try:
                raise FakeRpcError(FakeStatus.PERMISSION_DENIED)
            except FakeRpcError as original:
                raise RuntimeError("SDK wrapper") from original

        probe._milvus_denied(fail, "synthetic", "")

    def test_milvus_self_cause_does_not_loop_or_pass(self):
        def fail(**kwargs):
            original = RuntimeError("SDK self cause")
            raise original from original

        with self.assertRaises(probe.ProbeFailure):
            probe._milvus_denied(fail, "synthetic", "")

    def test_manifest_refuses_nonprobe_target(self):
        with self.assertRaises(probe.ProbeFailure):
            probe._manifest({"schema_version": 1, "probe_id": "../business"})

    def test_synthetic_image_has_valid_crc_and_small_dimensions(self):
        png = probe._small_png()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", png[:8])
        position = 8
        while position < len(png):
            size = struct.unpack(">I", png[position : position + 4])[0]
            kind = png[position + 4 : position + 8]
            body = png[position + 8 : position + 8 + size]
            crc = struct.unpack(">I", png[position + 8 + size : position + 12 + size])[0]
            self.assertEqual(crc, zlib.crc32(kind + body))
            if kind == b"IHDR":
                self.assertEqual((2, 2), struct.unpack(">II", body[:8]))
            if kind == b"IDAT":
                self.assertEqual(14, len(zlib.decompress(body)))
            position += 12 + size
        self.assertEqual(len(png), position)


class ProbeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state = FakeState()
        datatype = SimpleNamespace(INT64=5, FLOAT_VECTOR=101)
        self.sdk_patch = patch.object(
            probe,
            "_sdk",
            return_value=(None, None, None, FakeClientError, datatype, self.state.milvus),
        )
        self.s3_patch = patch.object(probe, "_s3", side_effect=self.state.s3)
        self.sleep_patch = patch.object(probe.time, "sleep")
        self.sdk_patch.start()
        self.s3_patch.start()
        self.sleep_patch.start()
        self.addCleanup(self.sdk_patch.stop)
        self.addCleanup(self.s3_patch.stop)
        self.addCleanup(self.sleep_patch.stop)

    def run_probe(self):
        return probe.run_checks("synthetic", ADMIN, SCOPED, "synthetic", MILVUS_TOKEN)

    def assert_owned_cleanup(self):
        self.assertFalse(self.state.collections)
        self.assertFalse(self.state.uploads)
        self.assertFalse(any(key.startswith("m01_probe/") for _, key in self.state.objects))
        self.assertTrue(all(key.startswith("m01_probe/") for _, key in self.state.deleted))
        self.assertTrue(all(not client.meta.events.hooks for client in self.state.clients))

    def test_all_contract_stages_and_precise_cleanup(self):
        unrelated = (probe.KNOWLEDGE_BUCKET, "business/not-owned.bin")
        self.state.objects[unrelated] = b"must remain untouched"
        results = self.run_probe()
        self.assertTrue(all(value == "PASS" for value in results.values()))
        self.assertIn("MILVUS_HNSW_FINISHED_2048_ROWS", results)
        self.assertIn("MILVUS_S3_DATA_AND_INDEX_OBJECTS", results)
        self.assertIn("S3_CROSS_BUCKET_COPY_SOURCE_DENIED", results)
        self.assertIn("S3_NESTED_SAME_BASENAME_TAGGING_ISOLATION", results)
        self.assert_owned_cleanup()
        self.assertEqual(b"must remain untouched", self.state.objects[unrelated])
        self.assertTrue(any("/index_log/" in key for _, key in self.state.objects))
        dimensions = [
            parse_qs(urlsplit(url).query) for url in self.state.requests if "width=" in url
        ]
        self.assertEqual([{"width": ["1"], "height": ["1"]}], dimensions)

    def test_failed_search_still_cleans_only_owned_data(self):
        self.state.fail_search = True
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_SEARCH_TARGET_ID$"):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_cleanup_failure_prevents_success(self):
        self.state.fail_delete = True
        with self.assertRaises(probe.ProbeFailure) as captured:
            self.run_probe()
        self.assertIn("CLEANUP_FAILED", str(captured.exception))

    def test_milvus_data_without_index_objects_cannot_pass(self):
        self.state.emit_index = False
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_S3_DATA_AND_INDEX_OBJECTS$"):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_unrelated_collection_index_does_not_satisfy_probe(self):
        self.state.emit_index = False
        self.state.objects[probe.MILVUS_BUCKET, "v1/index_log/90000/1/60000/99999/index"] = (
            b"unrelated"
        )
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_S3_DATA_AND_INDEX_OBJECTS$"):
            self.run_probe()

    def test_partially_indexed_rows_cannot_pass(self):
        self.state.index_rows = 3
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_INSERT_FLUSH_INDEX$"):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_failed_index_state_cannot_pass(self):
        self.state.index_state = "Failed"
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_INSERT_FLUSH_INDEX$"):
            self.run_probe()

    def test_milvus_unavailable_does_not_count_as_anonymous_denial(self):
        self.state.reject_status = FakeStatus.UNAVAILABLE
        with self.assertRaisesRegex(probe.ProbeFailure, "^MILVUS_ANONYMOUS_DENIED$"):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_cross_source_authorization_bypass_detected_and_cleaned(self):
        self.state.allow_cross_copy = True
        with self.assertRaisesRegex(probe.ProbeFailure, "^S3_CROSS_BUCKET_COPY_SOURCE_DENIED$"):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_nested_basename_tag_collision_detected(self):
        self.state.tag_basename_collision = True
        with self.assertRaisesRegex(
            probe.ProbeFailure, "^S3_NESTED_SAME_BASENAME_TAGGING_ISOLATION$"
        ):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_image_transformation_detected_and_hook_removed(self):
        self.state.rewrite_image = True
        with self.assertRaisesRegex(
            probe.ProbeFailure, "^S3_IMAGE_DIMENSIONS_RETURN_ORIGINAL_BYTES$"
        ):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_persistence_uses_same_id_full_index_and_explicit_cleanup(self):
        manifest = probe.persist_prepare("synthetic", SCOPED, "synthetic", MILVUS_TOKEN)
        collection = self.state.collections[manifest["collection_name"]]
        self.assertEqual(2048, len(collection["rows"]))
        self.assertEqual(2048, len({row["id"] for row in collection["rows"]}))
        self.assertEqual("HNSW", collection["index"]["index_type"])
        self.assertEqual(manifest["probe_id"], collection["description"])
        for _ in range(2):
            result = probe.persist_verify("synthetic", SCOPED, "synthetic", MILVUS_TOKEN, manifest)
            self.assertTrue(all(value == "PASS" for value in result.values()))
        probe.persist_cleanup("synthetic", SCOPED, "synthetic", MILVUS_TOKEN, manifest)
        self.assert_owned_cleanup()

    def test_persist_cleanup_refuses_different_collection_identity(self):
        manifest = probe.persist_prepare("synthetic", SCOPED, "synthetic", MILVUS_TOKEN)
        self.state.collections[manifest["collection_name"]]["collection_id"] += 1
        with self.assertRaisesRegex(probe.ProbeFailure, "^PERSIST_CLEANUP_COLLECTION$"):
            probe.persist_cleanup("synthetic", SCOPED, "synthetic", MILVUS_TOKEN, manifest)
        self.assertIn(manifest["collection_name"], self.state.collections)


if __name__ == "__main__":
    unittest.main()
