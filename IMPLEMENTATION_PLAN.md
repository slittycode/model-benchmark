# mrbench Implementation Plan

> **Model Router + Benchmark** — A CLI-first tool to route prompts to existing AI CLIs and benchmark them.

---

## 1. Clarifying Questions + Assumptions

### Questions (0 of 3 budget used)

After reviewing the requirements, I can proceed with explicit assumptions rather than blocking questions:

### Explicit Assumptions

| Area | Assumption |
|------|------------|
| **Primary adapter** | Ollama (most likely installed, well-documented API, easy to test) |
| **Streaming** | Parse line-by-line from subprocess stdout; TTFT measured on first non-empty line |
| **Token counting** | Use `tiktoken` for approximate counts when provider doesn't report; mark as "estimated" |
| **Cost tracking** | MVP: "unknown" for all; future: opt-in lookup table from public pricing pages |
| **Benchmark parallelism** | Sequential by default; `--parallel N` in future |
| **Python version** | 3.12+ (walrus, modern typing, `tomllib` stdlib) |
| **macOS paths** | Config: `~/.config/mrbench/`, Data: `~/.local/share/mrbench/` (XDG-style, works on macOS) |

---

## 2. Architecture Options

### Option A: Pure CLI + SQLite (Recommended for MVP)

```
┌─────────────────────────────────────────────────────────────┐
│                         mrbench CLI                          │
│  (Typer + Rich)                                              │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  doctor  │  detect  │   run    │  bench   │     report      │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴────────┬────────┘
     │          │          │          │              │
     ▼          ▼          ▼          ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Adapter Registry                         │
│  (Plugin discovery via entry_points)                         │
├─────────┬─────────┬─────────┬─────────┬─────────┬───────────┤
│ Ollama  │ Claude  │ Codex   │ Gemini  │  Goose  │   Fake    │
│ Adapter │ Adapter │ Adapter │ Adapter │ Adapter │  Adapter  │
└────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴─────┬─────┘
     │         │         │         │         │          │
     ▼         ▼         ▼         ▼         ▼          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Subprocess Executor                        │
│  (stdin prompt, stdout capture, timeout, streaming)          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  SQLite (runs, jobs, metrics) + JSONL artifacts in ./out/    │
└─────────────────────────────────────────────────────────────┘
```

**Pros:** Simple, testable, no server process, works offline  
**Cons:** No live dashboard (acceptable for MVP)

---

### Option B: CLI + Optional TUI (Rich Live)

Same as Option A, but add `mrbench watch` command that uses Rich Live panels to show benchmark progress in real-time.

**Pros:** Better UX during long benchmarks  
**Cons:** More complexity, can add post-MVP

---

### Option C: CLI + Background Daemon

Add `mrbench daemon start/stop` for persistent model warm-up and caching.

**Pros:** Faster repeated runs  
**Cons:** Violates "no server" spirit, complexity

---

### Recommendation: **Option A** for MVP, with hooks for Option B post-MVP

---

## 3. Threat Model + Mitigations

| Threat | Risk | Mitigation |
|--------|------|------------|
| **Prompt privacy leak** | Prompts may contain secrets, PII, or proprietary code | Default: don't persist prompt bodies. `--store-prompts` opt-in. Redact known patterns (API keys, tokens) before logging. |
| **Secret exposure in logs** | CLI invocations might include API keys in args | Never pass secrets as CLI args. Use stdin or env vars. Redact `--api-key`, `Bearer`, etc. from debug logs. |
| **Command injection** | Malformed prompt could inject shell commands | Never use `shell=True`. Use `subprocess.run()` with list args. Validate/sanitize model names against allowlist patterns. |
| **PATH hijacking** | Attacker places malicious `ollama` binary in PATH | Warn if binary not in expected locations (`/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`). Optional `--trusted-paths` config. |
| **Config file tampering** | Malicious config could point to attacker binaries | Validate config schema strictly. Warn on unexpected keys. Never `exec()` config values. |
| **Supply chain attack** | Malicious dependencies | Pin dependencies with hashes. Use `pip-audit` in CI. Minimal dependency tree. |
| **Device compromise** | Attacker has local access | Out of scope (assume trusted local environment), but never persist plaintext secrets. |
| **Subprocess timeout DoS** | Malicious model hangs forever | Enforce timeouts (default 300s, configurable). Kill process group on timeout. |

### Redaction Patterns (built-in)

```python
REDACT_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",          # OpenAI keys
    r"anthropic-[a-zA-Z0-9]{20,}",   # Anthropic keys  
    r"Bearer\s+[a-zA-Z0-9._-]+",     # Bearer tokens
    r"ghp_[a-zA-Z0-9]{36,}",         # GitHub PATs
    r"glpat-[a-zA-Z0-9-]{20,}",      # GitLab PATs
    r"password\s*[:=]\s*\S+",        # password= patterns
]
```

---

## 4. Data Model

### 4.1 SQLite Schema

