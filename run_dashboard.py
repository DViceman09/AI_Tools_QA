from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

for candidate in (ROOT_DIR / ".deps", ROOT_DIR / "src"):
    candidate_path = str(candidate)
    if candidate.exists() and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

import uvicorn


if __name__ == "__main__":
    uvicorn.run("bug_triage.app:create_app", factory=True, reload=True)

