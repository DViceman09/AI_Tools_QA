from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class SecretHygieneTests(unittest.TestCase):
    def test_api_key_file_is_gitignored(self) -> None:
        gitignore = (ROOT_DIR / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("API_KEY", gitignore)

    def test_api_key_file_is_dockerignored(self) -> None:
        dockerignore = (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("API_KEY", dockerignore)


if __name__ == "__main__":
    unittest.main()
