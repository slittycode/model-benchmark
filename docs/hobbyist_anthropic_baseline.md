# hobbyist_anthropic_baseline

Use this suite to generate practical Anthropic usage evidence for support/quota requests.

Scope:
- lightweight summarization on Haiku
- medium reasoning on Sonnet
- deep evaluation on Opus

This profile is intentionally hobbyist scale and should not be presented as enterprise throughput evidence.

## Prerequisites

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv sync --extra api
```

## Run Commands

Run the suite and capture the run id:

```bash
RUN_ID=$(uv run mrbench bench \
  --suite suites/hobbyist_anthropic_baseline.yaml \
  --provider anthropic \
  --output-dir out \
  --json | jq -r '.run_id')
echo "$RUN_ID"
```

Generate a machine-readable report:

```bash
uv run mrbench report "$RUN_ID" --output-dir out --format json > "out/$RUN_ID/report.json"
```

Generate an AWS Support attachment markdown:

```bash
uv run mrbench report "$RUN_ID" --output-dir out --format aws-support-markdown
```

Generated files:
- `out/<run_id>/run_meta.json`
- `out/<run_id>/report.json` (when redirected)
- `out/<run_id>/report_aws_support.md`

## How To Interpret For Quota Requests

- `latency_ms`: observed responsiveness by provider for this hobbyist workload mix.
- `token_usage`: real input/output demand from this suite; use this to justify requested token capacity.
- `error_rate`: failed jobs / total jobs; useful to show reliability pressure when limits are too tight.
- `fallback_rate`: jobs requiring a fallback model; useful to show where primary model allocation is insufficient.

Recommended framing in support tickets:
- state this is a hobbyist baseline (not enterprise traffic),
- include the `report_aws_support.md` attachment,
- request quota proportional to observed token usage plus modest headroom.
