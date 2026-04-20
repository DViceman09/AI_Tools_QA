from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bug_triage.config import ROOT_DIR, get_settings


class SettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_uses_local_defaults_without_railway_variables(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.database_path, ROOT_DIR / "data" / "bug_triage.db")
        self.assertEqual(settings.generated_tests_dir, ROOT_DIR / "generated_tests")
        self.assertEqual(settings.artifact_storage_dir, ROOT_DIR / "artifacts")
        self.assertTrue(settings.seed_demo_data)

    def test_uses_attached_railway_volume_for_runtime_storage(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RAILWAY_VOLUME_MOUNT_PATH": "/data",
                "RAILWAY_ENVIRONMENT_ID": "env_123",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        volume_root = Path("/data")
        self.assertEqual(settings.database_path, volume_root / "bug_triage.db")
        self.assertEqual(settings.generated_tests_dir, volume_root / "generated_tests")
        self.assertEqual(settings.artifact_storage_dir, volume_root / "artifacts")
        self.assertFalse(settings.seed_demo_data)

    def test_explicit_storage_root_overrides_railway_volume_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BUG_TRIAGE_STORAGE_ROOT": "/persist",
                "RAILWAY_VOLUME_MOUNT_PATH": "/data",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        storage_root = Path("/persist")
        self.assertEqual(settings.database_path, storage_root / "bug_triage.db")
        self.assertEqual(settings.generated_tests_dir, storage_root / "generated_tests")
        self.assertEqual(settings.artifact_storage_dir, storage_root / "artifacts")

    def test_explicit_seed_value_overrides_railway_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RAILWAY_ENVIRONMENT_ID": "env_123",
                "BUG_TRIAGE_SEED": "true",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertTrue(settings.seed_demo_data)


if __name__ == "__main__":
    unittest.main()
