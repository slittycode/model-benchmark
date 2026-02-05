"""Secret redaction for mrbench.

Automatically redacts sensitive patterns from text to prevent accidental exposure
of API keys, tokens, and credentials in logs and outputs.
"""

from __future__ import annotations

import re
from re import Pattern

# Compiled regex patterns for common secret formats
REDACT_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # OpenAI API keys
    ("OpenAI API Key", re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE)),
    # OpenAI project keys
    ("OpenAI Project Key", re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}", re.IGNORECASE)),
    # Anthropic API keys
    ("Anthropic API Key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}", re.IGNORECASE)),
    # Generic anthropic keys
    ("Anthropic Key", re.compile(r"anthropic-[a-zA-Z0-9]{20,}", re.IGNORECASE)),
    # Bearer tokens
    ("Bearer Token", re.compile(r"Bearer\s+[a-zA-Z0-9._-]{10,}", re.IGNORECASE)),
    # GitHub Personal Access Tokens
    ("GitHub PAT", re.compile(r"ghp_[a-zA-Z0-9]{36,}")),
    # GitHub OAuth tokens
    ("GitHub OAuth", re.compile(r"gho_[a-zA-Z0-9]{36,}")),
    # GitLab Personal Access Tokens
    ("GitLab PAT", re.compile(r"glpat-[a-zA-Z0-9-]{20,}")),
    # Google API keys
    ("Google API Key", re.compile(r"AIza[a-zA-Z0-9_-]{35}")),
    # AWS Access Key IDs
    ("AWS Access Key", re.compile(r"AKIA[A-Z0-9]{16}")),
    # AWS Secret Keys (following common patterns)
    ("AWS Secret Key", re.compile(r"(?:aws_secret|secret_key)\s*[:=]\s*['\"]?[a-zA-Z0-9/+=]{40}")),
    # Generic password patterns
    ("Password", re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?\S{8,}", re.IGNORECASE)),
    # Generic API key patterns
    ("API Key", re.compile(r"(?:api[_-]?key)\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{16,}", re.IGNORECASE)),
    # Generic token patterns
    ("Token", re.compile(r"(?:token|secret)\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{16,}", re.IGNORECASE)),
]

REDACTION_PLACEHOLDER = "[REDACTED]"


def redact_secrets(text: str, placeholder: str = REDACTION_PLACEHOLDER) -> str:
    """Redact known secret patterns from text.

    Args:
        text: Text that may contain secrets.
        placeholder: String to replace secrets with.

    Returns:
        Text with secrets replaced by placeholder.
    """
    result = text
    for _name, pattern in REDACT_PATTERNS:
        result = pattern.sub(placeholder, result)
    return result


def redact_command_args(args: list[str], placeholder: str = REDACTION_PLACEHOLDER) -> list[str]:
    """Redact secrets from command line arguments.

    This is useful for logging subprocess calls without exposing secrets.

    Args:
        args: List of command line arguments.
        placeholder: String to replace secrets with.

    Returns:
        Copy of args with secrets redacted.
    """
    return [redact_secrets(arg, placeholder) for arg in args]


def count_redactions(text: str) -> int:
    """Count how many secret patterns match in text.

    Useful for testing and auditing.

    Args:
        text: Text to scan for secrets.

    Returns:
        Number of secret patterns found.
    """
    count = 0
    for _name, pattern in REDACT_PATTERNS:
        count += len(pattern.findall(text))
    return count


def has_secrets(text: str) -> bool:
    """Check if text contains any known secret patterns.

    Args:
        text: Text to check.

    Returns:
        True if any secret patterns are found.
    """
    return count_redactions(text) > 0


def get_redaction_pattern_names() -> list[str]:
    """Get list of all redaction pattern names.

    Returns:
        List of pattern names (e.g., ["OpenAI API Key", "GitHub PAT"]).
    """
    return [name for name, _ in REDACT_PATTERNS]