```sql
-- File: src/mrbench/schema.sql

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,              -- UUID
    created_at TEXT NOT NULL,         -- ISO8601
    suite_path TEXT,                  -- path to suite YAML (nullable for single runs)
    config_snapshot TEXT,             -- JSON of config at run time
    status TEXT NOT NULL DEFAULT 'running',  -- running, completed, failed, cancelled
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,              -- UUID
    run_id TEXT NOT NULL REFERENCES runs(id),
    provider TEXT NOT NULL,           -- e.g., "ollama", "claude"
    model TEXT NOT NULL,              -- e.g., "llama3.2", "claude-3-opus"
    prompt_hash TEXT NOT NULL,        -- SHA256 of prompt (for dedup without storing)
    prompt_preview TEXT,              -- First 100 chars (redacted), nullable
    prompt_stored INTEGER DEFAULT 0,  -- 1 if full prompt in artifacts
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, timeout
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,               -- Redacted error if failed
    exit_code INTEGER
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    metric_name TEXT NOT NULL,        -- wall_time_ms, ttft_ms, output_tokens, etc.
    metric_value REAL NOT NULL,
    metric_unit TEXT,                 -- ms, tokens, bytes
    is_estimated INTEGER DEFAULT 0    -- 1 if value is estimated
);

CREATE TABLE IF NOT EXISTS capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    binary_path TEXT NOT NULL,
    binary_version TEXT,
    auth_status TEXT,                 -- authenticated, unauthenticated, unknown
    models_json TEXT,                 -- JSON array of available models
    features_json TEXT,               -- JSON of capabilities
    UNIQUE(provider, binary_path)
);

CREATE INDEX idx_jobs_run_id ON jobs(run_id);
CREATE INDEX idx_metrics_job_id ON metrics(job_id);
CREATE INDEX idx_capabilities_provider ON capabilities(provider);
```

### 4.2 File Layout

```
./out/
├── <run_id>/
│   ├── run_meta.json           # Run metadata
│   ├── jobs/
│   │   ├── <job_id>.json       # Job result + metrics
│   │   ├── <job_id>.output.txt # Raw output (if stored)
│   │   └── <job_id>.prompt.txt # Prompt (only if --store-prompts)
│   └── report.md               # Generated report

~/.local/share/mrbench/
├── mrbench.db                  # SQLite database
└── cache/
    └── capabilities.json       # Last detect snapshot
```

---

## 5. Config Schema (TOML)

```toml
# ~/.config/mrbench/config.toml

[general]
# Default output directory (relative to cwd or absolute)
output_dir = "./out"

# Default timeout for subprocess calls (seconds)
timeout = 300

# Store prompts by default (privacy-sensitive)
store_prompts = false

# Enable network features (model alias lookup, etc.)
enable_network = false

[discovery]
# Additional paths to search for binaries
extra_paths = [
    "~/bin",
    "~/.local/bin",
]

# Trusted binary locations (warn if binary found elsewhere)
trusted_paths = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "~/.local/bin",
]

[routing]
# Default routing policy: "preference", "fastest", "cheapest", "offline_only"
default_policy = "preference"

# Provider preference order (first available wins)
preference_order = [
    "ollama",
    "claude",
    "codex",
    "gemini",
    "goose",
    "opencode",
]

# Constraints applied by default
[routing.constraints]
offline_only = false
max_latency_ms = 30000
streaming_required = false

[providers.ollama]
enabled = true
# Override binary path if not in PATH
# binary = "/custom/path/to/ollama"
default_model = "llama3.2"

[providers.claude]
enabled = true
default_model = "claude-3-5-sonnet"
# Use --dangerously-skip-permissions for non-interactive
skip_permissions = false

[providers.codex]
enabled = true
default_model = "o4-mini"
approval_mode = "full-auto"

[providers.gemini]
enabled = true
default_model = "gemini-2.5-pro"

[providers.goose]
enabled = true

[providers.opencode]
enabled = true

# Logging configuration
[logging]
level = "INFO"  # DEBUG, INFO, WARNING, ERROR
redact_secrets = true
```

---

## 6. Discovery Matrix

| Provider | Detect Binary | Version Check | Auth Check | List Models | Run Prompt |
|----------|--------------|---------------|------------|-------------|------------|
| **Ollama** | `command -v ollama` | `ollama --version` | `ollama list` (non-empty = OK) | `ollama list` | `ollama run <model> "<prompt>"` |
| **Claude Code** | `command -v claude` | `claude --version` | `claude --print-auth-status` (if exists) or try `claude -p "hi" 2>&1` | N/A (manual model ID) | `claude -p "<prompt>" --output-format json` |
| **Codex CLI** | `command -v codex` | `codex --version` | `codex auth status` (if exists) or infer from env | N/A | `codex exec "<prompt>"` or `codex "<prompt>"` |
| **Gemini CLI** | `command -v gemini` | `gemini --version` | Check for `~/.config/gemini/` auth files | N/A | `gemini -p "<prompt>" --output-format json` |
| **OpenCode** | `command -v opencode` | `opencode --version` | N/A (uses env vars) | N/A | `opencode -p "<prompt>" --quiet` |
| **Goose** | `command -v goose` | `goose --version` | Check config files | N/A | `goose run "<prompt>"` |
| **llama.cpp** | `command -v llama-cli` or `main` | `llama-cli --version` | N/A (local only) | Scan `~/.cache/llama.cpp/` | `llama-cli -m <model> -p "<prompt>"` |
| **vLLM** | `command -v vllm` | `vllm --version` | N/A (server-based) | `vllm list` (if server running) | `vllm complete --quick "<prompt>"` |

