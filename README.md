# mrbench

**Model Router + Benchmark** — A CLI-first tool to route prompts to existing AI CLIs and benchmark them.

## Features

- 🔍 **Auto-discover** installed AI CLIs (Ollama, Claude Code, Codex CLI, Gemini CLI, etc.)
- 🔀 **Route** prompts to the best available backend based on constraints
- 📊 **Benchmark** across multiple providers with detailed metrics
- 📝 **Report** results in Markdown with comparisons
- 🔒 **Privacy-first** — prompts sent via stdin (not argv), prompt previews not persisted unless requested, secrets auto-redacted
- 🔐 **Safe discovery defaults** — auth checks run only when explicitly requested
- 🤖 **Machine-safe JSON** — all `--json` commands emit strict JSON on stdout (no Rich wrapping)

## Installation

```bash
# Using uv (recommended)
uv pip install mrbench

# Or from source
git clone https://github.com/yourusername/mrbench
cd mrbench
uv sync
```

## Quick Start

```bash
# Check what's installed
mrbench doctor

# Detect available providers
mrbench detect

# Discover tool/config status (no auth checks by default)
mrbench discover

# Include auth checks explicitly when needed
mrbench discover --check-auth

# Run a prompt
echo "What is 2 + 2?" | mrbench run --provider ollama --model llama3.2 --prompt -

# Auto-route to best provider
echo "Explain quantum computing" | mrbench route --prompt - --explain

# Run a benchmark suite
mrbench bench --suite suites/basic.yaml

# Generate report
mrbench report <run_id>
```

## Commands

| Command | Description |
|---------|-------------|
| `mrbench doctor` | Check prerequisites and show detected providers |
| `mrbench detect` | Run discovery and record capability snapshot |
| `mrbench discover` | Discover AI CLI tools/configs (`--check-auth` for auth probes) |
| `mrbench providers` | List detected providers/adapters |
| `mrbench models [provider]` | List available models for a provider |
| `mrbench run` | Run a single prompt against a provider |
| `mrbench route` | Choose best provider based on constraints |
| `mrbench bench` | Run benchmark suite across providers |
| `mrbench report` | Generate summary report for a run |

### JSON Contract

When `--json` is supplied, commands emit strict JSON to stdout that can be parsed directly with `json.loads(...)`.

### Timeout Behavior

`mrbench run --timeout <seconds>` is enforced per invocation across all adapters.

### Prompt Storage Policy

Benchmark runs do not persist `prompt_preview` metadata by default.  
When `--store-prompts` is enabled, prompt previews are persisted in redacted form and full prompt files are written to run artifacts.

### Typing Policy (Current)

CI gates on `mypy src`. A non-blocking informational check runs `mypy src tests` while test typing debt is reduced incrementally.

## Configuration

Config file: `~/.config/mrbench/config.toml`

```toml
[general]
timeout = 300
store_prompts = false

[routing]
default_policy = "preference"
preference_order = ["ollama", "claude", "codex", "gemini"]

[providers.ollama]
enabled = true
default_model = "llama3.2"
```

## License

MIT
