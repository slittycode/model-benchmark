"""Test secret redaction."""

from mrbench.core.redaction import (
    count_redactions,
    has_secrets,
    redact_secrets,
)


def test_redact_openai_key():
    text = "Using key sk-proj-abc123def456ghi789jkl012mno345pqr678"
    result = redact_secrets(text)
    assert "sk-proj-" not in result
    assert "[REDACTED]" in result


def test_redact_github_pat():
    text = "export GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"
    result = redact_secrets(text)
    assert "ghp_" not in result
    assert "[REDACTED]" in result


def test_no_false_positives():
    text = "The sky is blue and the grass is green"
    result = redact_secrets(text)
    assert result == text


def test_has_secrets_true():
    text = "my key is sk-abc123def456ghi789jkl"
    assert has_secrets(text) is True


def test_has_secrets_false():
    text = "no secrets here"
    assert has_secrets(text) is False


def test_count_redactions():
    text = "key1=sk-abc123def456ghi789jkl key2=ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"
    count = count_redactions(text)
    assert count == 2
