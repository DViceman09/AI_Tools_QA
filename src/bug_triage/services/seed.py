from __future__ import annotations

from pathlib import Path
import shutil

from ..repository import BugRepository
from ..schemas import IntelligentTestPlanRequest, TestDesignArtifactInput
from .testgen import TestGenerationService
from .testplan import IntelligentTestDesignService
from .triage import TriageContext, TriageService


LEGACY_DEMO_TITLES = {
    "checkout throws 500 when promo code expires during payment",
    "login form loops back to sign-in after mfa success",
    "customer details panel renders overlapping labels on narrow screens",
}

LEGACY_TEST_FILE_PATTERNS = (
    "test_bug_*checkout*.py",
    "test_bug_*api_returns_500*.py",
)

TINY_REFERENCE_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9VE3d2QAAAAASUVORK5CYII="
)


def seed_demo_data(
    repository: BugRepository,
    triage_service: TriageService,
    test_generation_service: TestGenerationService,
    test_design_service: IntelligentTestDesignService,
) -> None:
    seed_triage_service = TriageService()
    seed_test_generation_service = TestGenerationService(test_generation_service.generated_tests_dir)
    seed_test_design_service = IntelligentTestDesignService(test_design_service.artifact_storage_dir)

    _remove_legacy_demo_data(
        repository,
        generated_tests_dir=seed_test_generation_service.generated_tests_dir,
    )

    existing_bugs = repository.list_bugs()
    bugs_by_key = {
        (bug.source, bug.external_id): bug
        for bug in existing_bugs
        if bug.external_id
    }

    for spec in _demo_bug_specs():
        key = (spec["source"], spec["external_id"])
        bug = bugs_by_key.get(key)
        if bug is None:
            bug = repository.create_bug(
                source=spec["source"],
                external_id=spec["external_id"],
                game_title=spec["game_title"],
                platform=spec["platform"],
                engine=spec["engine"],
                build_number=spec["build_number"],
                title=spec["title"],
                description=spec["description"],
                environment=spec["environment"],
                version=spec["version"],
                stack_trace=spec["stack_trace"],
                metadata=spec["metadata"],
            )
            bugs_by_key[key] = bug

        triage = repository.get_latest_triage_for_bug(bug.id or 0)
        if spec["seed_triage"] and triage is None:
            triage = seed_triage_service.analyze(
                TriageContext(
                    bug=bug,
                    historical_bugs=repository.list_other_bugs(bug.id or 0),
                )
            )
            repository.save_triage(triage)
            repository.update_bug_classification(
                bug_id=bug.id or 0,
                severity=triage.severity,
                priority=triage.priority,
                component=triage.component,
                owner_team=triage.owner_team,
            )
            triage = repository.get_latest_triage_for_bug(bug.id or 0)

        if spec["seed_test_candidate"] and triage is not None:
            existing_candidates = repository.list_test_candidates_for_bug(bug.id or 0)
            if not existing_candidates:
                candidate = seed_test_generation_service.generate(bug, triage)
                repository.save_test_candidate(candidate)

        if spec["seed_test_plan"] and triage is not None:
            existing_plan = repository.get_latest_test_plan_for_bug(bug.id or 0)
            if existing_plan is None:
                existing_artifacts = repository.list_test_design_artifacts_for_bug(bug.id or 0)
                if not existing_artifacts:
                    new_artifacts = seed_test_design_service.ingest_artifacts(
                        bug_id=bug.id or 0,
                        artifacts=spec["artifacts"],
                    )
                    for artifact in new_artifacts:
                        repository.save_test_design_artifact(artifact)
                    existing_artifacts = repository.list_test_design_artifacts_for_bug(bug.id or 0)

                plan = seed_test_design_service.generate_plan(
                    bug=bug,
                    triage=triage,
                    request=spec["test_plan_request"],
                    artifacts=existing_artifacts,
                )
                repository.save_generated_test_plan(plan)

    _prune_unreferenced_outputs(
        repository,
        generated_tests_dir=seed_test_generation_service.generated_tests_dir,
        artifact_storage_dir=seed_test_design_service.artifact_storage_dir,
    )


def _remove_legacy_demo_data(
    repository: BugRepository,
    *,
    generated_tests_dir: Path,
) -> None:
    legacy_bug_ids = [
        bug.id or 0
        for bug in repository.list_bugs()
        if bug.title.strip().lower() in LEGACY_DEMO_TITLES
    ]

    for bug_id in legacy_bug_ids:
        removed_paths = repository.purge_bug(bug_id)
        _delete_files_and_empty_parents(removed_paths["test_file_paths"])
        _delete_files_and_empty_parents(removed_paths["artifact_paths"])

    for pattern in LEGACY_TEST_FILE_PATTERNS:
        for path in generated_tests_dir.glob(pattern):
            path.unlink(missing_ok=True)


def _prune_unreferenced_outputs(
    repository: BugRepository,
    *,
    generated_tests_dir: Path,
    artifact_storage_dir: Path,
) -> None:
    referenced_test_paths: set[str] = set()
    referenced_artifact_dirs: set[str] = set()

    for bug in repository.list_bugs():
        bug_id = bug.id or 0
        referenced_test_paths.update(
            candidate.file_path
            for candidate in repository.list_test_candidates_for_bug(bug_id)
            if candidate.file_path
        )
        referenced_artifact_dirs.update(
            str(Path(artifact.storage_path).parent)
            for artifact in repository.list_test_design_artifacts_for_bug(bug_id)
            if artifact.storage_path
        )

    if generated_tests_dir.exists():
        for path in generated_tests_dir.iterdir():
            if path.is_file() and str(path) not in referenced_test_paths:
                path.unlink(missing_ok=True)

    if artifact_storage_dir.exists():
        for bug_dir in artifact_storage_dir.glob("bug_*"):
            if bug_dir.is_dir() and str(bug_dir) not in referenced_artifact_dirs:
                shutil.rmtree(bug_dir, ignore_errors=True)