### Safe Auth Detection Rules

1. **Never parse token files** — only check file existence
2. **Never log auth command output** — only capture exit code
3. **Timeout quickly** (5s) — auth check shouldn't block
4. **Fallback to "unknown"** — if any error, assume unknown

---

## 7. Repository Structure

```
model-benchmark/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
│
├── src/
│   └── mrbench/
│       ├── __init__.py
│       ├── __main__.py              # Entry point: python -m mrbench
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py              # Typer app, command registration
│       │   ├── doctor.py            # mrbench doctor
│       │   ├── detect.py            # mrbench detect
│       │   ├── providers.py         # mrbench providers
│       │   ├── models.py            # mrbench models
│       │   ├── run.py               # mrbench run
│       │   ├── route.py             # mrbench route
│       │   ├── bench.py             # mrbench bench
│       │   └── report.py            # mrbench report
│       │
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py              # Abstract Adapter class
│       │   ├── registry.py          # Adapter discovery + registration
│       │   ├── ollama.py
│       │   ├── claude.py
│       │   ├── codex.py
│       │   ├── gemini.py
│       │   ├── goose.py
│       │   ├── opencode.py
│       │   ├── llamacpp.py
│       │   ├── vllm.py
│       │   └── fake.py              # Fake adapter for testing
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py            # Config loading + validation
│       │   ├── discovery.py         # Binary discovery logic
│       │   ├── executor.py          # Subprocess execution + streaming
│       │   ├── router.py            # Routing policy engine
│       │   ├── benchmark.py         # Benchmark orchestration
│       │   ├── metrics.py           # Metric collection + calculation
│       │   ├── storage.py           # SQLite + file I/O
│       │   └── redaction.py         # Secret redaction
│       │
│       ├── reporters/
│       │   ├── __init__.py
│       │   ├── markdown.py          # Markdown report generator
│       │   └── json.py              # JSON export
│       │
│       └── schema.sql               # SQLite schema
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── test_discovery.py
│   │   ├── test_executor.py
│   │   ├── test_router.py
│   │   ├── test_redaction.py
│   │   └── test_metrics.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── test_base.py
│   │   ├── test_ollama.py
│   │   ├── test_fake.py
│   │   └── test_registry.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_cli_doctor.py
│   │   ├── test_cli_detect.py
│   │   ├── test_cli_run.py
│   │   ├── test_cli_bench.py
│   │   └── test_cli_report.py
│   └── fixtures/
│       ├── fake_ollama.py           # Fake CLI script for testing
│       ├── fake_claude.py
│       ├── sample_suite.yaml
│       └── sample_config.toml
│
├── suites/
│   ├── basic.yaml                   # Simple prompts for smoke testing
│   ├── coding.yaml                  # Code-generation prompts
│   └── reasoning.yaml               # Complex reasoning prompts
│
└── docs/
    ├── index.md
    ├── quickstart.md
    ├── configuration.md
    ├── adapters.md
    └── benchmarking.md
```

---

## 8. Step-by-Step Implementation Plan (TDD)

### Phase 1: Project Scaffolding (Tasks 1.1–1.5)

---

#### Task 1.1: Initialize Python Project

**Files to create:**
- `pyproject.toml`
- `src/mrbench/__init__.py`
- `src/mrbench/__main__.py`
- `README.md`
- `.gitignore`

**Test:** `tests/unit/test_version.py`

```python
# tests/unit/test_version.py
"""Test that package version is accessible."""
import mrbench

def test_version_exists():
    assert hasattr(mrbench, "__version__")
    assert isinstance(mrbench.__version__, str)
    assert len(mrbench.__version__) > 0
```

**Commands:**
```bash
# Create project structure
mkdir -p src/mrbench tests/unit

# Run test (expect FAIL - module doesn't exist yet)
uv run pytest tests/unit/test_version.py -v
# Expected: ModuleNotFoundError

# Implement minimal package
# ... create files ...

# Run test (expect PASS)
uv run pytest tests/unit/test_version.py -v
# Expected: PASSED

git add . && git commit -m "feat: initialize project with pyproject.toml and version"
```

---

#### Task 1.2: Set Up CLI Framework with Typer

**Files to create/modify:**
- `src/mrbench/cli/__init__.py`
- `src/mrbench/cli/main.py`

**Test:** `tests/unit/test_cli_main.py`

```python
# tests/unit/test_cli_main.py
"""Test CLI app instantiation."""
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_cli_has_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mrbench" in result.output.lower() or "usage" in result.output.lower()

def test_cli_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
```

**Commands:**
```bash
# Run test (expect FAIL)
uv run pytest tests/unit/test_cli_main.py -v

# Implement CLI app
# ... edit files ...

# Run test (expect PASS)
uv run pytest tests/unit/test_cli_main.py -v

git commit -am "feat(cli): add Typer CLI framework with --help and --version"
```

