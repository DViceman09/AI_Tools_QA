from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bug_triage.models import TestCandidate
from bug_triage.repository import BugRepository
from bug_triage.services.seed import seed_demo_data
from bug_triage.services.testgen import TestGenerationService
from bug_triage.services.testplan import IntelligentTestDesignService
from bug_triage.services.triage import TriageService


class DemoSeedServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = (
            Path.home()
            / ".codex"
            / "memories"
            / "bug_triage_seed_tests"
            / self._testMethodName
        )
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.generated_tests_dir = self.temp_root / "generated_tests"
        self.artifacts_dir = self.temp_root / "artifacts"
        self.generated_tests_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.repository = BugRepository(self.temp_root / "bug_triage.db")
        self.repository.initialize()

    def test_seed_replaces_legacy_product_examples_with_game_showcase_data(self) -> None:
        legacy_bug = self.repository.create_bug(
            source="github",
            external_id="GH-142",
            game_title="Unknown Game",
            platform="pc",
            engine=None,
            build_number=None,
            title="Checkout throws 500 when promo code expires during payment",
            description="Legacy product example that should be removed from the game dashboard.",
            environment="prod",
            version="1.0",
            stack_trace=None,
            metadata={"legacy_demo": True},
        )
        legacy_test_path = self.generated_tests_dir / "test_bug_1_checkout_throws_500_when_promo_code_expi.py"
        legacy_test_path.write_text("# legacy file", encoding="utf-8")
        self.repository.save_test_candidate(
            TestCandidate(
                id=None,
                bug_id=legacy_bug.id or 0,
                test_type="api-regression",
                file_path=str(legacy_test_path),
                framework="Pytest",
                generated_code="# legacy file",
                status="generated",
                execution_summary="Legacy seed file",
            )
        )

        triage_service = TriageService()
        test_generation_service = TestGenerationService(self.generated_tests_dir)
        test_design_service = IntelligentTestDesignService(self.artifacts_dir)

        seed_demo_data(
            self.repository,
            triage_service,
            test_generation_service,
            test_design_service,
        )

        bugs = self.repository.list_bugs()
        titles = {bug.title for bug in bugs}
        external_ids = {bug.external_id for bug in bugs}

        self.assertNotIn(
            "Checkout throws 500 when promo code expires during payment",
            titles,
        )
        self.assertTrue({"GAME-142", "GAME-201", "SEN-311", "GAME-417"}.issubset(external_ids))
        self.assertTrue(all(bug.game_title != "Unknown Game" for bug in bugs))
        self.assertFalse(legacy_test_path.exists())

        bug_by_external_id = {bug.external_id: bug for bug in bugs}

        self.assertIsNotNone(
            self.repository.get_latest_triage_for_bug(bug_by_external_id["GAME-142"].id or 0)
        )
        self.assertGreater(
            len(self.repository.list_test_candidates_for_bug(bug_by_external_id["GAME-201"].id or 0)),
            0,
        )
        self.assertIsNone(
            self.repository.get_latest_triage_for_bug(bug_by_external_id["SEN-311"].id or 0)
        )
        self.assertIsNotNone(
            self.repository.get_latest_test_plan_for_bug(bug_by_external_id["GAME-417"].id or 0)
        )
        self.assertGreater(
            len(
                self.repository.list_test_design_artifacts_for_bug(
                    bug_by_external_id["GAME-417"].id or 0
                )
            ),
            0,
        )

        bug_count_after_first_seed = self.repository.count_bugs()
        seed_demo_data(
            self.repository,
            triage_service,
            test_generation_service,
            test_design_service,
        )
        self.assertEqual(self.repository.count_bugs(), bug_count_after_first_seed)


if __name__ == "__main__":
    unittest.main()
