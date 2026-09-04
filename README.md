# Leadfeeder Decision Agent

This private reviewer repository contains a local, read-only application that
turns Leadfeeder visitor evidence into an evidence-gated company ranking.

The application runs through **Codex and the reviewer's own Codex
authentication**. It is not a portable OpenAI API, Anthropic API, or Claude
application. Supporting another model runtime requires additional integration
and authentication work; see [Alternative runtimes](#alternative-runtimes).

No Codex credential, API key, Leadfeeder token, or real visitor export is stored
in this repository.

## What it does

For a natural-language visitor-analysis objective, the workflow:

1. selects the relevant Leadfeeder read operations;
2. retrieves the complete candidate population with pagination and
   deduplication;
3. processes every company through Evidence, ICP Scoring, and Rubric stages;
4. produces one complete-set Recommendation and ranking;
5. stops visibly when the source, connector, or evidence is insufficient.

Observed evidence, inference, and unknowns remain separate throughout the
workflow.

## Architecture

```text
Browser / ChatKit
        |
        v
Local FastAPI bridge
        |
        v
Official Python Codex SDK -- existing Codex authentication
        |
        v
Project Leadfeeder MCP -- reviewer completes Leadfeeder OAuth
        |
        v
Orchestrator -> Evidence -> ICP Scoring -> Rubric -> Recommendation
```

The authored value is the Leadfeeder control loop: source and tool choice,
completeness, pagination, deduplication, batching, stage sequencing, evidence
gates, and stopping. ChatKit provides the browser UI, while Codex provides the
generic model and tool runtime.

The five project skills are under `.agents/skills/`. Shared business policy is
under `policies/`, and their closed handoff contract is
`specs/001-evidence-gated-decision/contracts/stage-handoffs.md`.

## Safety profile

This reviewer package is strictly read-only:

- the project Leadfeeder MCP allowlist contains eight no-credit read tools;
- the OAuth scopes are `accounts:read`, `usage:read`, `companies:read`, and
  `web_visits:read`;
- no Custom Feed creation, update/delete, enrichment, contact, export, CRM,
  campaign, or outreach capability is exposed;
- every Codex thread uses a read-only filesystem sandbox and deny-all approval
  mode;
- application and conversation state exist only in process memory.

Codex combines project configuration with configuration already present on the
reviewer's machine. As a required preflight, use `codex mcp list` and ensure no
unrelated personal MCP servers are enabled. The workflow instructions permit
only the project Leadfeeder reads, but a clean reviewer profile gives the
clearest isolation.

## Prerequisites

The tested launcher requires:

- macOS, Git, and network access;
- [uv](https://docs.astral.sh/uv/getting-started/installation/);
- [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) authenticated with the
  reviewer's own ChatGPT account;
- access to the configured `gpt-5.6-sol` model;
- a Leadfeeder account with API/MCP access and a user with the
  `Integrations -> Manage API keys and use API` permission.

The application itself does not read an OpenAI API key. It reuses the active
same-host Codex session. Leadfeeder authentication is a separate OAuth flow.

## Installation and first run

### 1. Clone the private repository

```sh
git clone https://github.com/RommKapp/leadfeeder-decision-agent.git
cd leadfeeder-decision-agent
```

### 2. Install the local tools

If Codex CLI or uv is missing, use their official installers:

```sh
curl -fsSL https://chatgpt.com/codex/install.sh | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Confirm both commands are available:

```sh
codex --version
uv --version
```

### 3. Sign in to Codex

```sh
codex login status
```

If no active session is reported, run `codex login` and complete the browser
sign-in. Codex stores and manages this credential outside the repository. The
official authentication reference is
[Codex authentication](https://learn.chatgpt.com/docs/auth).

### 4. Trust the project configuration

Project-local MCP configuration is loaded only for trusted projects. From this
repository, run:

```sh
codex
```

Accept the workspace trust prompt after reviewing the repository. Once the
Codex prompt opens, exit with `Ctrl+C`.

### 5. Connect Leadfeeder

The repository already declares the remote `leadfeeder` MCP server in
`.codex/config.toml`. Authenticate it with the reviewer's own Leadfeeder
account:

```sh
codex mcp list
codex mcp login leadfeeder
codex mcp list
```

The login command opens the Leadfeeder OAuth flow in a browser. Do not paste a
Leadfeeder token or any other credential into the repository. After login,
`codex mcp list` should show `leadfeeder` as enabled and authenticated. See the
official [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Leadfeeder documents the same OAuth flow and required permission in its
[MCP connection guide](https://help.leadfeeder.com/en/articles/15532431-connect-leadfeeder-to-your-ai-tool-with-the-mcp-server)
and [permissions and credits guide](https://help.leadfeeder.com/en/articles/15532468-leadfeeder-mcp-server-permissions-and-credits).

### 6. Install the pinned Python environment

```sh
uv sync --locked --python 3.12
```

All Python dependencies are installed into the repository-local `.venv`.

### 7. Run deterministic checks

These checks use fictional fixtures and do not call Leadfeeder:

```sh
uv run --locked python tests/validate_revision3.py
uv run --locked pytest -q
```

### 8. Start the application

```sh
./scripts/run-local.sh
```

The launcher binds only to `127.0.0.1:8000`, waits for Codex readiness, and
opens the browser. Keep that terminal open while using the application; press
`Ctrl+C` to stop it.

Check readiness from another terminal:

```sh
curl -fsS http://127.0.0.1:8000/health
```

The response must contain `"ready":true`. This proves that the local Codex
runtime started. A real Leadfeeder question separately verifies the reviewer's
Leadfeeder OAuth and permissions.

## Suggested first check

Start with a bounded, no-credit request such as:

> Confirm that the Leadfeeder connection is available using only a read-only
> account lookup. Do not create, update, enrich, export, or send anything.

Then ask the workflow to investigate a visitor cohort available to the
reviewer's own Leadfeeder account. A missing connector, ambiguous account, or
insufficient evidence should produce an explicit stop rather than a guessed
answer.

## Troubleshooting

- **Codex is unavailable:** run `codex login status`, sign in if necessary, and
  restart the application.
- **`leadfeeder` is missing:** start `codex` once from this folder and accept
  the trust prompt, then retry `codex mcp list`.
- **Leadfeeder OAuth fails:** confirm that the reviewer is allowed to use the
  Leadfeeder API/MCP integration, then rerun `codex mcp login leadfeeder`.
- **The configured model is unavailable:** use a Codex account or workspace
  with access to `gpt-5.6-sol`. Model access is not shared by this repository.
- **Python setup fails:** verify `uv --version`, keep `uv.lock` unchanged, and
  rerun `uv sync --locked --python 3.12`.
- **Port 8000 is busy:** stop the process already using it before starting the
  launcher again.

## Alternative runtimes

This version deliberately depends on Codex and its authentication. Running the
same workflow through Claude, a direct OpenAI API client, or another provider is
not enabled by adding one API key. Such a version would need a replacement
agent/tool loop plus a separately designed and tested Leadfeeder OAuth flow,
token lifecycle, credential storage, and provider-specific error handling.

That work should be treated as a separate implementation revision, not as a
configuration change to this repository.

## Limitations

- localhost and single-user only;
- macOS launcher only;
- ephemeral process-memory conversations;
- no persistent history, accounts UI, deployment, scheduler, or database;
- results are limited to the reviewer's Leadfeeder access and available
  evidence;
- Leadfeeder MCP and OAuth behavior are controlled by Leadfeeder and may change.

## Evaluation terms

No open-source license is granted. This private repository is provided for
evaluation only and must not be redistributed or reused without the owner's
written permission.
