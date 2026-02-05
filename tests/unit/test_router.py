"""Test router policy engine."""

import pytest

from mrbench.adapters.fake import FakeAdapter
from mrbench.core.router import Router, RoutingConstraints, RoutingPolicy


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def offline_router() -> Router:
    return Router(policy=RoutingPolicy.OFFLINE_ONLY)


def test_router_selects_first_preference(router: Router):
    adapters = [FakeAdapter()]
    result = router.route(adapters)

    assert result is not None
    assert result.provider == "fake"


def test_router_with_preference_order():
    router = Router(preference_order=["fake", "ollama"])
    adapters = [FakeAdapter()]
    result = router.route(adapters)

    assert result is not None
    assert "Ranked #1" in result.reasons[1]


def test_router_returns_none_for_empty():
    router = Router()
    result = router.route([])

    assert result is None


def test_router_offline_constraint():
    router = Router()
    adapters = [FakeAdapter()]
    constraints = RoutingConstraints(offline_only=True)

    result = router.route(adapters, constraints)

    # Fake adapter is offline
    assert result is not None
    assert result.provider == "fake"


def test_router_streaming_constraint():
    router = Router()
    adapters = [FakeAdapter()]
    constraints = RoutingConstraints(streaming_required=True)

    result = router.route(adapters, constraints)

    # Fake adapter supports streaming
    assert result is not None


def test_router_default_models():
    router = Router()
    adapters = [FakeAdapter()]
    default_models = {"fake": "fake-fast"}

    result = router.route(adapters, default_models=default_models)

    assert result is not None
    assert result.model == "fake-fast"
