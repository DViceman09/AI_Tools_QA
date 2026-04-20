from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bug_triage.models import BugRecord, TriageRecommendation
from bug_triage.services.triage import TriageContext, TriageService


class FakeLLMClient:
    enabled = True
    mode_label = "openai (fake)"

    def triage_bug(self, context: TriageContext) -> TriageRecommendation:
        return TriageRecommendation(
            id=None,
            bug_id=context.bug.id or 0,
            summary="LLM summary",
            severity="high",
            priority="P1",
            component="networking",
            owner_team="Online Services",
            confidence=0.91,
            duplicate_of_id=None,
            probable_root_cause="LLM root cause",
            next_action="LLM next action",
            evidence=["LLM evidence 1", "LLM evidence 2"],
        )


class TriageServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TriageService()

    def test_detects_critical_console_platform_bug(self) -> None:
        bug = BugRecord(
            id=5,
            source="jira",
            external_id="GAME-5",
            game_title="Starfall Arena",
            platform="console",
            engine="Unreal",
            build_number="PS5-1.3.18-cert",
            title="PlayStation suspend resume causes crash on boot after inventory overlay",
            description=(
                "Certification blocker on console. Resuming from suspend with the inventory overlay open "
                "causes a crash on boot into a black screen."
            ),
            environment="cert",
        )

        result = self.service.analyze(TriageContext(bug=bug, historical_bugs=[]))

        self.assertEqual(result.severity, "critical")
        self.assertEqual(result.priority, "P0")
        self.assertEqual(result.component, "platform_compliance")
        self.assertEqual(result.owner_team, "Platform")

    def test_flags_duplicate_when_similarity_is_high(self) -> None:
        historical = BugRecord(
            id=2,
            source="jira",
            external_id="GAME-2",
            game_title="Starfall Arena",
            platform="mobile",
            engine="Unity",
            build_number="Android-2.7.4",
            title="Android matchmaking fails after party leader changes region",
            description="Party members time out and disconnect after a region swap.",
        )
        current = BugRecord(
            id=8,
            source="github",
            external_id="BUG-8",
            game_title="Starfall Arena",
            platform="mobile",
            engine="Unity",
            build_number="Android-2.7.5",
            title="Android matchmaking fails after party leader changes region",
            description="Changing region before queueing makes the party time out and disconnect.",
        )

        result = self.service.analyze(TriageContext(bug=current, historical_bugs=[historical]))

        self.assertEqual(result.duplicate_of_id, 2)
        self.assertGreaterEqual(result.confidence, 0.7)

    def test_uses_llm_client_when_available(self) -> None:
        service = TriageService(llm_client=FakeLLMClient())
        bug = BugRecord(
            id=11,
            source="manual",
            external_id=None,
            game_title="Neon Circuit",
            platform="pc",
            engine="Unity",
            build_number="Steam-0.9.8",
            title="Lobby desync",
            description="Desync after rejoining party.",
        )

        result = service.analyze(TriageContext(bug=bug, historical_bugs=[]))

        self.assertEqual(result.summary, "LLM summary")
        self.assertEqual(result.component, "networking")
        self.assertEqual(service.mode_label, "openai (fake)")


if __name__ == "__main__":
    unittest.main()