---

#### Task 1.3: Implement Config Loading

**Files to create:**
- `src/mrbench/core/config.py`

**Test:** `tests/unit/test_config.py`

```python
# tests/unit/test_config.py
"""Test configuration loading and validation."""
import pytest
from pathlib import Path
from mrbench.core.config import load_config, MrbenchConfig, DEFAULT_CONFIG

def test_default_config_is_valid():
    config = DEFAULT_CONFIG
    assert config.general.timeout == 300
    assert config.general.store_prompts is False

def test_load_config_from_toml(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('''
[general]
timeout = 600
store_prompts = true
''')
    config = load_config(config_file)
    assert config.general.timeout == 600
    assert config.general.store_prompts is True

def test_load_config_missing_file_uses_defaults(tmp_path: Path):
    config = load_config(tmp_path / "nonexistent.toml")
    assert config == DEFAULT_CONFIG

def test_config_validates_timeout_positive():
    with pytest.raises(ValueError, match="timeout"):
        MrbenchConfig.model_validate({"general": {"timeout": -1}})
```

**Commands:**
```bash
uv run pytest tests/unit/test_config.py -v
# Implement, then re-run
git commit -am "feat(core): add TOML config loading with validation"
```

---

#### Task 1.4: Implement Secret Redaction

**Files to create:**
- `src/mrbench/core/redaction.py`

**Test:** `tests/unit/test_redaction.py`

```python
# tests/unit/test_redaction.py
"""Test secret redaction patterns."""
from mrbench.core.redaction import redact_secrets, REDACT_PATTERNS

def test_redact_openai_key():
    text = "Using key sk-proj-abc123def456ghi789jkl012mno345pqr678"
    result = redact_secrets(text)
    assert "sk-proj-" not in result
    assert "[REDACTED]" in result

def test_redact_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    result = redact_secrets(text)
    assert "Bearer" in result  # Keep the word
    assert "eyJ" not in result

def test_redact_github_pat():
    text = "export GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"
    result = redact_secrets(text)
    assert "ghp_" not in result

def test_no_false_positives():
    text = "The sky is blue and the grass is green"
    result = redact_secrets(text)
    assert result == text

def test_redact_multiple_secrets():
    text = "key1=sk-abc123def456 key2=ghp_xyz789"
    result = redact_secrets(text)
    assert result.count("[REDACTED]") == 2
```

**Commands:**
```bash
uv run pytest tests/unit/test_redaction.py -v
git commit -am "feat(core): add secret redaction with common patterns"
```

---

#### Task 1.5: Implement SQLite Storage Layer

**Files to create:**
- `src/mrbench/schema.sql`
- `src/mrbench/core/storage.py`

**Test:** `tests/unit/test_storage.py`

```python
# tests/unit/test_storage.py
"""Test SQLite storage layer."""
import pytest
from pathlib import Path
from mrbench.core.storage import Storage, Run, Job, Metric

@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    db_path = tmp_path / "test.db"
    return Storage(db_path)

def test_storage_creates_tables(storage: Storage):
    # Tables should exist after init
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
```

**Commands:**
```bash
uv run pytest tests/unit/test_storage.py -v
git commit -am "feat(core): add SQLite storage layer with runs, jobs, metrics"
```

---

### Phase 2: Adapter Framework (Tasks 2.1–2.4)

---

#### Task 2.1: Define Abstract Adapter Base Class

**Files to create:**
- `src/mrbench/adapters/base.py`

**Test:** `tests/adapters/test_base.py`

```python
# tests/adapters/test_base.py
"""Test abstract adapter base class."""
import pytest
from abc import ABC
from mrbench.adapters.base import Adapter, AdapterCapabilities, RunResult

def test_adapter_is_abstract():
    assert issubclass(Adapter, ABC)
    with pytest.raises(TypeError):
        Adapter()  # Can't instantiate abstract class

def test_adapter_capabilities_defaults():
    caps = AdapterCapabilities(name="test")
    assert caps.streaming is False
    assert caps.tool_calling is False
    assert caps.max_tokens is None

def test_run_result_has_required_fields():
    result = RunResult(
        output="Hello world",
        exit_code=0,
        wall_time_ms=100.0,
    )
    assert result.output == "Hello world"
    assert result.error is None
    assert result.ttft_ms is None  # Optional
```

**Commands:**
```bash
uv run pytest tests/adapters/test_base.py -v
git commit -am "feat(adapters): define abstract Adapter base class"
```

---

#### Task 2.2: Implement Fake Adapter for Testing

**Files to create:**
- `src/mrbench/adapters/fake.py`
- `tests/fixtures/fake_ollama.py`

**Test:** `tests/adapters/test_fake.py`

