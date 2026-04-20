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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_path = Path(os.getenv("BUG_TRIAGE_DB_PATH", ROOT_DIR / "data" / "bug_triage.db"))
    generated_tests_dir = Path(
        os.getenv("BUG_TRIAGE_GENERATED_TESTS_DIR", ROOT_DIR / "generated_tests")
    )
    artifact_storage_dir = Path(
        os.getenv("BUG_TRIAGE_ARTIFACTS_DIR", ROOT_DIR / "artifacts")
    )
    return Settings(
        database_path=database_path,
        generated_tests_dir=generated_tests_dir,
        artifact_storage_dir=artifact_storage_dir,
        seed_demo_data=os.getenv("BUG_TRIAGE_SEED", "true").lower() == "true",
        ai_mode=os.getenv("BUG_TRIAGE_AI_MODE", "auto"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_triage_model=os.getenv("OPENAI_TRIAGE_MODEL", "gpt-5-mini"),
        openai_testgen_model=os.getenv("OPENAI_TESTGEN_MODEL", "gpt-5.2"),
    )
