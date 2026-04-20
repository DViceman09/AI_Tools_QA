from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bug_triage.config import ROOT_DIR, get_settings


class SettingsTests(unittest.TestCase):
    def _make_temp_key_file(self, file_name: str, value: str) -> Path:
        temp_dir = ROOT_DIR / ".tmp" / "config_tests" / self._testMethodName
        temp_dir.mkdir(parents=True, exist_ok=True)
        key_file = temp_dir / file_name
        key_file.write_text(value, encoding="utf-8")
        return key_file

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_uses_local_defaults_without_railway_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY_FILE": str(ROOT_DIR / ".tmp" / "missing_api_key"),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.database_path, ROOT_DIR / "data" / "bug_triage.db")
        self.assertEqual(settings.generated_tests_dir, ROOT_DIR / "generated_tests")
        self.assertEqual(settings.artifact_storage_dir, ROOT_DIR / "artifacts")
        self.assertTrue(settings.seed_demo_data)
        self.assertIsNone(settings.openai_api_key)

    def test_uses_attached_railway_volume_for_runtime_storage(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY_FILE": str(ROOT_DIR / ".tmp" / "missing_api_key"),
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
                "OPENAI_API_KEY_FILE": str(ROOT_DIR / ".tmp" / "missing_api_key"),
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
                "OPENAI_API_KEY_FILE": str(ROOT_DIR / ".tmp" / "missing_api_key"),
                "RAILWAY_ENVIRONMENT_ID": "env_123",
                "BUG_TRIAGE_SEED": "true",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertTrue(settings.seed_demo_data)

    def test_reads_openai_api_key_from_configured_file(self) -> None:
        key_file = self._make_temp_key_file("API_KEY", "test-file-key\n")

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY_FILE": str(key_file),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "test-file-key")

    def test_environment_openai_key_overrides_file(self) -> None:
        key_file = self._make_temp_key_file("API_KEY", "file-key")

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "env-key",
                "OPENAI_API_KEY_FILE": str(key_file),
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "env-key")


if __name__ == "__main__":
    unittest.main()
