"""SQLite storage layer for mrbench.

Handles persistence of benchmark runs, jobs, metrics, and capability snapshots.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from mrbench.core.config import get_default_data_path
from mrbench.core.redaction import redact_for_storage


def get_default_db_path() -> Path:
    """Get the default database path."""
    return get_default_data_path() / "mrbench.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    suite_path TEXT,
    config_snapshot TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    prompt_preview TEXT,
    prompt_stored INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    exit_code INTEGER
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT,
    is_estimated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    binary_path TEXT NOT NULL,
    binary_version TEXT,
    auth_status TEXT,
    models_json TEXT,
    features_json TEXT,
    UNIQUE(provider, binary_path)
);

CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_job_id ON metrics(job_id);
CREATE INDEX IF NOT EXISTS idx_capabilities_provider ON capabilities(provider);
"""


def _now_iso() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


def _generate_id() -> str:
    """Generate a new UUID."""
    return str(uuid.uuid4())


def hash_prompt(prompt: str) -> str:
    """Generate SHA256 hash of prompt text."""
    return hashlib.sha256(prompt.encode()).hexdigest()


@dataclass
class Run:
    """Represents a benchmark run."""

    id: str
    created_at: str
    status: str
    suite_path: str | None = None
    config_snapshot: str | None = None
    completed_at: str | None = None


@dataclass
class Job:
    """Represents a single job within a run."""

    id: str
    run_id: str
    provider: str
    model: str
    prompt_hash: str
    status: str
    created_at: str
    prompt_preview: str | None = None
    prompt_stored: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    exit_code: int | None = None


@dataclass
class Metric:
    """Represents a metric measurement."""

    id: int
    job_id: str
    metric_name: str
    metric_value: float
    metric_unit: str | None = None
    is_estimated: bool = False


@dataclass
class Capability:
    """Represents detected provider capabilities."""

    id: int
    detected_at: str
    provider: str
    binary_path: str
    binary_version: str | None = None
    auth_status: str | None = None
    models: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)


