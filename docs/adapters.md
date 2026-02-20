# Adapters

mrbench uses adapters to interface with different AI CLI tools and API providers. Each adapter handles detection, model listing, and prompt execution for its provider.

## CLI Adapters

| Adapter | Binary | Detection | Invocation |
|---------|--------|-----------|------------|
| `fake` | (builtin) | Always detected | Returns mock responses for testing |
| `ollama` | `ollama` | `ollama --version` | `ollama run <model>` (prompt via stdin) |
| `claude` | `claude` | `claude --version` | `claude -p - --output-format text` |
| `codex` | `codex` | `codex --version` | `codex exec -` |
| `gemini` | `gemini` | `gemini --version` | `gemini -p -` |
| `goose` | `goose` | `goose --version` | `goose run -` |
| `opencode` | `opencode` | `opencode --version` | `opencode -p - --quiet` |
| `llamacpp` | `llama-cli` | `llama-cli --version` | `llama-cli -m <model> -p -` |
| `vllm` | `vllm` | `vllm --version` | `vllm complete --quick -` |

## API Adapters

API adapters require the optional `api` extra:

```bash
pip install mrbench[api]
```

| Adapter | Environment Variable | Default Models | Features |
|---------|---------------------|----------------|----------|
| `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo` | Streaming, tool calling |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-*`, `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku` | Streaming, tool calling |

### API Key Setup

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic  
export ANTHROPIC_API_KEY=sk-ant-...

# Or pass directly in code
adapter = OpenAIAdapter(api_key="sk-...")
adapter = AnthropicAdapter(api_key="sk-ant-...")
```

## Adding a New Adapter

1. Create `src/mrbench/adapters/<name>.py`
2. Inherit from `Adapter` base class
3. Implement required methods:
   - `name` (property): unique identifier
   - `detect()`: check if CLI is installed
   - `list_models()`: return available models
   - `run(prompt, options)`: execute prompt
   - `get_capabilities()`: return AdapterCapabilities
4. Register in `registry.py` in `get_default_registry()`

## Adapter Status

Adapters gracefully handle missing binaries:

- `detect()` returns `DetectionResult(detected=False, error="<binary> not found")`
- `run()` returns `RunResult(exit_code=127, error="<binary> not found")`

All adapter runs receive a per-invocation timeout from `RunOptions.timeout`, so `mrbench run --timeout` is enforced consistently.

### Example: Goose (Not Installed)

```python
# From goose.py - handles missing binary gracefully
def detect(self) -> DetectionResult:
    binary = self._get_binary()
    if not binary:
        return DetectionResult(detected=False, error="goose binary not found")
    # ... detection logic if found
```

## Fake Adapter Models

For testing, the fake adapter provides these models:

- `fake-fast`: Returns response immediately
- `fake-slow`: Waits 100ms before responding
- `fake-error`: Returns exit code 1 with error
- `fake-stream`: Streams response in chunks
