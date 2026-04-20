from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bug_triage.models import BugRecord, GeneratedTestPlan, TestDesignArtifact, TriageRecommendation
from bug_triage.schemas import IntelligentTestPlanRequest, TestDesignArtifactInput
from bug_triage.services.testplan import IntelligentTestDesignService


class FakeLLMClient:
    enabled = True
    mode_label = "openai (fake)"

    def generate_intelligent_test_plan(
        self,
        *,
        bug: BugRecord,
        triage: TriageRecommendation | None,
        request: IntelligentTestPlanRequest,
        artifacts: list[TestDesignArtifact],
    ) -> GeneratedTestPlan:
        return GeneratedTestPlan(
            id=None,
            bug_id=bug.id or 0,
            feature_goal=request.feature_goal,
            design_notes=request.design_notes,
            summary="LLM grouped plan",
            assumptions=["assumption 1", "assumption 2"],
            suites=[
                {
                    "suite_category": "Smoke",
                    "suite_name": "Smoke suite",
                    "purpose": "LLM purpose",
                    "coverage_focus": ["console", "platform"],
                    "test_cases": [],
                }
            ],
            risks_not_covered=["risk 1", "risk 2"],
            suggested_execution_order=["Smoke", "Sanity", "Regression", "Functional", "Non-functional"],
        )


class IntelligentTestDesignServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_dir = Path(__file__).resolve().parents[1] / ".tmp_testplan" / self._testMethodName
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def test_ingest_artifacts_stores_text_and_image_inputs(self) -> None:
        service = IntelligentTestDesignService(self.output_dir)
        image_payload = "data:image/png;base64," + base64.b64encode(b"fake-image").decode("ascii")
        artifacts = service.ingest_artifacts(
            bug_id=77,
            artifacts=[
                TestDesignArtifactInput(
                    name="feature_notes.md",
                    artifact_kind="text",
                    mime_type="text/markdown",
                    text_content="# Notes\nInventory compare should survive resume.",
                ),
                TestDesignArtifactInput(
                    name="hud.png",
                    artifact_kind="image",
                    mime_type="image/png",
                    data_url=image_payload,
                ),
            ],
        )

        self.assertEqual(len(artifacts), 2)
        self.assertTrue(Path(artifacts[0].storage_path).exists())
        self.assertTrue(Path(artifacts[1].storage_path).exists())
        self.assertIn("Inventory compare", artifacts[0].extracted_text)

    def test_heuristic_plan_contains_required_grouped_suites(self) -> None:
        service = IntelligentTestDesignService(self.output_dir)
        bug = BugRecord(
            id=9,
            source="jira",
            external_id="GAME-9",
            game_title="Starfall Arena",
            platform="console",
            engine="Unreal",
            build_number="PS5-1.3.18-cert",
            title="PS5 inventory compare lockup after suspend",
            description="Suspend/resume can lock the player on inventory compare.",
        )
        triage = TriageRecommendation(
            id=None,
            bug_id=9,
            summary="Platform resume issue",
            severity="critical",
            priority="P0",
            component="platform_compliance",
            owner_team="Platform",
            confidence=0.9,
            duplicate_of_id=None,
            probable_root_cause="Resume handling issue.",
            next_action="Add grouped regression coverage.",
            evidence=["e1", "e2"],
        )
        request = IntelligentTestPlanRequest(
            feature_goal="Inventory compare flow on PS5 resume",
            design_notes="Needs platform recovery and save-state coverage.",
            focus_areas=["platform recovery", "save integrity"],
        )

        plan = service.generate_plan(
            bug=bug,
            triage=triage,
            request=request,
            artifacts=[],
        )

        categories = [suite["suite_category"] for suite in plan.suites]
        self.assertEqual(categories[:5], ["Smoke", "Sanity", "Regression", "Functional", "Non-functional"])
        self.assertGreaterEqual(len(plan.suites[0]["test_cases"]), 2)
        self.assertIn("Smoke", plan.suggested_execution_order)

    def test_uses_llm_client_when_available(self) -> None:
        service = IntelligentTestDesignService(self.output_dir, llm_client=FakeLLMClient())
        bug = BugRecord(
            id=10,
            source="manual",
            external_id=None,
            game_title="Neon Circuit",
            platform="pc",
            engine="Unity",
            build_number="Steam-0.9.8",
            title="Ultrawide HUD clipping",
            description="HUD clips on ultrawide displays.",
        )
        request = IntelligentTestPlanRequest(feature_goal="HUD clipping validation")

        plan = service.generate_plan(
            bug=bug,
            triage=None,
            request=request,
            artifacts=[],
        )

        self.assertEqual(plan.summary, "LLM grouped plan")
        self.assertEqual(service.mode_label, "openai (fake)")


if __name__ == "__main__":
    unittest.main()