class Storage:
    """SQLite storage manager for mrbench."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            db_path = get_default_db_path()

        self.db_path = db_path

        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection, creating if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        conn.executescript(SCHEMA)
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Storage:
        """Support context-manager usage for deterministic connection cleanup."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection on context exit."""
        self.close()

    def list_tables(self) -> list[str]:
        """List all tables in database."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [row["name"] for row in cursor.fetchall()]

    # Run methods

    def create_run(
        self,
        suite_path: str | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> Run:
        """Create a new benchmark run.

        Args:
            suite_path: Path to the benchmark suite file.
            config_snapshot: Configuration at time of run.

        Returns:
            Created Run object.
        """
        run_id = _generate_id()
        created_at = _now_iso()
        config_json = json.dumps(config_snapshot) if config_snapshot else None

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO runs (id, created_at, suite_path, config_snapshot, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (run_id, created_at, suite_path, config_json),
        )
        conn.commit()

        return Run(
            id=run_id,
            created_at=created_at,
            status="running",
            suite_path=suite_path,
            config_snapshot=config_json,
        )

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Run(
            id=row["id"],
            created_at=row["created_at"],
            status=row["status"],
            suite_path=row["suite_path"],
            config_snapshot=row["config_snapshot"],
            completed_at=row["completed_at"],
        )

    def complete_run(self, run_id: str, status: str = "completed") -> None:
        """Mark a run as completed."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, _now_iso(), run_id),
        )
        conn.commit()

    def list_runs(self, limit: int = 50) -> list[Run]:
        """List recent runs."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            Run(
                id=row["id"],
                created_at=row["created_at"],
                status=row["status"],
                suite_path=row["suite_path"],
                config_snapshot=row["config_snapshot"],
                completed_at=row["completed_at"],
            )
            for row in cursor.fetchall()
        ]

    # Job methods

    def create_job(
        self,
        run_id: str,
        provider: str,
        model: str,
        prompt_hash: str,
        prompt_preview: str | None = None,
    ) -> Job:
        """Create a new job.

        Args:
            run_id: Parent run ID.
            provider: Provider name (e.g., "ollama").
            model: Model name (e.g., "llama3.2").
            prompt_hash: SHA256 hash of prompt.
            prompt_preview: First 100 chars of prompt (redacted).

        Returns:
            Created Job object.
        """
        job_id = _generate_id()
        created_at = _now_iso()

        stored_preview = redact_for_storage(prompt_preview)

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO jobs (id, run_id, provider, model, prompt_hash, prompt_preview, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (job_id, run_id, provider, model, prompt_hash, stored_preview, created_at),
        )
        conn.commit()

        return Job(
            id=job_id,
            run_id=run_id,
            provider=provider,
            model=model,
            prompt_hash=prompt_hash,
            status="pending",
            created_at=created_at,
            prompt_preview=stored_preview,
        )

    def start_job(self, job_id: str) -> None:
        """Mark a job as started."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
            (_now_iso(), job_id),
        )
        conn.commit()

    def complete_job(
        self,
        job_id: str,
        exit_code: int,
        error_message: str | None = None,
    ) -> None:
        """Mark a job as completed."""
        status = "completed" if exit_code == 0 else "failed"
        stored_error = redact_for_storage(error_message)
        conn = self._get_conn()
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, completed_at = ?, exit_code = ?, error_message = ?
            WHERE id = ?
            """,
            (status, _now_iso(), exit_code, stored_error, job_id),
        )
        conn.commit()

    def get_job(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Job(
            id=row["id"],
            run_id=row["run_id"],
            provider=row["provider"],
            model=row["model"],
            prompt_hash=row["prompt_hash"],
            status=row["status"],
            created_at=row["created_at"],
            prompt_preview=row["prompt_preview"],
            prompt_stored=bool(row["prompt_stored"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            exit_code=row["exit_code"],
        )

    def get_jobs_for_run(self, run_id: str) -> list[Job]:
        """Get all jobs for a run."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM jobs WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        )
        return [
            Job(
                id=row["id"],
                run_id=row["run_id"],
                provider=row["provider"],
                model=row["model"],
                prompt_hash=row["prompt_hash"],
                status=row["status"],
                created_at=row["created_at"],
                prompt_preview=row["prompt_preview"],
                prompt_stored=bool(row["prompt_stored"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"],
                exit_code=row["exit_code"],
            )
            for row in cursor.fetchall()
        ]

    # Metric methods

    def add_metric(
        self,
        job_id: str,
        metric_name: str,
        metric_value: float,
        metric_unit: str | None = None,
        is_estimated: bool = False,
    ) -> Metric:
        """Add a metric for a job.

        Args:
            job_id: Job ID.
            metric_name: Name of metric (e.g., "wall_time_ms").
            metric_value: Metric value.
            metric_unit: Unit of measurement.
            is_estimated: Whether value is estimated.

        Returns:
            Created Metric object.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO metrics (job_id, metric_name, metric_value, metric_unit, is_estimated)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, metric_name, metric_value, metric_unit, int(is_estimated)),
        )
        conn.commit()

        return Metric(
            id=cursor.lastrowid or 0,
            job_id=job_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            is_estimated=is_estimated,
        )

    def get_job_metrics(self, job_id: str) -> list[Metric]:
        """Get all metrics for a job."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM metrics WHERE job_id = ?",
            (job_id,),
        )
        return [
            Metric(
                id=row["id"],
                job_id=row["job_id"],
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                metric_unit=row["metric_unit"],
                is_estimated=bool(row["is_estimated"]),
            )
            for row in cursor.fetchall()
        ]

    # Capability methods

    def save_capabilities(
        self,
        provider: str,
        binary_path: str,
        binary_version: str | None = None,
        auth_status: str | None = None,
        models: list[str] | None = None,
        features: dict[str, Any] | None = None,
    ) -> Capability:
        """Save or update provider capabilities.

        Args:
            provider: Provider name.
            binary_path: Path to binary.
            binary_version: Version string.
            auth_status: Authentication status.
            models: List of available models.
            features: Feature dictionary.

        Returns:
            Created or updated Capability object.
        """
        detected_at = _now_iso()
        models_json = json.dumps(models or [])
        features_json = json.dumps(features or {})

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO capabilities
                (detected_at, provider, binary_path, binary_version, auth_status, models_json, features_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, binary_path) DO UPDATE SET
                detected_at = excluded.detected_at,
                binary_version = excluded.binary_version,
                auth_status = excluded.auth_status,
                models_json = excluded.models_json,
                features_json = excluded.features_json
            """,
            (
                detected_at,
                provider,
                binary_path,
                binary_version,
                auth_status,
                models_json,
                features_json,
            ),
        )
        conn.commit()

        # Fetch the saved record
        cursor = conn.execute(
            "SELECT * FROM capabilities WHERE provider = ? AND binary_path = ?",
            (provider, binary_path),
        )
        row = cursor.fetchone()

        return Capability(
            id=row["id"],
            detected_at=row["detected_at"],
            provider=row["provider"],
            binary_path=row["binary_path"],
            binary_version=row["binary_version"],
            auth_status=row["auth_status"],
            models=json.loads(row["models_json"] or "[]"),
            features=json.loads(row["features_json"] or "{}"),
        )

    def get_capabilities(self, provider: str | None = None) -> list[Capability]:
        """Get stored capabilities.

        Args:
            provider: Optional provider filter.

        Returns:
            List of Capability objects.
        """
        conn = self._get_conn()
        if provider:
            cursor = conn.execute(
                "SELECT * FROM capabilities WHERE provider = ?",
                (provider,),
            )
        else:
            cursor = conn.execute("SELECT * FROM capabilities")

        return [
            Capability(
                id=row["id"],
                detected_at=row["detected_at"],
                provider=row["provider"],
                binary_path=row["binary_path"],
                binary_version=row["binary_version"],
                auth_status=row["auth_status"],
                models=json.loads(row["models_json"] or "[]"),
                features=json.loads(row["features_json"] or "{}"),
            )
            for row in cursor.fetchall()
        ]
