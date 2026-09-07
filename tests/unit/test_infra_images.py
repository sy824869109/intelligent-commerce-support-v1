"""M01 immutable image-lock tests; Docker is never contacted."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import infra_images  # noqa: E402


class InfraImageTests(unittest.TestCase):
    def test_repository_lock_has_exact_scope(self):
        self.assertEqual(set(infra_images.ORDER), set(infra_images.lock()))

    def test_invalid_lock_scope_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy/compose").mkdir(parents=True)
            (root / "deploy/compose/images.lock.json").write_text(
                json.dumps({"schema_version": 2, "images": {"mysql": "x@y"}}),
                encoding="utf-8",
            )
            with patch.object(infra_images, "ROOT", root), self.assertRaises(ValueError):
                infra_images.lock()

    def test_verify_requires_exact_image_ids(self):
        images = {name: f"ics-{name}:test@sha256:{name}" for name in infra_images.ORDER}
        with patch.object(infra_images, "run", side_effect=lambda args: args[3].split("@", 1)[1]):
            infra_images.verify(images)

    def test_verify_rejects_digest_mismatch(self):
        images = {name: f"ics-{name}:test@sha256:{name}" for name in infra_images.ORDER}
        with patch.object(infra_images, "run", return_value="sha256:wrong"):
            with self.assertRaises(RuntimeError):
                infra_images.verify(images)


if __name__ == "__main__":
    unittest.main()
