from __future__ import annotations

import logging
import re
from pathlib import Path

from ..models import BugRecord, TestCandidate, TriageRecommendation


logger = logging.getLogger(__name__)


class TestGenerationService:
    def __init__(self, generated_tests_dir: Path, llm_client: object | None = None) -> None:
        self.generated_tests_dir = generated_tests_dir
        self.generated_tests_dir.mkdir(parents=True, exist_ok=True)
        self.llm_client = llm_client
        self.mode_label = "heuristic"
        if llm_client is not None and getattr(llm_client, "enabled", False):
            self.mode_label = getattr(llm_client, "mode_label", "openai")

    def generate(self, bug: BugRecord, triage: TriageRecommendation) -> TestCandidate:
        if self.llm_client is not None and getattr(self.llm_client, "enabled", False):
            try:
                return self.llm_client.generate_test_candidate(
                    bug=bug,
                    triage=triage,
                    generated_tests_dir=self.generated_tests_dir,
                )
            except Exception as error:
                logger.warning("OpenAI test generation failed; falling back to heuristic mode: %s", error)
                self.mode_label = "heuristic (fallback)"

        test_type = self._pick_test_type(bug, triage)
        framework, file_extension = self._framework_for_engine(bug.engine)
        file_name = self._make_file_name(bug, file_extension)
        file_path = self.generated_tests_dir / file_name
        generated_code = self._render_test_code(bug, triage, test_type, framework)
        file_path.write_text(generated_code, encoding="utf-8")

        return TestCandidate(
            id=None,
            bug_id=bug.id or 0,
            test_type=test_type,
            file_path=str(file_path),
            framework=framework,
            generated_code=generated_code,
            status="generated",
            execution_summary=(
                f"Candidate test generated locally for {bug.game_title} on {bug.platform}. "
                "Execution hook not connected yet."
            ),
        )

    def _pick_test_type(self, bug: BugRecord, triage: TriageRecommendation) -> str:
        text = f"{bug.title} {bug.description} {triage.component}".lower()
        if triage.component == "networking":
            return "network-regression"
        if triage.component == "platform_compliance":
            return "platform-regression"
        if triage.component == "performance":
            return "performance-guard"
        if triage.component == "save_progression":
            return "progression-regression"
        if triage.component == "commerce_liveops":
            return "liveops-regression"
        if triage.component in {"ui_ux", "rendering"} or any(
            keyword in text for keyword in ("hud", "menu", "screen", "shader")
        ):
            return "ui-regression" if triage.component == "ui_ux" else "rendering-regression"
        return "gameplay-regression"

    def _framework_for_engine(self, engine: str | None) -> tuple[str, str]:
        normalized = (engine or "").strip().lower()
        if normalized == "unity":
            return "Unity Test Framework", "cs"
        if normalized == "unreal":
            return "Unreal Automation Spec", "cpp"
        return "Pytest Harness", "py"

    def _make_file_name(self, bug: BugRecord, file_extension: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", bug.title.lower()).strip("_")[:40]
        return f"bug_{bug.id}_{slug or 'regression'}.{file_extension}"

    def _render_test_code(
        self,
        bug: BugRecord,
        triage: TriageRecommendation,
        test_type: str,
        framework: str,
    ) -> str:
        normalized_framework = framework.lower()
        if "unity" in normalized_framework:
            return self._render_unity_test(bug, triage, test_type)
        if "unreal" in normalized_framework:
            return self._render_unreal_test(bug, triage, test_type)
        return self._render_python_test(bug, triage, test_type)

    def _render_unity_test(
        self, bug: BugRecord, triage: TriageRecommendation, test_type: str
    ) -> str:
        class_name = self._class_name(bug)
        return f"""using NUnit.Framework;
using System.Collections;
using UnityEngine.TestTools;

public class {class_name}
{{
    [UnityTest]
    public IEnumerator Bug_{bug.id}_{self._test_method_name(test_type)}()
    {{
        // Regression guard for {bug.game_title} on {bug.platform}.
        // Bug: {bug.title}
        // Component: {triage.component}
        yield return null;

        Assert.That(true, Is.True, "Replace with the real gameplay or platform assertion.");
    }}
}}
"""

    def _render_unreal_test(
        self, bug: BugRecord, triage: TriageRecommendation, test_type: str
    ) -> str:
        spec_name = self._class_name(bug)
        return f"""#include "Misc/AutomationTest.h"

BEGIN_DEFINE_SPEC({spec_name}, "Game.Regression.Bug{bug.id}", EAutomationTestFlags::ProductFilter | EAutomationTestFlags::ApplicationContextMask)
END_DEFINE_SPEC({spec_name})

void {spec_name}::Define()
{{
    Describe("Bug {bug.id}: {bug.title}", [this]()
    {{
        It("guards against the {test_type} repro on {bug.platform}", [this]()
        {{
            // Component: {triage.component}
            TestTrue(TEXT("Replace with the actual regression assertion."), true);
        }});
    }});
}}
"""

    def _render_python_test(
        self, bug: BugRecord, triage: TriageRecommendation, test_type: str
    ) -> str:
        return f'''def test_bug_{bug.id}_{test_type.replace("-", "_")}(game_harness):
    """
    Regression guard for {bug.game_title} on {bug.platform}
    Bug: {bug.title}
    Engine: {bug.engine or "custom"}
    Component: {triage.component}
    """
    session = game_harness.launch(platform="{bug.platform}")
    result = session.repro_bug_{bug.id}()

    assert result.did_repro is False
'''

    def _class_name(self, bug: BugRecord) -> str:
        slug = re.sub(r"[^a-z0-9]+", " ", bug.title.lower()).title().replace(" ", "")
        return f"Bug{bug.id}{slug[:40] or 'Regression'}Tests"

    def _test_method_name(self, test_type: str) -> str:
        return test_type.replace("-", "_")
