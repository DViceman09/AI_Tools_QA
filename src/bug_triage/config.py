from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Game Bug Triage"
    database_path: Path = ROOT_DIR / "data" / "bug_triage.db"
    generated_tests_dir: Path = ROOT_DIR / "generated_tests"
    artifact_storage_dir: Path = ROOT_DIR / "artifacts"
    seed_demo_data: bool = True
    ai_mode: str = "auto"
    openai_api_key: str | None = None
    openai_triage_model: str = "gpt-5-mini"
    openai_testgen_model: str = "gpt-5.2"


def _resolve_secret_file_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate
    return ROOT_DIR / candidate


def _read_secret_file(path: Path) -> str | None:
    if not path.is_file():
        return None

    raw_value = path.read_text(encoding="utf-8").strip()
    return raw_value or None


def _resolve_storage_defaults() -> tuple[Path, Path, Path]:
    storage_root = os.getenv("BUG_TRIAGE_STORAGE_ROOT")
    if storage_root:
        base_path = Path(storage_root).expanduser()
        return (
            base_path / "bug_triage.db",
            base_path / "generated_tests",
            base_path / "artifacts",
        )

    railway_volume_mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume_mount_path:
        base_path = Path(railway_volume_mount_path)
        return (
            base_path / "bug_triage.db",
            base_path / "generated_tests",
            base_path / "artifacts",
        )

    return (
        ROOT_DIR / "data" / "bug_triage.db",
        ROOT_DIR / "generated_tests",
        ROOT_DIR / "artifacts",
    )


def _resolve_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return Path(raw_value).expanduser()


def _resolve_seed_demo_data() -> bool:
    raw_value = os.getenv("BUG_TRIAGE_SEED")
    if raw_value is not None:
        return raw_value.strip().lower() == "true"

    if os.getenv("RAILWAY_ENVIRONMENT_ID"):
        return False

    return True


def _resolve_openai_api_key() -> str | None:
    raw_value = os.getenv("OPENAI_API_KEY")
    if raw_value is not None and raw_value.strip():
        return raw_value.strip()

    secret_file_path = _resolve_secret_file_path(
        "OPENAI_API_KEY_FILE",
        ROOT_DIR / "API_KEY",
    )
    return _read_secret_file(secret_file_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_database_path, default_generated_tests_dir, default_artifact_storage_dir = (
        _resolve_storage_defaults()
    )
    return Settings(
        database_path=_resolve_path("BUG_TRIAGE_DB_PATH", default_database_path),
        generated_tests_dir=_resolve_path(
            "BUG_TRIAGE_GENERATED_TESTS_DIR",
            default_generated_tests_dir,
        ),
        artifact_storage_dir=_resolve_path(
            "BUG_TRIAGE_ARTIFACTS_DIR",
            default_artifact_storage_dir,
        ),
        seed_demo_data=_resolve_seed_demo_data(),
        ai_mode=os.getenv("BUG_TRIAGE_AI_MODE", "auto"),
        openai_api_key=_resolve_openai_api_key(),
        openai_triage_model=os.getenv("OPENAI_TRIAGE_MODEL", "gpt-5-mini"),
        openai_testgen_model=os.getenv("OPENAI_TESTGEN_MODEL", "gpt-5.2"),
    )