def _delete_files_and_empty_parents(paths: list[str]) -> None:
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            path.unlink(missing_ok=True)

        parent = path.parent
        if parent.exists() and parent.name.startswith("bug_"):
            try:
                next(parent.iterdir())
            except StopIteration:
                parent.rmdir()


def _demo_bug_specs() -> list[dict[str, object]]:
    return [
        {
            "source": "jira",
            "external_id": "GAME-142",
            "game_title": "Starfall Arena",
            "platform": "console",
            "engine": "Unreal",
            "build_number": "PS5-1.3.18-cert",
            "title": "PS5 hard-locks when resuming from suspend on inventory screen",
            "description": (
                "After resuming the title from suspend while the player inventory is open, the game "
                "hard-locks on a black screen and requires a force close. Reproducible on the PS5 "
                "certification candidate while switching back from the system shell."
            ),
            "environment": "cert",
            "version": "1.3.18",
            "stack_trace": "Fatal: ResumeFlow failed after InventoryOverlay restore.",
            "metadata": {
                "labels": ["ps5", "cert", "suspend-resume"],
                "demo_seed": True,
            },
            "seed_triage": True,
            "seed_test_candidate": True,
            "seed_test_plan": False,
        },
        {
            "source": "github",
            "external_id": "GAME-201",
            "game_title": "Starfall Arena",
            "platform": "mobile",
            "engine": "Unity",
            "build_number": "Android-2.7.4-qa",
            "title": "Android matchmaking fails after party leader changes region",
            "description": (
                "When the party leader changes region from EU to NA and queues immediately, Android clients "
                "stay in matchmaking for around 90 seconds and then disconnect back to the lobby while the "
                "party leader remains in a broken in-between state."
            ),
            "environment": "qa",
            "version": "2.7.4",
            "stack_trace": "TimeoutException in PartyMatchSession.JoinDedicatedLobby",
            "metadata": {
                "labels": ["android", "matchmaking", "party", "networking"],
                "demo_seed": True,
            },
            "seed_triage": True,
            "seed_test_candidate": True,
            "seed_test_plan": False,
        },
        {
            "source": "sentry",
            "external_id": "SEN-311",
            "game_title": "Neon Circuit",
            "platform": "pc",
            "engine": "Unity",
            "build_number": "Steam-0.9.7",
            "title": "Inventory tooltip overlaps compare panel at ultrawide resolution",
            "description": (
                "At 3440x1440 the compare panel and inventory tooltip overlap in the loadout menu, "
                "making weapon stat deltas unreadable. The issue is cosmetic but easy to reproduce "
                "on the PC staging build."
            ),
            "environment": "staging",
            "version": "0.9.7",
            "stack_trace": None,
            "metadata": {
                "labels": ["ui", "pc", "ultrawide", "loadout"],
                "demo_seed": True,
            },
            "seed_triage": False,
            "seed_test_candidate": False,
            "seed_test_plan": False,
        },
        {
            "source": "manual",
            "external_id": "GAME-417",
            "game_title": "Rune Rally",
            "platform": "mobile",
            "engine": "Unity",
            "build_number": "iOS-5.4.0-rc1",
            "title": "Daily challenge reward claim soft-locks after reconnect",
            "description": (
                "If the player reconnects after losing network during the daily challenge reward claim, "
                "the reward modal can stay on screen indefinitely while input is blocked and the player "
                "cannot return to the city hub."
            ),
            "environment": "release-candidate",
            "version": "5.4.0",
            "stack_trace": "SoftLockWarning: DailyChallengeRewardModal did not resolve post reconnect.",
            "metadata": {
                "labels": ["daily-challenge", "reward-claim", "reconnect", "progression"],
                "demo_seed": True,
            },
            "seed_triage": True,
            "seed_test_candidate": False,
            "seed_test_plan": True,
            "test_plan_request": IntelligentTestPlanRequest(
                feature_goal="Daily challenge reward claim flow after reconnect on iOS",
                design_notes=(
                    "Cover clean reconnect, duplicate reward prevention, reward modal recovery, "
                    "currency balance integrity, and return-to-hub behavior."
                ),
                focus_areas=[
                    "network recovery",
                    "reward integrity",
                    "progression recovery",
                    "ui recovery",
                ],
            ),
            "artifacts": [
                TestDesignArtifactInput(
                    name="daily_challenge_acceptance.md",
                    artifact_kind="text",
                    mime_type="text/markdown",
                    text_content=(
                        "# Daily Challenge Reward Claim\n"
                        "- Player should never receive duplicate premium currency.\n"
                        "- Reward modal must resolve to success, retry, or graceful cancel.\n"
                        "- Returning to the city hub must restore full input and updated balances.\n"
                        "- Session recovery should preserve completed challenge state across reconnect."
                    ),
                ),
                TestDesignArtifactInput(
                    name="reward_modal_reference.png",
                    artifact_kind="image",
                    mime_type="image/png",
                    data_url=TINY_REFERENCE_PNG,
                    description="Reference placeholder for the reward claim modal layout.",
                ),
                TestDesignArtifactInput(
                    name="reward_flow_notes.json",
                    artifact_kind="text",
                    mime_type="application/json",
                    text_content=(
                        '{'
                        '"retry_window_seconds": 30,'
                        '"expected_outcomes": ["success","retry","graceful_cancel"],'
                        '"must_persist": ["challenge_complete","currency_balance","hub_navigation_state"]'
                        "}"
                    ),
                ),
            ],
        },
    ]
