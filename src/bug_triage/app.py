from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .domain import GAME_SCOPE_SUMMARY
from .repository import BugRepository
from .schemas import BugCreateRequest, IntelligentTestPlanRequest
from .services.llm import OpenAIGameLLMClient
from .services.seed import seed_demo_data
from .services.testgen import TestGenerationService
from .services.testplan import IntelligentTestDesignService
from .services.triage import TriageContext, TriageService


def create_app() -> FastAPI:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    repository = BugRepository(settings.database_path)
    llm_client = None
    if settings.ai_mode in {"auto", "openai"}:
        llm_client = OpenAIGameLLMClient(
            api_key=settings.openai_api_key,
            triage_model=settings.openai_triage_model,
            testgen_model=settings.openai_testgen_model,
        )
    triage_service = TriageService(llm_client=llm_client)
    test_generation_service = TestGenerationService(
        settings.generated_tests_dir,
        llm_client=llm_client,
    )
    test_design_service = IntelligentTestDesignService(
        settings.artifact_storage_dir,
        llm_client=llm_client,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        if settings.seed_demo_data:
            seed_demo_data(
                repository,
                triage_service,
                test_generation_service,
                test_design_service,
            )
        app.state.repository = repository
        app.state.triage_service = triage_service
        app.state.test_generation_service = test_generation_service
        app.state.test_design_service = test_design_service
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"app_name": settings.app_name, "scope_summary": GAME_SCOPE_SUMMARY},
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "mode": triage_service.mode_label,
            "scope": GAME_SCOPE_SUMMARY,
        }

    @app.get("/api/dashboard")
    async def get_dashboard() -> dict[str, Any]:
        bugs = repository.list_bugs()
        return {
            "metrics": repository.dashboard_metrics(),
            "bugs": [_serialize_bug_summary(repository, bug.id or 0) for bug in bugs],
        }

    @app.post("/api/bugs")
    async def create_bug(payload: BugCreateRequest) -> dict[str, Any]:
        bug = repository.create_bug(
            source=payload.source,
            external_id=payload.external_id,
            game_title=payload.game_title,
            platform=payload.platform,
            engine=payload.engine,
            build_number=payload.build_number,
            title=payload.title,
            description=payload.description,
            environment=payload.environment,
            version=payload.version,
            stack_trace=payload.stack_trace,
            metadata=payload.metadata,
        )
        return _serialize_bug_detail(repository, bug.id or 0)

    @app.get("/api/bugs/{bug_id}")
    async def get_bug(bug_id: int) -> dict[str, Any]:
        try:
            return _serialize_bug_detail(repository, bug_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/bugs/{bug_id}/triage")
    async def triage_bug(bug_id: int) -> dict[str, Any]:
        try:
            bug = repository.get_bug(bug_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        recommendation = triage_service.analyze(
            TriageContext(bug=bug, historical_bugs=repository.list_other_bugs(bug_id))
        )
        repository.save_triage(recommendation)
        repository.update_bug_classification(
            bug_id=bug_id,
            severity=recommendation.severity,
            priority=recommendation.priority,
            component=recommendation.component,
            owner_team=recommendation.owner_team,
        )
        return _serialize_bug_detail(repository, bug_id)

    @app.post("/api/bugs/{bug_id}/generate-tests")
    async def generate_tests(bug_id: int) -> dict[str, Any]:
        try:
            bug = repository.get_bug(bug_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        triage = repository.get_latest_triage_for_bug(bug_id)
        if triage is None:
            recommendation = triage_service.analyze(
                TriageContext(bug=bug, historical_bugs=repository.list_other_bugs(bug_id))
            )
            repository.save_triage(recommendation)
            repository.update_bug_classification(
                bug_id=bug_id,
                severity=recommendation.severity,
                priority=recommendation.priority,
                component=recommendation.component,
                owner_team=recommendation.owner_team,
            )
            triage = repository.get_latest_triage_for_bug(bug_id)
        assert triage is not None

        candidate = test_generation_service.generate(bug, triage)
        repository.save_test_candidate(candidate)
        return _serialize_bug_detail(repository, bug_id)

    @app.post("/api/bugs/{bug_id}/generate-intelligent-testcases")
    async def generate_intelligent_testcases(
        bug_id: int,
        payload: IntelligentTestPlanRequest,
    ) -> dict[str, Any]:
        try:
            bug = repository.get_bug(bug_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        triage = repository.get_latest_triage_for_bug(bug_id)
        if triage is None:
            recommendation = triage_service.analyze(
                TriageContext(bug=bug, historical_bugs=repository.list_other_bugs(bug_id))
            )
            repository.save_triage(recommendation)
            repository.update_bug_classification(
                bug_id=bug_id,
                severity=recommendation.severity,
                priority=recommendation.priority,
                component=recommendation.component,
                owner_team=recommendation.owner_team,
            )
            triage = repository.get_latest_triage_for_bug(bug_id)

        new_artifacts = test_design_service.ingest_artifacts(
            bug_id=bug_id,
            artifacts=payload.artifacts,
        )
        for artifact in new_artifacts:
            repository.save_test_design_artifact(artifact)
        all_artifacts = repository.list_test_design_artifacts_for_bug(bug_id)

        plan = test_design_service.generate_plan(
            bug=bug,
            triage=triage,
            request=payload,
            artifacts=all_artifacts,
        )
        repository.save_generated_test_plan(plan)
        return _serialize_bug_detail(repository, bug_id)

    return app


def _serialize_bug_summary(repository: BugRepository, bug_id: int) -> dict[str, Any]:
    bug = repository.get_bug(bug_id)
    triage = repository.get_latest_triage_for_bug(bug_id)
    tests = repository.list_test_candidates_for_bug(bug_id)
    test_plan = repository.get_latest_test_plan_for_bug(bug_id)
    return {
        "id": bug.id,
        "source": bug.source,
        "external_id": bug.external_id,
        "game_title": bug.game_title,
        "platform": bug.platform,
        "engine": bug.engine,
        "build_number": bug.build_number,
        "title": bug.title,
        "status": bug.status,
        "severity": bug.severity,
        "priority": bug.priority,
        "component": bug.component,
        "owner_team": bug.owner_team,
        "created_at": bug.created_at,
        "triage_summary": triage.summary if triage else None,
        "triage_confidence": triage.confidence if triage else None,
        "test_candidates": len(tests),
        "has_test_plan": test_plan is not None,
    }


def _serialize_bug_detail(repository: BugRepository, bug_id: int) -> dict[str, Any]:
    bug = repository.get_bug(bug_id)
    triage = repository.get_latest_triage_for_bug(bug_id)
    tests = repository.list_test_candidates_for_bug(bug_id)
    artifacts = repository.list_test_design_artifacts_for_bug(bug_id)
    test_plan = repository.get_latest_test_plan_for_bug(bug_id)
    return {
        "bug": {
            "id": bug.id,
            "source": bug.source,
            "external_id": bug.external_id,
            "game_title": bug.game_title,
            "platform": bug.platform,
            "engine": bug.engine,
            "build_number": bug.build_number,
            "title": bug.title,
            "description": bug.description,
            "status": bug.status,
            "severity": bug.severity,
            "priority": bug.priority,
            "component": bug.component,
            "owner_team": bug.owner_team,
            "environment": bug.environment,
            "version": bug.version,
            "stack_trace": bug.stack_trace,
            "metadata": bug.metadata,
            "created_at": bug.created_at,
            "updated_at": bug.updated_at,
        },
        "triage": None
        if triage is None
        else {
            "id": triage.id,
            "summary": triage.summary,
            "severity": triage.severity,
            "priority": triage.priority,
            "component": triage.component,
            "owner_team": triage.owner_team,
            "confidence": triage.confidence,
            "duplicate_of_id": triage.duplicate_of_id,
            "probable_root_cause": triage.probable_root_cause,
            "next_action": triage.next_action,
            "evidence": triage.evidence,
            "created_at": triage.created_at,
        },
        "tests": [
            {
                "id": candidate.id,
                "test_type": candidate.test_type,
                "file_path": candidate.file_path,
                "framework": candidate.framework,
                "generated_code": candidate.generated_code,
                "status": candidate.status,
                "execution_summary": candidate.execution_summary,
                "created_at": candidate.created_at,
            }
            for candidate in tests
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "name": artifact.name,
                "artifact_kind": artifact.artifact_kind,
                "mime_type": artifact.mime_type,
                "storage_path": artifact.storage_path,
                "extracted_text": artifact.extracted_text,
                "created_at": artifact.created_at,
            }
            for artifact in artifacts
        ],
        "test_plan": None
        if test_plan is None
        else {
            "id": test_plan.id,
            "feature_goal": test_plan.feature_goal,
            "design_notes": test_plan.design_notes,
            "summary": test_plan.summary,
            "assumptions": test_plan.assumptions,
            "suites": test_plan.suites,
            "risks_not_covered": test_plan.risks_not_covered,
            "suggested_execution_order": test_plan.suggested_execution_order,
            "created_at": test_plan.created_at,
        },
    }
