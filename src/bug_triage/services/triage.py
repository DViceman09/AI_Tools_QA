from __future__ import annotations

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..domain import COMPONENT_OWNER_MAPPING
from ..models import BugRecord, TriageRecommendation


logger = logging.getLogger(__name__)

SEVERITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "critical": (
        "save corruption",
        "save wipe",
        "crash on boot",
        "cannot launch",
        "cert blocker",
        "progression blocker",
        "purchase failed",
    ),
    "high": (
        "crash",
        "hard lock",
        "freeze",
        "disconnect",
        "matchmaking fails",
        "black screen",
        "quest blocked",
        "stuck on loading",
    ),
    "medium": (
        "stutter",
        "frame drop",
        "clipping",
        "ui overlap",
        "audio cuts",
        "desync",
        "latency",
        "incorrect reward",
    ),
    "low": ("typo", "cosmetic", "minor visual", "alignment", "subtitle timing"),
}

COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gameplay": ("combat", "quest", "mission", "enemy", "checkpoint", "ability", "collision"),
    "ui_ux": ("hud", "menu", "inventory", "screen", "button", "overlay", "dialog"),
    "rendering": ("shader", "texture", "lighting", "shadow", "artifact", "render", "flicker"),
    "performance": ("fps", "frame", "memory", "leak", "stutter", "hitch", "performance"),
    "networking": ("matchmaking", "lobby", "party", "latency", "disconnect", "server", "desync"),
    "platform_compliance": (
        "playstation",
        "xbox",
        "switch",
        "steam deck",
        "suspend",
        "resume",
        "cert",
        "achievement",
        "trophy",
    ),
    "input_controls": ("controller", "gamepad", "keyboard", "mouse", "input", "remap", "trigger"),
    "save_progression": ("save", "load", "progression", "checkpoint", "autosave", "slot"),
    "commerce_liveops": ("store", "bundle", "currency", "battle pass", "iap", "entitlement", "reward"),
    "build_release": ("boot", "startup", "patch", "install", "download", "build", "packaging"),
    "audio": ("audio", "music", "sound", "voice", "vo", "sfx", "mute"),
}


@dataclass(slots=True)
class TriageContext:
    bug: BugRecord
    historical_bugs: list[BugRecord]


