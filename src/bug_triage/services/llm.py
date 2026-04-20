from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..domain import COMPONENT_OWNER_MAPPING, GAME_COMPONENTS
from ..models import BugRecord, GeneratedTestPlan, TestCandidate, TestDesignArtifact, TriageRecommendation
from ..schemas import IntelligentTestPlanRequest
from .triage import TriageContext


logger = logging.getLogger(__name__)

GAME_TEST_TYPES = (
    "gameplay-regression",
    "ui-regression",
    "rendering-regression",
    "performance-guard",
    "network-regression",
    "platform-regression",
    "progression-regression",
    "liveops-regression",
)


class LLMTriageResponse(BaseModel):
    summary: str
    severity: Literal["critical", "high", "medium", "low"]
    priority: Literal["P0", "P1", "P2", "P3"]
    component: Literal[
        "gameplay",
        "ui_ux",
        "rendering",
        "performance",
        "networking",
        "platform_compliance",
        "input_controls",
        "save_progression",
        "commerce_liveops",
        "build_release",
        "audio",
    ]
    owner_team: str
    confidence: float = Field(ge=0.0, le=1.0)
    duplicate_of_id: int | None = None
    probable_root_cause: str
    next_action: str
    evidence: list[str] = Field(min_length=2, max_length=6)


class LLMTestResponse(BaseModel):
    test_type: Literal[
        "gameplay-regression",
        "ui-regression",
        "rendering-regression",
        "performance-guard",
        "network-regression",
        "platform-regression",
        "progression-regression",
        "liveops-regression",
    ]
    framework: str
    file_extension: Literal["cs", "cpp", "py"]
    rationale: str
    generated_code: str


class LLMDetailedTestCase(BaseModel):
    title: str
    priority: Literal["P0", "P1", "P2", "P3"]
    objective: str
    preconditions: list[str] = Field(min_length=1, max_length=6)
    steps: list[str] = Field(min_length=3, max_length=8)
    expected_results: list[str] = Field(min_length=2, max_length=6)
    edge_cases: list[str] = Field(min_length=2, max_length=5)
    tags: list[str] = Field(min_length=2, max_length=8)
    automation_notes: str


class LLMTestSuite(BaseModel):
    suite_category: Literal[
        "Smoke",
        "Sanity",
        "Regression",
        "Functional",
        "Non-functional",
        "Exploratory",
        "Compatibility",
        "Compliance",
    ]
    suite_name: str
    purpose: str
    coverage_focus: list[str] = Field(min_length=2, max_length=6)
    test_cases: list[LLMDetailedTestCase] = Field(min_length=2, max_length=6)


class LLMTestPlanResponse(BaseModel):
    summary: str
    assumptions: list[str] = Field(min_length=2, max_length=6)
    suites: list[LLMTestSuite] = Field(min_length=5, max_length=8)
    risks_not_covered: list[str] = Field(min_length=2, max_length=6)
    suggested_execution_order: list[str] = Field(min_length=5, max_length=8)


class OpenAIGameLLMClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        triage_model: str,
        testgen_model: str,
    ) -> None:
        self.api_key = api_key
        self.triage_model = triage_model
        self.testgen_model = testgen_model
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def mode_label(self) -> str:
        return f"openai ({self.triage_model} / {self.testgen_model})"

    def triage_bug(self, context: TriageContext) -> TriageRecommendation:
        payload = {
            "bug": self._bug_payload(context.bug),
            "historical_bugs": [self._bug_payload(bug) for bug in context.historical_bugs[:8]],
            "allowed_components": list(GAME_COMPONENTS),
            "default_owner_mapping": COMPONENT_OWNER_MAPPING,
        }
        parsed = self._structured_completion(
            model=self.triage_model,
            system_prompt=(
                "You are a senior bug triage analyst for shipped games. "
                "Only handle bugs for mobile, PC, and console games. "
                "Do not classify bugs as web, SaaS, enterprise, checkout, or login products. "
                "Use the allowed component list exactly. "
                "Prioritize player impact, crashes, progression blockers, save corruption, "
                "performance regressions, matchmaking failures, and certification risk."
            ),
            user_prompt=(
                "Produce a structured triage recommendation for this game bug. "
                "If a duplicate is plausible, return the matching historical bug ID, otherwise null.\n"
                f"{json.dumps(payload, indent=2)}"
            ),
            schema=LLMTriageResponse,
        )

        return TriageRecommendation(
            id=None,
            bug_id=context.bug.id or 0,
            summary=parsed.summary,
            severity=parsed.severity,
            priority=parsed.priority,
            component=parsed.component,
            owner_team=parsed.owner_team or COMPONENT_OWNER_MAPPING.get(parsed.component, "QA"),
            confidence=round(parsed.confidence, 2),
            duplicate_of_id=parsed.duplicate_of_id,
            probable_root_cause=parsed.probable_root_cause,
            next_action=parsed.next_action,
            evidence=parsed.evidence,
        )

    def generate_test_candidate(
        self,
        bug: BugRecord,
        triage: TriageRecommendation,
        generated_tests_dir: Path,
    ) -> TestCandidate:
        payload = {
            "bug": self._bug_payload(bug),
            "triage": {
                "summary": triage.summary,
                "severity": triage.severity,
                "priority": triage.priority,
                "component": triage.component,
                "owner_team": triage.owner_team,
                "root_cause": triage.probable_root_cause,
                "next_action": triage.next_action,
            },
            "constraints": {
                "engine_guidance": {
                    "Unity": "Prefer Unity Test Framework C# tests with PlayMode or EditMode coverage.",
                    "Unreal": "Prefer Unreal Automation Spec style C++ tests.",
                    "Custom": "Prefer a concise Python or pseudo-harness regression example.",
                    "Other": "Prefer a concise Python or pseudo-harness regression example.",
                },
                "no_markdown_fences": True,
                "test_types": list(GAME_TEST_TYPES),
            },
        }
        parsed = self._structured_completion(
            model=self.testgen_model,
            system_prompt=(
                "You generate concise regression tests for mobile, PC, and console games only. "
                "Respect the engine, platform, and bug scope. "
                "Return code only in the generated_code field, without markdown fences."
            ),
            user_prompt=(
                "Generate a candidate regression test for this game bug.\n"
                f"{json.dumps(payload, indent=2)}"
            ),
            schema=LLMTestResponse,
        )
        generated_tests_dir.mkdir(parents=True, exist_ok=True)
        file_path = generated_tests_dir / self._make_file_name(bug, parsed.file_extension)
        file_path.write_text(parsed.generated_code, encoding="utf-8")

        return TestCandidate(
            id=None,
            bug_id=bug.id or 0,
            test_type=parsed.test_type,
            file_path=str(file_path),
            framework=parsed.framework,
            generated_code=parsed.generated_code,
            status="generated",
            execution_summary=(
                f"Candidate test generated by OpenAI using {self.testgen_model}. {parsed.rationale}"
            ),
        )

    def generate_intelligent_test_plan(
        self,
        *,
        bug: BugRecord,
        triage: TriageRecommendation | None,
        request: IntelligentTestPlanRequest,
        artifacts: list[TestDesignArtifact],
    ) -> GeneratedTestPlan:
        content = [
            {
                "type": "input_text",
                "text": (
                    "Generate a detailed game QA test plan grouped into suites. "
                    "You must include Smoke, Sanity, Regression, Functional, and Non-functional suites at minimum. "
                    "Each testcase must include preconditions, detailed steps, expected results, edge cases, tags, priority, "
                    "and automation notes.\n"
                    f"{json.dumps(self._test_plan_payload(bug, triage, request, artifacts), indent=2)}"
                ),
            }
        ]
        content.extend(self._artifact_content_items(artifacts))

        parsed = self._structured_completion(
            model=self.testgen_model,
            system_prompt=(
                "You are a principal game QA lead for mobile, PC, and console titles. "
                "Generate intelligent, detailed, execution-ready testcases using the bug context plus any uploaded images, PDFs, "
                "design notes, and supplemental artifacts. "
                "Organize output into suites for Smoke, Sanity, Regression, Functional, and Non-functional testing. "
                "Make edge cases explicit, cover platform and recovery behavior, and stay grounded in the supplied materials."
            ),
            user_content=content,
            schema=LLMTestPlanResponse,
        )

        return GeneratedTestPlan(
            id=None,
            bug_id=bug.id or 0,
            feature_goal=request.feature_goal,
            design_notes=request.design_notes,
            summary=parsed.summary,
            assumptions=parsed.assumptions,
            suites=[suite.model_dump() for suite in parsed.suites],
            risks_not_covered=parsed.risks_not_covered,
            suggested_execution_order=parsed.suggested_execution_order,
        )

    def _structured_completion(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str | None = None,
        user_content: list[dict[str, object]] | None = None,
        schema: type[BaseModel],
    ) -> BaseModel:
        client = self._get_client()
        content = user_content or [{"type": "input_text", "text": user_prompt or ""}]
        input_items = [{"role": "user", "content": content}]

        responses_api = client.responses
        if hasattr(responses_api, "parse"):
            response = responses_api.parse(
                model=model,
                instructions=system_prompt,
                input=input_items,
                text_format=schema,
            )
            parsed = getattr(response, "output_parsed", None)
            if parsed is not None:
                return parsed

        response = responses_api.create(
            model=model,
            instructions=system_prompt,
            input=input_items,
            text={"format": {"type": "json_object"}},
        )
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise RuntimeError("OpenAI response did not include output_text.")
        return schema.model_validate_json(output_text)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("The openai package is not installed.") from error
        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _bug_payload(self, bug: BugRecord) -> dict[str, object]:
        return {
            "id": bug.id,
            "source": bug.source,
            "external_id": bug.external_id,
            "game_title": bug.game_title,
            "platform": bug.platform,
            "engine": bug.engine,
            "build_number": bug.build_number,
            "title": bug.title,
            "description": bug.description,
            "environment": bug.environment,
            "version": bug.version,
            "stack_trace": bug.stack_trace,
            "metadata": bug.metadata,
        }

    def _make_file_name(self, bug: BugRecord, file_extension: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", bug.title.lower()).strip("_")[:40]
        return f"bug_{bug.id}_{slug or 'regression'}.{file_extension}"

    def _artifact_content_items(self, artifacts: list[TestDesignArtifact]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for artifact in artifacts:
            if artifact.artifact_kind == "image" and artifact.storage_path:
                path = Path(artifact.storage_path)
                data_url = self._path_to_data_url(path, artifact.mime_type)
                items.append({"type": "input_image", "image_url": data_url})
            elif artifact.artifact_kind == "pdf" and artifact.storage_path:
                path = Path(artifact.storage_path)
                items.append(
                    {
                        "type": "input_file",
                        "filename": artifact.name,
                        "file_data": self._path_to_base64(path),
                    }
                )
            elif artifact.extracted_text:
                items.append(
                    {
                        "type": "input_text",
                        "text": f"Artifact: {artifact.name}\nType: {artifact.artifact_kind}\nContent:\n{artifact.extracted_text}",
                    }
                )
        return items

    def _test_plan_payload(
        self,
        bug: BugRecord,
        triage: TriageRecommendation | None,
        request: IntelligentTestPlanRequest,
        artifacts: list[TestDesignArtifact],
    ) -> dict[str, object]:
        return {
            "bug": self._bug_payload(bug),
            "triage": None
            if triage is None
            else {
                "summary": triage.summary,
                "severity": triage.severity,
                "priority": triage.priority,
                "component": triage.component,
                "owner_team": triage.owner_team,
                "root_cause": triage.probable_root_cause,
            },
            "test_design_request": {
                "feature_goal": request.feature_goal,
                "design_notes": request.design_notes,
                "focus_areas": request.focus_areas,
            },
            "artifacts": [
                {
                    "name": artifact.name,
                    "artifact_kind": artifact.artifact_kind,
                    "mime_type": artifact.mime_type,
                    "has_text": bool(artifact.extracted_text),
                }
                for artifact in artifacts
            ],
        }

    def _path_to_base64(self, path: Path) -> str:
        import base64

        return base64.b64encode(path.read_bytes()).decode("ascii")

    def _path_to_data_url(self, path: Path, mime_type: str) -> str:
        encoded = self._path_to_base64(path)
        return f"data:{mime_type};base64,{encoded}"