```python
# tests/adapters/test_fake.py
"""Test fake adapter for contract testing."""
import pytest
from mrbench.adapters.fake import FakeAdapter

@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()

def test_fake_adapter_detect_returns_true(adapter: FakeAdapter):
    result = adapter.detect()
    assert result.detected is True
    assert result.binary_path == "fake"

def test_fake_adapter_list_models(adapter: FakeAdapter):
    models = adapter.list_models()
    assert "fake-fast" in models
    assert "fake-slow" in models

def test_fake_adapter_run_returns_output(adapter: FakeAdapter):
    result = adapter.run(prompt="Hello", model="fake-fast")
    assert result.exit_code == 0
    assert "Hello" in result.output or result.output != ""

def test_fake_adapter_run_with_delay(adapter: FakeAdapter):
    result = adapter.run(prompt="Test", model="fake-slow")
    assert result.wall_time_ms >= 100  # Simulated delay

def test_fake_adapter_run_error_model(adapter: FakeAdapter):
    result = adapter.run(prompt="Test", model="fake-error")
    assert result.exit_code != 0
    assert result.error is not None
```

**Commands:**
```bash
uv run pytest tests/adapters/test_fake.py -v
git commit -am "feat(adapters): add FakeAdapter for testing"
```

---

#### Task 2.3: Implement Adapter Registry

**Files to create:**
- `src/mrbench/adapters/registry.py`

**Test:** `tests/adapters/test_registry.py`

```python
# tests/adapters/test_registry.py
"""Test adapter registry and discovery."""
import pytest
from mrbench.adapters.registry import AdapterRegistry
from mrbench.adapters.fake import FakeAdapter

@pytest.fixture
def registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(FakeAdapter())
    return reg

def test_registry_get_by_name(registry: AdapterRegistry):
    adapter = registry.get("fake")
    assert adapter is not None
    assert isinstance(adapter, FakeAdapter)

def test_registry_list_all(registry: AdapterRegistry):
    adapters = registry.list_all()
    assert "fake" in [a.name for a in adapters]

def test_registry_detect_all(registry: AdapterRegistry):
    detected = registry.detect_all()
    assert len(detected) >= 1
    assert detected[0].name == "fake"

def test_registry_get_unknown_returns_none(registry: AdapterRegistry):
    adapter = registry.get("nonexistent")
    assert adapter is None
```

**Commands:**
```bash
uv run pytest tests/adapters/test_registry.py -v
git commit -am "feat(adapters): add AdapterRegistry with registration and discovery"
```

---

#### Task 2.4: Implement Subprocess Executor

**Files to create:**
- `src/mrbench/core/executor.py`

**Test:** `tests/unit/test_executor.py`

```python
# tests/unit/test_executor.py
"""Test subprocess executor."""
import pytest
import sys
from mrbench.core.executor import SubprocessExecutor, ExecutorResult

@pytest.fixture
def executor() -> SubprocessExecutor:
    return SubprocessExecutor(timeout=5)

def test_executor_runs_command(executor: SubprocessExecutor):
    result = executor.run([sys.executable, "-c", "print('hello')"])
    assert result.exit_code == 0
    assert "hello" in result.stdout

def test_executor_captures_stderr(executor: SubprocessExecutor):
    result = executor.run([sys.executable, "-c", "import sys; sys.stderr.write('error')"])
    assert "error" in result.stderr

def test_executor_with_stdin(executor: SubprocessExecutor):
    result = executor.run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
        stdin="test input"
    )
    assert "test input" in result.stdout

def test_executor_timeout():
    executor = SubprocessExecutor(timeout=0.1)
    result = executor.run([sys.executable, "-c", "import time; time.sleep(10)"])
    assert result.timed_out is True
    assert result.exit_code != 0

def test_executor_measures_wall_time(executor: SubprocessExecutor):
    result = executor.run([sys.executable, "-c", "import time; time.sleep(0.1); print('done')"])
    assert result.wall_time_ms >= 100
```

**Commands:**
```bash
uv run pytest tests/unit/test_executor.py -v
git commit -am "feat(core): add SubprocessExecutor with timeout and streaming"
```

---

### Phase 3: Real Adapter Implementation (Tasks 3.1–3.2)

---

#### Task 3.1: Implement Ollama Adapter

**Files to create:**
- `src/mrbench/adapters/ollama.py`

**Test:** `tests/adapters/test_ollama.py`

```python
# tests/adapters/test_ollama.py
"""Test Ollama adapter."""
import pytest
from unittest.mock import Mock, patch
from mrbench.adapters.ollama import OllamaAdapter
from mrbench.core.executor import ExecutorResult

@pytest.fixture
def adapter() -> OllamaAdapter:
    return OllamaAdapter()

def test_ollama_adapter_name(adapter: OllamaAdapter):
    assert adapter.name == "ollama"

def test_ollama_detect_when_installed(adapter: OllamaAdapter):
    with patch("shutil.which", return_value="/opt/homebrew/bin/ollama"):
        with patch.object(adapter, "_run_version_check", return_value="0.1.0"):
            result = adapter.detect()
            assert result.detected is True
            assert result.binary_path == "/opt/homebrew/bin/ollama"

def test_ollama_detect_when_not_installed(adapter: OllamaAdapter):
    with patch("shutil.which", return_value=None):
        result = adapter.detect()
        assert result.detected is False

def test_ollama_list_models_parses_output(adapter: OllamaAdapter):
    mock_output = """NAME           ID          SIZE    MODIFIED
llama3.2       abc123      2.0 GB  1 hour ago
mistral        def456      4.0 GB  2 hours ago"""
    
    with patch.object(adapter, "_run_command", return_value=ExecutorResult(
        stdout=mock_output, stderr="", exit_code=0, wall_time_ms=100
    )):
        models = adapter.list_models()
        assert "llama3.2" in models
        assert "mistral" in models

def test_ollama_run_constructs_correct_command(adapter: OllamaAdapter):
    with patch.object(adapter, "_run_command") as mock_run:
        mock_run.return_value = ExecutorResult(
            stdout="Response text", stderr="", exit_code=0, wall_time_ms=500
        )
        result = adapter.run("What is 2+2?", model="llama3.2")
        
        # Verify command construction
        call_args = mock_run.call_args[0][0]
        assert "ollama" in call_args[0]
        assert "run" in call_args
        assert "llama3.2" in call_args
```

