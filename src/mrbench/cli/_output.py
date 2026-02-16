"""CLI output helpers."""

from __future__ import annotations

import json
import sys
from typing import Any


def emit_json(data: Any) -> None:
    """Emit strict JSON to stdout without Rich wrapping effects."""
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
