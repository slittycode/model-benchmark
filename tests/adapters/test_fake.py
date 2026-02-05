"""Test fake adapter."""

import pytest

from mrbench.adapters.base import RunOptions
from mrbench.adapters.fake import FakeAdapter


@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()


def test_fake_adapter_name(adapter: FakeAdapter):
    assert adapter.name == "fake"


def test_fake_adapter_detect(adapter: FakeAdapter):
    result = adapter.detect()
    assert result.detected is True
    assert result.binary_path == "fake"
    assert result.version == "1.0.0"


def test_fake_adapter_list_models(adapter: FakeAdapter):
    models = adapter.list_models()
    assert "fake-fast" in models
    assert "fake-slow" in models
    assert "fake-error" in models


def test_fake_adapter_run_fast(adapter: FakeAdapter):
    options = RunOptions(model="fake-fast")
    result = adapter.run("Hello world", options)
    assert result.exit_code == 0
    assert "Hello" in result.output or "Fake response" in result.output


def test_fake_adapter_run_slow(adapter: FakeAdapter):
    options = RunOptions(model="fake-slow")
    result = adapter.run("Test", options)
    assert result.exit_code == 0
    assert result.wall_time_ms >= 100


def test_fake_adapter_run_error(adapter: FakeAdapter):
    options = RunOptions(model="fake-error")
    result = adapter.run("Test", options)
    assert result.exit_code != 0
    assert result.error is not None


def test_fake_adapter_capabilities(adapter: FakeAdapter):
    caps = adapter.get_capabilities()
    assert caps.name == "fake"
    assert caps.streaming is True
    assert caps.offline is True