**Commands:**
```bash
uv run pytest tests/adapters/test_ollama.py -v
git commit -am "feat(adapters): implement Ollama adapter"
```

---

#### Task 3.2: Implement Discovery Module

**Files to create:**
- `src/mrbench/core/discovery.py`

**Test:** `tests/unit/test_discovery.py`

```python
# tests/unit/test_discovery.py
"""Test binary discovery logic."""
import pytest
from pathlib import Path
from unittest.mock import patch
from mrbench.core.discovery import (
    discover_binaries,
    DiscoveryResult,
    DEFAULT_SEARCH_PATHS,
)

def test_default_search_paths_includes_common_locations():
    paths = DEFAULT_SEARCH_PATHS
    assert "/opt/homebrew/bin" in paths or Path("/opt/homebrew/bin") in [Path(p) for p in paths]

def test_discover_binaries_finds_in_path():
    with patch("shutil.which", return_value="/usr/local/bin/ollama"):
        results = discover_binaries(["ollama"])
        assert len(results) == 1
        assert results[0].name == "ollama"
        assert results[0].path == Path("/usr/local/bin/ollama")

def test_discover_binaries_not_found():
    with patch("shutil.which", return_value=None):
        results = discover_binaries(["nonexistent_binary"])
        assert len(results) == 0

def test_discover_binaries_warns_untrusted_path():
    with patch("shutil.which", return_value="/tmp/sketchy/ollama"):
        results = discover_binaries(["ollama"], trusted_paths=["/usr/local/bin"])
        assert len(results) == 1
        assert results[0].trusted is False
```

**Commands:**
```bash
uv run pytest tests/unit/test_discovery.py -v
git commit -am "feat(core): add binary discovery with trusted path warnings"
```

---

### Phase 4: CLI Commands (Tasks 4.1–4.6)

---

#### Task 4.1: Implement `mrbench doctor`

**Files to create:**
- `src/mrbench/cli/doctor.py`

**Test:** `tests/integration/test_cli_doctor.py`

```python
# tests/integration/test_cli_doctor.py
"""Test mrbench doctor command."""
import pytest
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_doctor_runs_without_error():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0

def test_doctor_shows_python_version():
    result = runner.invoke(app, ["doctor"])
    assert "python" in result.output.lower()

def test_doctor_checks_for_adapters():
    result = runner.invoke(app, ["doctor"])
    # Should mention checking for providers
    assert "provider" in result.output.lower() or "adapter" in result.output.lower()

def test_doctor_json_output():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "python_version" in data
    assert "providers" in data
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_doctor.py -v
git commit -am "feat(cli): implement doctor command with provider checks"
```

---

#### Task 4.2: Implement `mrbench detect`

**Files to create:**
- `src/mrbench/cli/detect.py`

**Test:** `tests/integration/test_cli_detect.py`

```python
# tests/integration/test_cli_detect.py
"""Test mrbench detect command."""
import pytest
import json
from pathlib import Path
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_detect_runs():
    result = runner.invoke(app, ["detect"])
    assert result.exit_code == 0

def test_detect_json_output():
    result = runner.invoke(app, ["detect", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "providers" in data
    assert "detected_at" in data

def test_detect_write_creates_file(tmp_path: Path):
    result = runner.invoke(app, ["detect", "--write", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    
    cache_file = tmp_path / "capabilities.json"
    assert cache_file.exists()
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_detect.py -v
git commit -am "feat(cli): implement detect command with --write and --json"
```

---

#### Task 4.3: Implement `mrbench providers` and `models`

**Files to create:**
- `src/mrbench/cli/providers.py`
- `src/mrbench/cli/models.py`

**Test:** `tests/integration/test_cli_providers.py`

```python
# tests/integration/test_cli_providers.py
"""Test mrbench providers and models commands."""
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_providers_lists_adapters():
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    # Should show at least the fake adapter in test mode
    assert "fake" in result.output.lower() or "ollama" in result.output.lower()

def test_models_requires_provider():
    result = runner.invoke(app, ["models"])
    # Either shows error or lists all providers' models
    assert result.exit_code in [0, 1, 2]

def test_models_with_fake_provider():
    result = runner.invoke(app, ["models", "fake"])
    assert result.exit_code == 0
    assert "fake-fast" in result.output or "fake" in result.output.lower()
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_providers.py -v
git commit -am "feat(cli): implement providers and models commands"
```

