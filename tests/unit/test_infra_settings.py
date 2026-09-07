"""M01 environment-layer validation; no credentials or network access."""

from __future__ import annotations
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import infra_settings as settings  # noqa: E402


class InfraSettingsTests(unittest.TestCase):
    def test_all_profiles(self):
        for name in settings.ENVIRONMENTS:
            with self.subTest(name=name):
                self.assertEqual(settings.load(name)["environment"], name)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(settings.SettingsError):
            settings.validate({}, "other")

    def test_plaintext_secret_key_rejected(self):
        profile = settings.load("dev")
        profile["password"] = "synthetic"
        with self.assertRaises(settings.SettingsError):
            settings.validate(profile, "dev")

    def test_dev_non_loopback_rejected(self):
        profile = copy.deepcopy(settings.load("dev"))
        profile["hosts"]["mysql"] = "0.0.0.0"
        with self.assertRaises(settings.SettingsError):
            settings.validate(profile, "dev")

    def test_prod_without_tls_rejected(self):
        profile = copy.deepcopy(settings.load("prod"))
        profile["tls_required"] = False
        with self.assertRaises(settings.SettingsError):
            settings.validate(profile, "prod")

    def test_environment_mismatch_rejected(self):
        with self.assertRaises(settings.SettingsError):
            settings.validate(settings.load("test"), "prod")

    def test_invalid_port_rejected(self):
        profile = copy.deepcopy(settings.load("test"))
        profile["ports"]["s3"] = 0
        with self.assertRaises(settings.SettingsError):
            settings.validate(profile, "test")


if __name__ == "__main__":
    unittest.main()
