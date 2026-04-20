from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BugCreateRequest(BaseModel):
    source: str = Field(default="manual")
    external_id: str | None = None
    game_title: str = Field(min_length=2, max_length=120)
    platform: Literal["mobile", "pc", "console"]
    engine: str | None = Field(default=None, max_length=50)
    build_number: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    environment: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)
    stack_trace: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestDesignArtifactInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    artifact_kind: Literal["image", "pdf", "text", "notes", "other"]
    mime_type: str = Field(min_length=1, max_length=120)
    text_content: str | None = Field(default=None, max_length=100_000)
    data_url: str | None = Field(default=None, max_length=10_000_000)
    description: str | None = Field(default=None, max_length=2_000)


class IntelligentTestPlanRequest(BaseModel):
    feature_goal: str = Field(min_length=5, max_length=300)
    design_notes: str = Field(default="", max_length=20_000)
    focus_areas: list[str] = Field(default_factory=list, max_length=20)
    artifacts: list[TestDesignArtifactInput] = Field(default_factory=list, max_length=12)