---

#### Task 4.4: Implement `mrbench run`

**Files to create:**
- `src/mrbench/cli/run.py`

**Test:** `tests/integration/test_cli_run.py`

```python
# tests/integration/test_cli_run.py
"""Test mrbench run command."""
import pytest
import json
from pathlib import Path
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_run_with_fake_provider(tmp_path: Path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("What is 2 + 2?")
    
    result = runner.invoke(app, [
        "run",
        "--provider", "fake",
        "--model", "fake-fast",
        "--prompt", str(prompt_file),
    ])
    assert result.exit_code == 0

def test_run_outputs_metrics():
    result = runner.invoke(app, [
        "run",
        "--provider", "fake",
        "--model", "fake-fast",
        "--prompt", "-",  # stdin
        "--json",
    ], input="Hello")
    assert result.exit_code == 0
    
    data = json.loads(result.output)
    assert "wall_time_ms" in data
    assert "exit_code" in data

def test_run_with_stream_flag():
    result = runner.invoke(app, [
        "run",
        "--provider", "fake",
        "--model", "fake-fast",
        "--prompt", "-",
        "--stream",
    ], input="Test streaming")
    assert result.exit_code == 0

def test_run_unknown_provider_fails():
    result = runner.invoke(app, [
        "run",
        "--provider", "nonexistent",
        "--model", "x",
        "--prompt", "-",
    ], input="test")
    assert result.exit_code != 0
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_run.py -v
git commit -am "feat(cli): implement run command with provider/model selection"
```

---

#### Task 4.5: Implement `mrbench route`

**Files to create:**
- `src/mrbench/core/router.py`
- `src/mrbench/cli/route.py`

**Test:** `tests/integration/test_cli_route.py`

```python
# tests/integration/test_cli_route.py
"""Test mrbench route command."""
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

def test_route_selects_provider():
    result = runner.invoke(app, [
        "route",
        "--prompt", "-",
    ], input="Hello world")
    assert result.exit_code == 0
    # Should output a provider name
    assert any(p in result.output.lower() for p in ["fake", "ollama", "claude"])

def test_route_explain_shows_reasoning():
    result = runner.invoke(app, [
        "route",
        "--prompt", "-",
        "--explain",
    ], input="Hello world")
    assert result.exit_code == 0
    assert "reason" in result.output.lower() or "because" in result.output.lower()

def test_route_offline_only():
    result = runner.invoke(app, [
        "route",
        "--prompt", "-",
        "--offline-only",
    ], input="Hello")
    assert result.exit_code == 0
    # Should select a local provider

def test_route_json_output():
    result = runner.invoke(app, ["route", "--prompt", "-", "--json"], input="test")
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "provider" in data
    assert "model" in data
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_route.py -v
git commit -am "feat(cli): implement route command with policy engine"
```

---

#### Task 4.6: Implement `mrbench bench` and `report`

**Files to create:**
- `src/mrbench/core/benchmark.py`
- `src/mrbench/cli/bench.py`
- `src/mrbench/cli/report.py`
- `src/mrbench/reporters/markdown.py`
- `suites/basic.yaml`

**Test:** `tests/integration/test_cli_bench.py`

```python
# tests/integration/test_cli_bench.py
"""Test mrbench bench and report commands."""
import pytest
import json
from pathlib import Path
from typer.testing import CliRunner
from mrbench.cli.main import app

runner = CliRunner()

@pytest.fixture
def sample_suite(tmp_path: Path) -> Path:
    suite = tmp_path / "test_suite.yaml"
    suite.write_text('''
name: test-suite
prompts:
  - id: simple
    text: "What is 2 + 2?"
  - id: hello
    text: "Say hello"
''')
    return suite

def test_bench_runs_suite(sample_suite: Path, tmp_path: Path):
    result = runner.invoke(app, [
        "bench",
        "--suite", str(sample_suite),
        "--provider", "fake",
        "--output-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    # Should create output directory with results
    assert (tmp_path / "runs").exists() or any(tmp_path.iterdir())

def test_bench_creates_run_id(sample_suite: Path, tmp_path: Path):
    result = runner.invoke(app, [
        "bench",
        "--suite", str(sample_suite),
        "--provider", "fake",
        "--output-dir", str(tmp_path),
        "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "run_id" in data

def test_report_generates_markdown(sample_suite: Path, tmp_path: Path):
    # First run a benchmark
    runner.invoke(app, [
        "bench",
        "--suite", str(sample_suite),
        "--provider", "fake",
        "--output-dir", str(tmp_path),
    ])
    
    # Find the run ID
    runs_dir = tmp_path
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if run_dirs:
        run_id = run_dirs[0].name
        
        result = runner.invoke(app, [
            "report",
            run_id,
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
```

**Commands:**
```bash
uv run pytest tests/integration/test_cli_bench.py -v
git commit -am "feat(cli): implement bench and report commands"
```

