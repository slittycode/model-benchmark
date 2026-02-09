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


def test_get_run_missing_returns_none(storage: Storage):
    assert storage.get_run("missing-run-id") is None


def test_list_runs_respects_limit(storage: Storage):
    run1 = storage.create_run(suite_path="suites/one.yaml")
    run2 = storage.create_run(suite_path="suites/two.yaml")
    run3 = storage.create_run(suite_path="suites/three.yaml")

    listed = storage.list_runs(limit=2)
    listed_ids = {run.id for run in listed}

    assert len(listed) == 2
    assert listed_ids.issubset({run1.id, run2.id, run3.id})


def test_get_job_missing_returns_none(storage: Storage):
    assert storage.get_job("missing-job-id") is None


def test_save_capabilities_round_trip_and_provider_filter(storage: Storage):
    saved = storage.save_capabilities(
        provider="ollama",
        binary_path="/bin/ollama",
        binary_version="0.1.0",
        auth_status="authenticated",
        models=["llama3.2"],
        features={"streaming": True},
    )

    assert saved.provider == "ollama"
    assert saved.binary_version == "0.1.0"
    assert saved.models == ["llama3.2"]
    assert saved.features == {"streaming": True}

    all_caps = storage.get_capabilities()
    assert len(all_caps) == 1
    assert all_caps[0].provider == "ollama"

    filtered = storage.get_capabilities("ollama")
    assert len(filtered) == 1
    assert filtered[0].binary_path == "/bin/ollama"


def test_save_capabilities_upserts_existing_record(storage: Storage):
    initial = storage.save_capabilities(
        provider="codex",
        binary_path="/bin/codex",
        binary_version="1.0.0",
        auth_status="authenticated",
        models=["gpt-5-codex"],
        features={"streaming": True},
    )
    updated = storage.save_capabilities(
        provider="codex",
        binary_path="/bin/codex",
        binary_version="1.1.0",
        auth_status="not_authenticated",
        models=["gpt-5-codex-latest"],
        features={"streaming": False},
    )

    assert updated.id == initial.id
    assert updated.binary_version == "1.1.0"
    assert updated.auth_status == "not_authenticated"
    assert updated.models == ["gpt-5-codex-latest"]
    assert updated.features == {"streaming": False}


def test_save_capabilities_defaults_models_and_features(storage: Storage):
    saved = storage.save_capabilities(
        provider="goose",
        binary_path="/bin/goose",
    )

    assert saved.models == []
    assert saved.features == {}
