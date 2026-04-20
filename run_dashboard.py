from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

for candidate in (ROOT_DIR / ".deps", ROOT_DIR / "src"):
    candidate_path = str(candidate)
    if candidate.exists() and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

import uvicorn


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    uvicorn.run(
        "bug_triage.app:create_app",
        factory=True,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=_env_flag("BUG_TRIAGE_RELOAD", default=False),
    )