---

### Phase 5: Polish and CI (Tasks 5.1–5.3)

---

#### Task 5.1: Add Remaining Adapters (Stubs)

**Files to create:**
- `src/mrbench/adapters/claude.py`
- `src/mrbench/adapters/codex.py`
- `src/mrbench/adapters/gemini.py`
- `src/mrbench/adapters/goose.py`
- `src/mrbench/adapters/opencode.py`

Each adapter implements the base interface with proper detection and invocation patterns from the discovery matrix.

**Commands:**
```bash
uv run pytest tests/adapters/ -v
git commit -am "feat(adapters): add Claude, Codex, Gemini, Goose, OpenCode adapter stubs"
```

---

#### Task 5.2: Set Up CI/CD

**Files to create:**
- `.github/workflows/ci.yml`

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [macos-latest, ubuntu-latest]
        python-version: ["3.12", "3.13"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.14"
      
      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: uv sync --dev
      
      - name: Run linting
        run: |
          uv run ruff check src tests
          uv run ruff format --check src tests
      
      - name: Run type checking
        run: uv run mypy src
      
      - name: Run tests
        run: uv run pytest tests/ -v --cov=mrbench --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.12' && matrix.os == 'macos-latest'

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

**Commands:**
```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for testing and building"
```

---

#### Task 5.3: Documentation and README

**Files to create:**
- `README.md` (expand)
- `docs/quickstart.md`
- `docs/configuration.md`

**Commands:**
```bash
git commit -am "docs: add quickstart and configuration documentation"
```

---

## 9. Local Development Commands

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <repo-url>
cd model-benchmark
uv sync --dev

# Run tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=mrbench --cov-report=html

# Lint and format
uv run ruff check src tests
uv run ruff format src tests

# Type check
uv run mypy src

# Run CLI locally
uv run mrbench --help
uv run mrbench doctor
uv run mrbench detect --json

# Build package
uv build
```

---

## 10. "Done Means" Checklist

### MVP Complete When:

- [ ] `mrbench doctor` runs and shows system status with Rich formatting
- [ ] `mrbench detect` finds installed CLIs and writes `capabilities.json`
- [ ] `mrbench providers` lists all detected providers
- [ ] `mrbench models ollama` lists Ollama models (if installed)
- [ ] `mrbench run --provider fake --model fake-fast --prompt -` works end-to-end
- [ ] `mrbench run --provider ollama --model llama3.2 --prompt -` works (if Ollama installed)
- [ ] `mrbench route --prompt - --explain` prints routing decision with reasoning
- [ ] `mrbench bench --suite suites/basic.yaml --provider fake` completes without error
- [ ] `mrbench report <run_id>` generates readable Markdown
- [ ] All tests pass: `pytest tests/ -v` (100% of unit tests, 90%+ of integration)
- [ ] No secrets logged in any debug output
- [ ] README has install instructions and quick example
- [ ] CI passes on macOS and Linux

### Quality Gates:

- [ ] Type hints on all public functions
- [ ] `ruff check` passes with zero warnings
- [ ] `mypy src` passes with no errors
- [ ] Test coverage ≥ 80%
- [ ] No `TODO` or `FIXME` in shipped code (only in future roadmap)

---

## 11. Top Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CLI invocation patterns change between versions | Medium | Medium | Version detection + graceful fallback + integration test fixtures |
| Streaming output parsing varies by provider | High | Low | Abstract streaming interface with provider-specific parsers |
| Token counting inaccuracy | Medium | Low | Mark as "estimated", use tiktoken, document limitations |
| PATH hijacking false positives | Low | Medium | Warn but don't block, let user configure trusted paths |
| User has zero AI CLIs installed | Medium | High | Clear error messaging in `doctor`, link to install guides |

---

## 12. Future Roadmap (Post-MVP)

1. **TUI Dashboard** — `mrbench watch` with Rich Live panels for benchmark progress
2. **Parallel Benchmarks** — `--parallel N` flag for concurrent job execution
3. **Cost Tracking** — Opt-in lookup from public pricing, mark as "estimated"
4. **Model Alias Resolution** — `--net` flag to fetch model ID mappings
5. **Plugin System** — Third-party adapters via `entry_points`
6. **HTML Reports** — Interactive charts with Plotly or similar
7. **Prompt Templates** — Variable substitution in suite YAML
8. **Regression Detection** — Compare runs, alert on performance degradation
9. **Export Formats** — CSV, Parquet for data analysis
10. **Shell Completion** — Typer's built-in completion for bash/zsh/fish

---

## Summary

This implementation plan provides a **minimal but complete** MVP for mrbench:

- **8 adapter definitions** (Ollama prioritized, 7 others stubbed)
- **Fake adapter + fixtures** for testing without real CLIs
- **SQLite storage** + file artifacts for durability
- **7 CLI commands** covering discovery, routing, running, and reporting
- **TDD approach** with test-first development for each component
- **CI pipeline** for quality gates and cross-platform testing

The design prioritizes **security** (no secrets in logs, redaction, subprocess safety) and **usability** (Rich output, clear error messages, actionable doctor output).
