from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_dashboard_template_uses_path_only_static_asset_urls(self) -> None:
        template = (ROOT_DIR / "src" / "bug_triage" / "templates" / "dashboard.html").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "request.app.url_path_for('static', path='styles.css')",
            template,
        )
        self.assertIn(
            "request.app.url_path_for('static', path='app.js')",
            template,
        )
        self.assertNotIn("request.url_for('static'", template)

    def test_dockerfile_trusts_forwarded_headers(self) -> None:
        dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FORWARDED_ALLOW_IPS=*", dockerfile)
        self.assertIn("--proxy-headers", dockerfile)


if __name__ == "__main__":
    unittest.main()
