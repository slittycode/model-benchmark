# mrbench

**Model Router + Benchmark** — A CLI-first tool to route prompts to existing AI CLIs and benchmark them.

## Features

- 🔍 **Auto-discover** installed AI CLIs (Ollama, Claude Code, Codex CLI, Gemini CLI, etc.)
- 🔀 **Route** prompts to the best available backend based on constraints
- 📊 **Benchmark** across multiple providers with detailed metrics
- 📝 **Report** results in Markdown with comparisons
- 🔒 **Privacy-first** — prompts not stored by default, secrets auto-redacted

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

# Run a prompt
echo "What is 2 + 2?" | mrbench run --provider ollama --model llama3.2

# Auto-route to best provider
echo "Explain quantum computing" | mrbench route --explain

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
| `mrbench providers` | List detected providers/adapters |
| `mrbench models [provider]` | List available models for a provider |
| `mrbench run` | Run a single prompt against a provider |
| `mrbench route` | Choose best provider based on constraints |
| `mrbench bench` | Run benchmark suite across providers |
| `mrbench report` | Generate summary report for a run |

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
