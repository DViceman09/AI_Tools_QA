from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BugRecord:
    id: int | None
    source: str
    external_id: str | None
    game_title: str
    platform: str
    engine: str | None
    build_number: str | None
    title: str
    description: str
    status: str = "new"
    severity: str | None = None
    priority: str | None = None
    component: str | None = None
    owner_team: str | None = None
    environment: str | None = None
    version: str | None = None
    stack_trace: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class TriageRecommendation:
    id: int | None
    bug_id: int
    summary: str
    severity: str
    priority: str
    component: str
    owner_team: str
    confidence: float
    duplicate_of_id: int | None
    probable_root_cause: str
    next_action: str
    evidence: list[str]
    created_at: str | None = None


@dataclass(slots=True)
class TestCandidate:
    id: int | None
    bug_id: int
    test_type: str
    file_path: str
    framework: str
    generated_code: str
    status: str
    execution_summary: str
    created_at: str | None = None


@dataclass(slots=True)
class TestDesignArtifact:
    id: int | None
    bug_id: int
    name: str
    artifact_kind: str
    mime_type: str
    storage_path: str | None
    extracted_text: str | None
    created_at: str | None = None


@dataclass(slots=True)
class GeneratedTestPlan:
    id: int | None
    bug_id: int
    feature_goal: str
    design_notes: str
    summary: str
    assumptions: list[str]
    suites: list[dict[str, Any]]
    risks_not_covered: list[str]
    suggested_execution_order: list[str]
    created_at: str | None = None
