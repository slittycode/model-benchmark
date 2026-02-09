"""Test SQLite storage layer."""

from pathlib import Path

import pytest

from mrbench.core.storage import Storage, hash_prompt


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    db_path = tmp_path / "test.db"
    instance = Storage(db_path)
    yield instance
    instance.close()


def test_storage_creates_tables(storage: Storage):
    tables = storage.list_tables()
    assert "runs" in tables
    assert "jobs" in tables
    assert "metrics" in tables
    assert "capabilities" in tables


def test_create_run(storage: Storage):
    run = storage.create_run(suite_path="suites/basic.yaml")
    assert run.id is not None
    assert run.status == "running"
    assert run.suite_path == "suites/basic.yaml"


def test_create_job(storage: Storage):
    run = storage.create_run()
    job = storage.create_job(
        run_id=run.id,
        provider="ollama",
        model="llama3.2",
        prompt_hash="abc123",
    )
    assert job.id is not None
    assert job.provider == "ollama"


def test_add_metric(storage: Storage):
    run = storage.create_run()
    job = storage.create_job(run.id, "ollama", "llama3.2", "hash")
    storage.add_metric(job.id, "wall_time_ms", 1234.5, "ms")

    metrics = storage.get_job_metrics(job.id)
    assert len(metrics) == 1
    assert metrics[0].metric_name == "wall_time_ms"
    assert metrics[0].metric_value == 1234.5


def test_hash_prompt():
    prompt = "What is 2 + 2?"
    h = hash_prompt(prompt)
    assert len(h) == 64  # SHA256 hex length
    assert hash_prompt(prompt) == h  # Deterministic


def test_complete_run(storage: Storage):
    run = storage.create_run()
    storage.complete_run(run.id, "completed")

    updated = storage.get_run(run.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.completed_at is not None


def test_storage_context_manager_closes_connection(tmp_path: Path):
    db_path = tmp_path / "ctx.db"
    with Storage(db_path) as managed:
        tables = managed.list_tables()
        assert "runs" in tables
        assert managed._conn is not None

    assert managed._conn is None
