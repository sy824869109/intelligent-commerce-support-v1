"""Offline source-extraction guards; no network, model, compiler or Docker execution."""

import importlib
from io import BytesIO
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
builder = importlib.import_module("prepare_environment_source")


class SourceExtractionTests(unittest.TestCase):
    def fixture(self, folder, name, kind=tarfile.REGTYPE):
        archive = folder / "source.tar"
        with tarfile.open(archive, "w") as bundle:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = 4
                bundle.addfile(member, BytesIO(b"test"))
            else:
                member.linkname = "../../outside"
                bundle.addfile(member)
        return archive

    def test_valid_source_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = self.fixture(folder, "source/pkg/main.go")
            self.assertEqual(builder.extract_source(archive, folder / "source"), [])
            self.assertEqual((folder / "source/pkg/main.go").read_bytes(), b"test")

    def test_traversal_and_alternate_windows_paths_rejected(self):
        for name in (
            "other/main.go",
            "source/../outside",
            "/source/x",
            "source/C:/x",
            "source/a\\x",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                archive = self.fixture(folder, name)
                with self.assertRaises(ValueError):
                    builder.extract_source(archive, folder / "source")

    def test_links_are_recorded_never_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = self.fixture(folder, "source/link", tarfile.SYMTYPE)
            self.assertEqual(builder.extract_source(archive, folder / "source"), ["source/link"])
            self.assertFalse((folder / "source/link").exists())

    def test_special_files_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = self.fixture(folder, "source/device", tarfile.CHRTYPE)
            with self.assertRaises(ValueError):
                builder.extract_source(archive, folder / "source")

    def test_collector_components_cover_all_configured_pipelines(self):
        import yaml

        root = Path(__file__).resolve().parents[2] / "deploy/dev-environment"
        manifest = yaml.safe_load((root / "security/collector-builder.yaml").read_text())
        config = yaml.safe_load((root / "observability/otel.yaml").read_text())
        modules = [
            entry["gomod"].split()[0].rsplit("/", 1)[-1]
            for kind in ("receivers", "processors", "exporters", "extensions")
            for entry in manifest[kind]
        ]
        expected = {
            "otlpreceiver",
            "memorylimiterprocessor",
            "batchprocessor",
            "otlpexporter",
            "otlphttpexporter",
            "prometheusexporter",
            "healthcheckextension",
        }
        self.assertEqual(set(modules), expected)
        self.assertEqual(set(config["service"]["pipelines"]), {"metrics", "logs", "traces"})


if __name__ == "__main__":
    unittest.main()