class TriageService:
    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client
        self.mode_label = "heuristic"
        if llm_client is not None and getattr(llm_client, "enabled", False):
            self.mode_label = getattr(llm_client, "mode_label", "openai")

    def analyze(self, context: TriageContext) -> TriageRecommendation:
        if self.llm_client is not None and getattr(self.llm_client, "enabled", False):
            try:
                return self.llm_client.triage_bug(context)
            except Exception as error:
                logger.warning("OpenAI triage failed; falling back to heuristic mode: %s", error)
                self.mode_label = "heuristic (fallback)"
        return self._heuristic_analyze(context)

    def _heuristic_analyze(self, context: TriageContext) -> TriageRecommendation:
        bug = context.bug
        text = " ".join(
            part.strip().lower()
            for part in [
                bug.game_title,
                bug.platform,
                bug.engine or "",
                bug.title,
                bug.description,
                bug.stack_trace or "",
                bug.environment or "",
            ]
            if part
        )

        severity, severity_hits = self._infer_severity(text)
        component = self._infer_component(text)
        owner_team = COMPONENT_OWNER_MAPPING.get(component, "QA")
        priority = self._severity_to_priority(severity)
        duplicate_of_id, duplicate_ratio = self._find_duplicate_candidate(bug, context.historical_bugs)

        confidence = min(
            0.96,
            0.48 + (0.08 * max(severity_hits, 1)) + (0.14 if component != "gameplay" else 0.08),
        )
        if duplicate_ratio >= 0.78:
            confidence += 0.08

        probable_root_cause = self._infer_root_cause(component, text)
        next_action = self._recommend_next_action(severity, duplicate_of_id, bug.platform)
        evidence = self._build_evidence(component, severity_hits, duplicate_ratio, context.historical_bugs)

        return TriageRecommendation(
            id=None,
            bug_id=bug.id or 0,
            summary=self._summarize(bug, severity, component, duplicate_of_id),
            severity=severity,
            priority=priority,
            component=component,
            owner_team=owner_team,
            confidence=round(confidence, 2),
            duplicate_of_id=duplicate_of_id,
            probable_root_cause=probable_root_cause,
            next_action=next_action,
            evidence=evidence,
        )

    def _infer_severity(self, text: str) -> tuple[str, int]:
        critical_hits = sum(1 for keyword in SEVERITY_KEYWORDS["critical"] if keyword in text)
        if critical_hits > 0:
            return "critical", critical_hits
        best = ("medium", 0)
        for severity, keywords in SEVERITY_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if keyword in text)
            if hits > best[1]:
                best = (severity, hits)
        return best if best[1] > 0 else ("medium", 0)

    def _infer_component(self, text: str) -> str:
        best_component = "gameplay"
        best_hits = 0
        for component, keywords in COMPONENT_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if keyword in text)
            if hits > best_hits:
                best_component = component
                best_hits = hits
        return best_component

    def _severity_to_priority(self, severity: str) -> str:
        return {
            "critical": "P0",
            "high": "P1",
            "medium": "P2",
            "low": "P3",
        }[severity]

    def _find_duplicate_candidate(
        self, bug: BugRecord, historical_bugs: list[BugRecord]
    ) -> tuple[int | None, float]:
        best_bug_id: int | None = None
        best_ratio = 0.0
        bug_text = f"{bug.game_title} {bug.platform} {bug.title} {bug.description}".lower()
        bug_title = bug.title.lower()
        for candidate in historical_bugs:
            candidate_text = (
                f"{candidate.game_title} {candidate.platform} {candidate.title} {candidate.description}"
            ).lower()
            title_ratio = SequenceMatcher(None, bug_title, candidate.title.lower()).ratio()
            body_ratio = SequenceMatcher(None, bug_text, candidate_text).ratio()
            ratio = (0.65 * title_ratio) + (0.35 * body_ratio)
            if ratio > best_ratio:
                best_ratio = ratio
                best_bug_id = candidate.id
        if best_ratio >= 0.72:
            return best_bug_id, best_ratio
        return None, best_ratio

    def _infer_root_cause(self, component: str, text: str) -> str:
        if "null" in text or "none" in text:
            return "Likely missing guard logic around a null or unset gameplay state."
        if component == "networking":
            return "Likely session-state, matchmaking, or replication defect between client and backend."
        if component == "platform_compliance":
            return "Likely platform lifecycle handling issue around suspend, resume, entitlement, or certification flow."
        if component == "save_progression":
            return "Likely save serialization, checkpoint state, or progression persistence regression."
        if component == "performance":
            return "Likely main-thread hitching, asset streaming pressure, or memory churn under gameplay load."
        if component == "rendering":
            return "Likely render pipeline, shader variant, or platform-specific GPU state regression."
        if component == "ui_ux":
            return "Likely menu state synchronization or incorrect layout behavior for the current platform target."
        if component == "commerce_liveops":
            return "Likely entitlement, reward grant, or live configuration handling issue."
        if component == "audio":
            return "Likely event routing, mixer state, or platform audio focus regression."
        if component == "build_release":
            return "Likely build packaging, startup initialization, or content patching regression."
        return "Likely gameplay state machine or script logic regression in the reported flow."

    def _recommend_next_action(
        self, severity: str, duplicate_of_id: int | None, platform: str
    ) -> str:
        if duplicate_of_id is not None:
            return f"Link this issue to bug #{duplicate_of_id}, confirm the same repro path, and consolidate tracking."
        if severity == "critical":
            return (
                f"Escalate immediately, notify the owning team, and reproduce on the affected {platform} build "
                "with save-state and crash artifacts attached."
            )
        if severity == "high":
            return (
                "Assign to the owning team, verify the bug on the latest candidate build, and add a regression test "
                "or scripted repro."
            )
        return "Review evidence, confirm severity against player impact, and queue regression coverage."

    def _build_evidence(
        self,
        component: str,
        severity_hits: int,
        duplicate_ratio: float,
        historical_bugs: list[BugRecord],
    ) -> list[str]:
        evidence = [
            f"Component classification matched the {component} game-domain heuristic.",
            f"Severity model matched {severity_hits} high-signal game QA keywords.",
            f"Historical similarity best score: {duplicate_ratio:.2f}.",
        ]
        if historical_bugs:
            evidence.append(f"Compared against {len(historical_bugs)} prior bug records.")
        return evidence

    def _summarize(
        self, bug: BugRecord, severity: str, component: str, duplicate_of_id: int | None
    ) -> str:
        duplicate_phrase = (
            f" Likely duplicate of bug #{duplicate_of_id}." if duplicate_of_id is not None else ""
        )
        return (
            f"{bug.game_title} on {bug.platform} appears to have a {severity} severity {component} issue "
            f"in the reported gameplay flow.{duplicate_phrase}"
        )
