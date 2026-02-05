"""Test package version."""

import mrbench


def test_version_exists():
    assert hasattr(mrbench, "__version__")
    assert isinstance(mrbench.__version__, str)
    assert len(mrbench.__version__) > 0


def test_version_format():
    # Should be semver-like
    parts = mrbench.__version__.split(".")
    assert len(parts) >= 2
