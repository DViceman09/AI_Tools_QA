from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

from ..models import BugRecord, GeneratedTestPlan, TestDesignArtifact, TriageRecommendation
from ..schemas import IntelligentTestPlanRequest, TestDesignArtifactInput


logger = logging.getLogger(__name__)


class IntelligentTestDesignService:
    def __init__(self, artifact_storage_dir: Path, llm_client: object | None = None) -> None:
        self.artifact_storage_dir = artifact_storage_dir
        self.artifact_storage_dir.mkdir(parents=True, exist_ok=True)
        self.llm_client = llm_client
        self.mode_label = "heuristic"
        if llm_client is not None and getattr(llm_client, "enabled", False):
            self.mode_label = getattr(llm_client, "mode_label", "openai")

    def ingest_artifacts(
        self,
        *,
        bug_id: int,
        artifacts: list[TestDesignArtifactInput],
    ) -> list[TestDesignArtifact]:
        stored: list[TestDesignArtifact] = []
        bug_dir = self.artifact_storage_dir / f"bug_{bug_id}"
        bug_dir.mkdir(parents=True, exist_ok=True)

        for index, artifact in enumerate(artifacts, start=1):
            storage_path: str | None = None
            extracted_text = (artifact.text_content or artifact.description or "").strip() or None

            if artifact.data_url:
                file_name = self._sanitize_name(index, artifact.name)
                file_path = bug_dir / file_name
                header, raw_data = self._split_data_url(artifact.data_url)
                file_bytes = base64.b64decode(raw_data)
                file_path.write_bytes(file_bytes)
                storage_path = str(file_path)

                if artifact.artifact_kind == "text" and extracted_text is None:
                    try:
                        extracted_text = file_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        extracted_text = None
            elif extracted_text:
                file_name = self._sanitize_name(index, artifact.name if artifact.name else "notes.txt")
                file_path = bug_dir / file_name
                file_path.write_text(extracted_text, encoding="utf-8")
                storage_path = str(file_path)

            stored.append(
                TestDesignArtifact(
                    id=None,
                    bug_id=bug_id,
                    name=artifact.name,
                    artifact_kind=artifact.artifact_kind,
                    mime_type=artifact.mime_type,
                    storage_path=storage_path,
                    extracted_text=extracted_text,
                )
            )

        return stored

    def generate_plan(
        self,
        *,
        bug: BugRecord,
        triage: TriageRecommendation | None,
        request: IntelligentTestPlanRequest,
        artifacts: list[TestDesignArtifact],
    ) -> GeneratedTestPlan:
        if self.llm_client is not None and getattr(self.llm_client, "enabled", False):
            try:
                return self.llm_client.generate_intelligent_test_plan(
                    bug=bug,
                    triage=triage,
                    request=request,
                    artifacts=artifacts,
                )
            except Exception as error:
                logger.warning("OpenAI testcase generation failed; falling back to heuristic mode: %s", error)
                self.mode_label = "heuristic (fallback)"

        return self._heuristic_plan(
            bug=bug,
            triage=triage,
            request=request,
            artifacts=artifacts,
        )

    def _heuristic_plan(
        self,
        *,
        bug: BugRecord,
        triage: TriageRecommendation | None,
        request: IntelligentTestPlanRequest,
        artifacts: list[TestDesignArtifact],
    ) -> GeneratedTestPlan:
        component = triage.component if triage is not None else "gameplay"
        severity = triage.severity if triage is not None else "medium"
        artifact_names = [artifact.name for artifact in artifacts]
        artifact_focus = ", ".join(artifact_names[:4]) if artifact_names else "bug report context only"
        focus = request.focus_areas or [component, bug.platform, bug.engine or "gameplay flow"]

        suites = [
            {
                "suite_category": "Smoke",
                "suite_name": f"{bug.game_title} build viability smoke",
                "purpose": "Validate the core player path and startup health before deeper coverage.",
                "coverage_focus": [bug.platform, bug.engine or "engine", component],
                "test_cases": [
                    self._case(
                        title="Boot and reach the primary gameplay shell",
                        priority="P0" if severity in {"critical", "high"} else "P1",
                        objective="Confirm the game launches and the player can reach the affected feature path.",
                        preconditions=[
                            f"Install the latest {bug.platform} build {bug.build_number or bug.version or 'candidate build'}.",
                            "Use a clean local profile and valid network where applicable.",
                        ],
                        steps=[
                            "Launch the game from a cold start.",
                            "Progress through splash, login, entitlement, and landing screens.",
                            f"Navigate into the reported feature area: {request.feature_goal}.",
                        ],
                        expected_results=[
                            "The game remains responsive and reaches the target surface without crash or hard lock.",
                            "No blocking error dialogs, corrupted UI, or fatal loading regressions appear.",
                        ],
                        edge_cases=[
                            "Resume from suspend or background during the load flow.",
                            "Repeat the launch sequence after force-closing the previous session.",
                        ],
                        tags=[bug.platform, component, "smoke"],
                        automation_notes="Automate as the first build-verification gate where possible.",
                    ),
                    self._case(
                        title="Critical path interaction sanity after launch",
                        priority="P1",
                        objective="Confirm the first interaction inside the affected feature path is stable.",
                        preconditions=[
                            "The player is standing at the target feature entry point.",
                        ],
                        steps=[
                            "Trigger the same interaction family as the reported bug.",
                            "Observe transitions, loading feedback, and player input handling.",
                            "Return to the previous screen or gameplay shell.",
                        ],
                        expected_results=[
                            "Interaction completes without crash, stall, or severe visual breakage.",
                            "Control returns to the player after the interaction resolves.",
                        ],
                        edge_cases=[
                            "Spam confirm/cancel input during the transition.",
                            "Trigger the action with low memory or weak network conditions if relevant.",
                        ],
                        tags=[component, "smoke", "player-flow"],
                        automation_notes="Good candidate for a short PlayMode or functional harness smoke path.",
                    ),
                ],
            },
            {
                "suite_category": "Sanity",
                "suite_name": f"{request.feature_goal} sanity sweep",
                "purpose": "Verify the changed area behaves consistently across common state variations.",
                "coverage_focus": focus[:4],
                "test_cases": [
                    self._case(
                        title="Nominal-state sanity of the affected feature",
                        priority="P1",
                        objective="Verify the reported feature works in the most common player state.",
                        preconditions=[
                            "Use a representative account or save with normal progression state.",
                            f"Apply any setup described in the bug: {bug.title}",
                        ],
                        steps=[
                            "Follow the intended player path into the feature.",
                            "Perform the core interaction once with standard timing.",
                            "Exit and re-enter the feature to confirm state cleanup.",
                        ],
                        expected_results=[
                            "The feature behaves consistently across repeat runs.",
                            "No stale state, duplicated rewards, or broken UI remnants remain after exit.",
                        ],
                        edge_cases=[
                            "Use the feature immediately after another adjacent system interaction.",
                            "Re-enter after a partial failure or cancel operation.",
                        ],
                        tags=["sanity", component],
                        automation_notes="Useful as a narrow post-fix validation pack for QA and developers.",
                    ),
                    self._case(
                        title="State-transition sanity around the bug entry point",
                        priority="P1",
                        objective="Verify nearby transitions do not reintroduce the issue.",
                        preconditions=[
                            "Identify two neighboring states before and after the bug trigger.",
                        ],
                        steps=[
                            "Enter the feature from the normal flow.",
                            "Enter the same feature from an alternate path if one exists.",
                            "Back out, reload the state, and repeat the action.",
                        ],
                        expected_results=[
                            "Transitions are visually and functionally consistent.",
                            "No hidden progression, entitlement, or session state becomes invalid.",
                        ],
                        edge_cases=[
                            "Player changes settings or input device mid-flow.",
                            "The system time, locale, or matchmaking region changes before repeating the flow.",
                        ],
                        tags=["sanity", "state-management"],
                        automation_notes="Model as setup/teardown assertions around state entry and exit.",
                    ),
                ],
            },
            {
                "suite_category": "Regression",
                "suite_name": f"{bug.title} regression pack",
                "purpose": "Prove the exact reported defect and closely related negative paths stay fixed.",
                "coverage_focus": [bug.title, component, severity, artifact_focus],
                "test_cases": [
                    self._case(
                        title="Direct repro path no longer fails",
                        priority="P0",
                        objective="Replay the reported issue exactly and confirm the defect no longer occurs.",
                        preconditions=[
                            f"Use the affected build family or a post-fix build derived from {bug.build_number or bug.version or 'the failing build'}.",
                            "Prepare the same inventory, progression, or matchmaking context needed to trigger the bug.",
                        ],
                        steps=[
                            "Apply the original repro sequence from the bug report and design inputs.",
                            "Capture logs, telemetry, and visible state before the final trigger.",
                            "Execute the final trigger and observe the outcome for at least one full resolution cycle.",
                        ],
                        expected_results=[
                            "The original defect does not reproduce.",
                            "The player can continue play without hidden corruption, disconnect, or blocked progression.",
                        ],
                        edge_cases=[
                            "Repeat the exact repro path three times consecutively.",
                            "Trigger the repro path after restarting the title or reconnecting to services.",
                        ],
                        tags=["regression", component, severity],
                        automation_notes="This should become the primary automated regression where the engine and codebase allow it.",
                    ),
                    self._case(
                        title="Neighboring negative paths stay stable",
                        priority="P1",
                        objective="Cover variations around the repro path that commonly fail after a targeted fix.",
                        preconditions=[
                            "Use alternate player state or content variants close to the repro conditions.",
                        ],
                        steps=[
                            "Repeat the repro path with altered timing, inventory, or session state.",
                            "Repeat the path with one input or system dependency missing or delayed.",
                            "Validate recovery and player continuity after the action resolves.",
                        ],
                        expected_results=[
                            "The fix holds under timing variation and imperfect state conditions.",
                            "Fallback messaging and player recovery are coherent if the operation cannot complete.",
                        ],
                        edge_cases=[
                            "Low-connectivity or packet-loss simulation for online flows.",
                            "Suspend/resume, device disconnect, or profile swap during the final trigger.",
                        ],
                        tags=["regression", "negative-path"],
                        automation_notes="Pair with fixtures that vary timing and state initialization.",
                    ),
                ],
            },
            {
                "suite_category": "Functional",
                "suite_name": f"{request.feature_goal} functional coverage",
                "purpose": "Exercise the player-facing feature comprehensively across positive, alternate, and boundary behaviors.",
                "coverage_focus": focus[:5],
                "test_cases": [
                    self._case(
                        title="Primary feature rules and expected outputs",
                        priority="P1",
                        objective="Verify the intended rules, feedback, and outcomes of the feature under normal use.",
                        preconditions=[
                            "Set up a representative player profile and content state.",
                        ],
                        steps=[
                            "Execute the main feature flow from entry to completion.",
                            "Observe rewards, state transitions, UI feedback, and persistence behavior.",
                            "Validate follow-up screens, gameplay consequences, or profile changes.",
                        ],
                        expected_results=[
                            "Feature outputs align with the design intent and player expectations.",
                            "Any resulting state is saved, synced, and rendered correctly across subsequent views.",
                        ],
                        edge_cases=[
                            "Boundary values such as empty inventory, full inventory, max progression, or expired timers.",
                            "Alternate control schemes or accessibility settings enabled.",
                        ],
                        tags=["functional", "core-flow"],
                        automation_notes="Map each business rule or design rule to an assertion set.",
                    ),
                    self._case(
                        title="Secondary and alternate player journeys",
                        priority="P2",
                        objective="Cover less common but legitimate journeys through the same feature.",
                        preconditions=[
                            "Prepare alternate states such as late-game, new-user, and partially-completed states.",
                        ],
                        steps=[
                            "Access the feature from an alternate gameplay or menu route.",
                            "Use optional actions, backtracking, retries, or cancel/confirm branches.",
                            "Verify the system settles into the correct final state after each branch.",
                        ],
                        expected_results=[
                            "Optional branches remain consistent with the intended rules.",
                            "No duplicated grants, missing saves, broken HUD updates, or invisible blockers appear.",
                        ],
                        edge_cases=[
                            "Rapid repeated entry and exit into the feature.",
                            "Cross-session continuity after a quit/relaunch in the middle of the feature lifecycle.",
                        ],
                        tags=["functional", "alternate-path"],
                        automation_notes="Good candidate for parameterized data-driven cases.",
                    ),
                ],
            },
            {
                "suite_category": "Non-functional",
                "suite_name": f"{bug.platform} quality gates for {request.feature_goal}",
                "purpose": "Check platform quality, performance, reliability, and operational resilience around the feature.",
                "coverage_focus": [bug.platform, bug.engine or "engine", "performance", "stability"],
                "test_cases": [
                    self._case(
                        title="Performance and responsiveness under feature load",
                        priority="P1",
                        objective="Confirm the feature remains responsive within acceptable frame-time and memory behavior.",
                        preconditions=[
                            "Enable performance capture or profiling on the target platform.",
                        ],
                        steps=[
                            "Exercise the feature repeatedly for a sustained session.",
                            "Capture frame-time, memory, loading, and service-latency signals.",
                            "Compare the results against platform or team-defined budgets.",
                        ],
                        expected_results=[
                            "The feature does not introduce unacceptable hitching, frame drops, or memory growth.",
                            "Loading and transitions remain understandable to the player.",
                        ],
                        edge_cases=[
                            "Stress the feature after a long play session with multiple scene loads.",
                            "Run on lower-end device tiers or certification-equivalent hardware constraints.",
                        ],
                        tags=["non-functional", "performance"],
                        automation_notes="Integrate with telemetry thresholds and alerting where possible.",
                    ),
                    self._case(
                        title="Reliability, compatibility, and recovery",
                        priority="P1",
                        objective="Validate resilience against platform interruptions and service instability.",
                        preconditions=[
                            "Prepare interruption scenarios relevant to the target platform.",
                        ],
                        steps=[
                            "Trigger suspend/resume, controller disconnect, network fluctuation, or app backgrounding as applicable.",
                            "Return to the feature and continue the player journey.",
                            "Verify save integrity, session continuity, and correct recovery messaging.",
                        ],
                        expected_results=[
                            "The game recovers safely without trapping the player in an invalid state.",
                            "Compatibility-sensitive behaviors remain within platform expectations.",
                        ],
                        edge_cases=[
                            "Locale change, account switch, or entitlement refresh during recovery.",
                            "Unexpected shutdown during write/save/claim operations.",
                        ],
                        tags=["non-functional", "stability", bug.platform],
                        automation_notes="Use scripted interruption hooks on supported target platforms.",
                    ),
                ],
            },
        ]

        return GeneratedTestPlan(
            id=None,
            bug_id=bug.id or 0,
            feature_goal=request.feature_goal,
            design_notes=request.design_notes,
            summary=(
                f"Detailed game QA testcase plan for {bug.game_title} on {bug.platform}, generated from "
                f"the selected bug plus {len(artifacts)} supporting artifact(s)."
            ),
            assumptions=[
                "The latest candidate build contains the target fix or feature state under evaluation.",
                "Uploaded artifacts are representative of the intended gameplay flow and current design direction.",
                "Smoke, Sanity, Regression, Functional, and Non-functional suites are the minimum mandatory groups.",
            ],
            suites=suites,
            risks_not_covered=[
                "Repository-specific automation harness details are not yet connected.",
                "Console certification checklists and first-party compliance cases may require platform-specific expansion.",
                "Opaque binary design sources without text or PDF extraction may need manual QA interpretation.",
            ],
            suggested_execution_order=[
                "Smoke",
                "Sanity",
                "Regression",
                "Functional",
                "Non-functional",
            ],
        )

    def _case(
        self,
        *,
        title: str,
        priority: str,
        objective: str,
        preconditions: list[str],
        steps: list[str],
        expected_results: list[str],
        edge_cases: list[str],
        tags: list[str],
        automation_notes: str,
    ) -> dict[str, object]:
        return {
            "title": title,
            "priority": priority,
            "objective": objective,
            "preconditions": preconditions,
            "steps": steps,
            "expected_results": expected_results,
            "edge_cases": edge_cases,
            "tags": tags,
            "automation_notes": automation_notes,
        }

    def _sanitize_name(self, index: int, file_name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", file_name).strip("._")
        return f"{index:02d}_{cleaned or 'artifact'}"

    def _split_data_url(self, data_url: str) -> tuple[str, str]:
        if "," not in data_url:
            raise ValueError("Invalid data URL received for artifact upload.")
        return tuple(data_url.split(",", 1))
