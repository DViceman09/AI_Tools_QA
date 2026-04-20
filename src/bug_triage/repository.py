from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .models import (
    BugRecord,
    GeneratedTestPlan,
    TestCandidate,
    TestDesignArtifact,
    TriageRecommendation,
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class BugRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS bugs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    external_id TEXT,
                    game_title TEXT,
                    platform TEXT,
                    engine TEXT,
                    build_number TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    severity TEXT,
                    priority TEXT,
                    component TEXT,
                    owner_team TEXT,
                    environment TEXT,
                    version TEXT,
                    stack_trace TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bug_id INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    component TEXT NOT NULL,
                    owner_team TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    duplicate_of_id INTEGER,
                    probable_root_cause TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (bug_id) REFERENCES bugs(id)
                );

                CREATE TABLE IF NOT EXISTS test_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bug_id INTEGER NOT NULL,
                    test_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    framework TEXT NOT NULL,
                    generated_code TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (bug_id) REFERENCES bugs(id)
                );

                CREATE TABLE IF NOT EXISTS test_design_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bug_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    storage_path TEXT,
                    extracted_text TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (bug_id) REFERENCES bugs(id)
                );

                CREATE TABLE IF NOT EXISTS generated_test_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bug_id INTEGER NOT NULL,
                    feature_goal TEXT NOT NULL,
                    design_notes TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    suites_json TEXT NOT NULL,
                    risks_json TEXT NOT NULL,
                    execution_order_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (bug_id) REFERENCES bugs(id)
                );
                """
            )
            self._migrate_bug_columns(connection)
            connection.commit()

    def create_bug(
        self,
        *,
        source: str,
        external_id: str | None,
        game_title: str,
        platform: str,
        engine: str | None,
        build_number: str | None,
        title: str,
        description: str,
        environment: str | None,
        version: str | None,
        stack_trace: str | None,
        metadata: dict[str, object],
    ) -> BugRecord:
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO bugs (
                    source, external_id, game_title, platform, engine, build_number,
                    title, description, status, severity, priority, component, owner_team,
                    environment, version, stack_trace, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    external_id,
                    game_title,
                    platform,
                    engine,
                    build_number,
                    title,
                    description,
                    environment,
                    version,
                    stack_trace,
                    json.dumps(metadata),
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
            bug_id = int(cursor.lastrowid)
        return self.get_bug(bug_id)

    def update_bug_classification(
        self,
        *,
        bug_id: int,
        severity: str,
        priority: str,
        component: str,
        owner_team: str,
        status: str = "triaged",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE bugs
                SET severity = ?, priority = ?, component = ?, owner_team = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (severity, priority, component, owner_team, status, utc_now(), bug_id),
            )
            connection.commit()

    def list_bugs(self) -> list[BugRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bugs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._bug_from_row(row) for row in rows]

    def get_bug(self, bug_id: int) -> BugRecord:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
        if row is None:
            raise KeyError(f"Bug {bug_id} not found")
        return self._bug_from_row(row)

    def list_other_bugs(self, bug_id: int) -> list[BugRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bugs WHERE id != ? ORDER BY created_at DESC, id DESC",
                (bug_id,),
            ).fetchall()
        return [self._bug_from_row(row) for row in rows]

    def save_triage(self, recommendation: TriageRecommendation) -> TriageRecommendation:
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO triage_recommendations (
                    bug_id, summary, severity, priority, component, owner_team,
                    confidence, duplicate_of_id, probable_root_cause, next_action,
                    evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation.bug_id,
                    recommendation.summary,
                    recommendation.severity,
                    recommendation.priority,
                    recommendation.component,
                    recommendation.owner_team,
                    recommendation.confidence,
                    recommendation.duplicate_of_id,
                    recommendation.probable_root_cause,
                    recommendation.next_action,
                    json.dumps(recommendation.evidence),
                    timestamp,
                ),
            )
            connection.commit()
            triage_id = int(cursor.lastrowid)
        return self.get_latest_triage_for_bug(recommendation.bug_id, triage_id=triage_id)

    def get_latest_triage_for_bug(
        self, bug_id: int, *, triage_id: int | None = None
    ) -> TriageRecommendation | None:
        sql = """
            SELECT * FROM triage_recommendations
            WHERE bug_id = ?
        """
        params: tuple[object, ...] = (bug_id,)
        if triage_id is not None:
            sql += " AND id = ?"
            params = (bug_id, triage_id)
        sql += " ORDER BY created_at DESC, id DESC LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return None if row is None else self._triage_from_row(row)

    def save_test_candidate(self, candidate: TestCandidate) -> TestCandidate:
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO test_candidates (
                    bug_id, test_type, file_path, framework, generated_code,
                    status, execution_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.bug_id,
                    candidate.test_type,
                    candidate.file_path,
                    candidate.framework,
                    candidate.generated_code,
                    candidate.status,
                    candidate.execution_summary,
                    timestamp,
                ),
            )
            connection.commit()
            candidate_id = int(cursor.lastrowid)
        return self.get_test_candidate(candidate_id)

    def get_test_candidate(self, candidate_id: int) -> TestCandidate:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM test_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Test candidate {candidate_id} not found")
        return self._test_candidate_from_row(row)

    def list_test_candidates_for_bug(self, bug_id: int) -> list[TestCandidate]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM test_candidates
                WHERE bug_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (bug_id,),
            ).fetchall()
        return [self._test_candidate_from_row(row) for row in rows]

    def save_test_design_artifact(self, artifact: TestDesignArtifact) -> TestDesignArtifact:
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO test_design_artifacts (
                    bug_id, name, artifact_kind, mime_type, storage_path, extracted_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.bug_id,
                    artifact.name,
                    artifact.artifact_kind,
                    artifact.mime_type,
                    artifact.storage_path,
                    artifact.extracted_text,
                    timestamp,
                ),
            )
            connection.commit()
            artifact_id = int(cursor.lastrowid)
        return self.get_test_design_artifact(artifact_id)

    def get_test_design_artifact(self, artifact_id: int) -> TestDesignArtifact:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM test_design_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Test design artifact {artifact_id} not found")
        return self._test_design_artifact_from_row(row)

    def list_test_design_artifacts_for_bug(self, bug_id: int) -> list[TestDesignArtifact]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM test_design_artifacts
                WHERE bug_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (bug_id,),
            ).fetchall()
        return [self._test_design_artifact_from_row(row) for row in rows]

    def save_generated_test_plan(self, plan: GeneratedTestPlan) -> GeneratedTestPlan:
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO generated_test_plans (
                    bug_id, feature_goal, design_notes, summary, assumptions_json, suites_json,
                    risks_json, execution_order_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.bug_id,
                    plan.feature_goal,
                    plan.design_notes,
                    plan.summary,
                    json.dumps(plan.assumptions),
                    json.dumps(plan.suites),
                    json.dumps(plan.risks_not_covered),
                    json.dumps(plan.suggested_execution_order),
                    timestamp,
                ),
            )
            connection.commit()
            plan_id = int(cursor.lastrowid)
        return self.get_generated_test_plan(plan_id)

    def get_generated_test_plan(self, plan_id: int) -> GeneratedTestPlan:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM generated_test_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Generated test plan {plan_id} not found")
        return self._generated_test_plan_from_row(row)

    def get_latest_test_plan_for_bug(self, bug_id: int) -> GeneratedTestPlan | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM generated_test_plans
                WHERE bug_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (bug_id,),
            ).fetchone()
        return None if row is None else self._generated_test_plan_from_row(row)

    def purge_bug(self, bug_id: int) -> dict[str, list[str]]:
        test_file_paths = [
            candidate.file_path
            for candidate in self.list_test_candidates_for_bug(bug_id)
            if candidate.file_path
        ]
        artifact_paths = [
            artifact.storage_path
            for artifact in self.list_test_design_artifacts_for_bug(bug_id)
            if artifact.storage_path
        ]

        with self.connect() as connection:
            connection.execute("DELETE FROM triage_recommendations WHERE bug_id = ?", (bug_id,))
            connection.execute("DELETE FROM test_candidates WHERE bug_id = ?", (bug_id,))
            connection.execute("DELETE FROM test_design_artifacts WHERE bug_id = ?", (bug_id,))
            connection.execute("DELETE FROM generated_test_plans WHERE bug_id = ?", (bug_id,))
            connection.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
            connection.commit()

        return {
            "test_file_paths": test_file_paths,
            "artifact_paths": artifact_paths,
        }

    def count_bugs(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM bugs").fetchone()
        return int(row["total"])

    def dashboard_metrics(self) -> dict[str, int]:
        with self.connect() as connection:
            total_bugs = int(
                connection.execute("SELECT COUNT(*) AS total FROM bugs").fetchone()["total"]
            )
            triaged_bugs = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT bug_id) AS total FROM triage_recommendations"
                ).fetchone()["total"]
            )
            generated_tests = int(
                connection.execute("SELECT COUNT(*) AS total FROM test_candidates").fetchone()[
                    "total"
                ]
            )
            generated_test_plans = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM generated_test_plans"
                ).fetchone()["total"]
            )
            critical_open = int(
                connection.execute(
                    "SELECT COUNT(*) AS total FROM bugs WHERE severity = 'critical' AND status != 'closed'"
                ).fetchone()["total"]
            )
        coverage = int((triaged_bugs / total_bugs) * 100) if total_bugs else 0
        return {
            "total_bugs": total_bugs,
            "triaged_bugs": triaged_bugs,
            "generated_tests": generated_tests,
            "generated_test_plans": generated_test_plans,
            "critical_open": critical_open,
            "triage_coverage": coverage,
        }

    def _migrate_bug_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(bugs)").fetchall()
        }
        additions = {
            "game_title": "ALTER TABLE bugs ADD COLUMN game_title TEXT",
            "platform": "ALTER TABLE bugs ADD COLUMN platform TEXT",
            "engine": "ALTER TABLE bugs ADD COLUMN engine TEXT",
            "build_number": "ALTER TABLE bugs ADD COLUMN build_number TEXT",
        }
        for column, sql in additions.items():
            if column not in columns:
                connection.execute(sql)

    def _bug_from_row(self, row: sqlite3.Row) -> BugRecord:
        return BugRecord(
            id=row["id"],
            source=row["source"],
            external_id=row["external_id"],
            game_title=row["game_title"] or "Unknown Game",
            platform=row["platform"] or "pc",
            engine=row["engine"],
            build_number=row["build_number"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            severity=row["severity"],
            priority=row["priority"],
            component=row["component"],
            owner_team=row["owner_team"],
            environment=row["environment"],
            version=row["version"],
            stack_trace=row["stack_trace"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _triage_from_row(self, row: sqlite3.Row) -> TriageRecommendation:
        return TriageRecommendation(
            id=row["id"],
            bug_id=row["bug_id"],
            summary=row["summary"],
            severity=row["severity"],
            priority=row["priority"],
            component=row["component"],
            owner_team=row["owner_team"],
            confidence=row["confidence"],
            duplicate_of_id=row["duplicate_of_id"],
            probable_root_cause=row["probable_root_cause"],
            next_action=row["next_action"],
            evidence=json.loads(row["evidence_json"]),
            created_at=row["created_at"],
        )

    def _test_candidate_from_row(self, row: sqlite3.Row) -> TestCandidate:
        return TestCandidate(
            id=row["id"],
            bug_id=row["bug_id"],
            test_type=row["test_type"],
            file_path=row["file_path"],
            framework=row["framework"],
            generated_code=row["generated_code"],
            status=row["status"],
            execution_summary=row["execution_summary"],
            created_at=row["created_at"],
        )

    def _test_design_artifact_from_row(self, row: sqlite3.Row) -> TestDesignArtifact:
        return TestDesignArtifact(
            id=row["id"],
            bug_id=row["bug_id"],
            name=row["name"],
            artifact_kind=row["artifact_kind"],
            mime_type=row["mime_type"],
            storage_path=row["storage_path"],
            extracted_text=row["extracted_text"],
            created_at=row["created_at"],
        )

    def _generated_test_plan_from_row(self, row: sqlite3.Row) -> GeneratedTestPlan:
        return GeneratedTestPlan(
            id=row["id"],
            bug_id=row["bug_id"],
            feature_goal=row["feature_goal"],
            design_notes=row["design_notes"],
            summary=row["summary"],
            assumptions=json.loads(row["assumptions_json"]),
            suites=json.loads(row["suites_json"]),
            risks_not_covered=json.loads(row["risks_json"]),
            suggested_execution_order=json.loads(row["execution_order_json"]),
            created_at=row["created_at"],
        )
