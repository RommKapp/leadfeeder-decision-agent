# AGENTS.md

## Purpose and startup

This private repository is a local, read-only Leadfeeder decision workflow for
review and evaluation. Keep changes small and within the requested scope.

At the start of relevant work, read:

1. this file and `README.md`;
2. `pyproject.toml`, `.codex/config.toml`, and the relevant application files;
3. `policies/` and
   `specs/001-evidence-gated-decision/contracts/stage-handoffs.md`;
4. the orchestrator skill and only the supporting skills needed for the task;
5. the latest one to three entries at the top of `CHANGELOG.md`; search older
   history only when needed.

The five skills, policy files, and handoff contract are one bundle. Decision
logic belongs in its named skill, not in the FastAPI bridge.

## Runtime boundary

- The supported application path is ChatKit -> FastAPI -> official Python
  Codex SDK -> project-scoped Leadfeeder MCP.
- The app reuses the active same-host Codex authentication. It must not read or
  copy Codex credentials, accept an API key in the UI, or create another
  credential store.
- Do not add Claude, a direct OpenAI/Anthropic API runtime, provider abstraction,
  custom OAuth flow, REST fallback, JSON-RPC/App Server client, database,
  scheduler, persistent history, or remote hosting without explicit approval.
- Preserve the configured `gpt-5.6-sol` model and `max` reasoning unless a model
  change is explicitly requested.

## Data and action safety

- Preserve the exact read-only Leadfeeder tool and OAuth-scope allowlists in
  `.codex/config.toml`. Do not expose a write, paid, enrichment, contact,
  export, CRM, campaign, or outreach capability.
- Preserve the app's localhost binding, read-only sandbox, deny-all approval
  mode, source gates, evidence gates, and explicit abstention behavior.
- Separate observed facts, inferences, hypotheses, and unknowns. Do not replace
  Leadfeeder evidence with public-web assumptions.
- Never commit or print OAuth tokens, API keys, credentials, raw visitor or
  contact exports, private account data, or generated dumps.

## Models, Git, and history

When a task selects, changes, compares, or configures an AI model, verify the
current official provider documentation first. Record the verification date,
source, chosen model, and relevant quality, pricing, availability, or
deprecation trade-off in the change summary or changelog.

Keep the repository private. Before every commit or push, review `.gitignore`
and the staged diff for secrets, private data, raw output, binaries, and large
files. Preserve concurrent changes from other agents and never revert unrelated
work.

Add substantive history newest-first at the top of the History section in
`CHANGELOG.md`; never append a new entry below older history.

## Validation

Run from the repository root after a runtime, skill, policy, or setup change:

```sh
uv sync --locked --python 3.12
uv run --locked python tests/validate_revision3.py
uv run --locked python -m json.tool tests/fixtures/leadfeeder-decision/forward-cases.json >/dev/null
uv run --locked python -m json.tool tests/fixtures/leadfeeder-decision/pipeline-90d-121.json >/dev/null
uv run --locked python -m json.tool tests/fixtures/leadfeeder-decision/ownership-cases.json >/dev/null
uv run --locked pytest -q
sh -n scripts/run-local.sh
git diff --check
git status --short --branch
```

Also run the system `quick_validate.py` against all five project skills. For a
localhost runtime or setup change, start `./scripts/run-local.sh` and require
`curl -fsS http://127.0.0.1:8000/health` to contain `"ready":true`. Validate
Leadfeeder separately with one bounded read-only prompt without printing its
business-data response.
