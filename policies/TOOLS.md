# Leadfeeder Tool Policy

**Policy ID**: `TOOLS_READ_ONLY_V1`
**Revision**: `10`

## Available Capabilities

Leadfeeder is the required source of visitor and company evidence. The workflow
uses the project-local, OAuth-authenticated Leadfeeder MCP and does not add a
REST adapter or require an API key.
Public web research may help the agent discover and understand commercially
relevant public pages, but it cannot replace Leadfeeder visit evidence.

Use an accessible account explicitly selected by the caller. If none is
selected, discover the accessible accounts with `get_account_info` and proceed
only when exactly one is available; otherwise ask the caller to choose. Never
use a hard-coded, project-specific, or remembered account default.

The project exposes these no-credit, read-only capability contracts:

- account selection and current account credit balance;
- monthly API usage;
- Custom Feed inventory and feed details;
- visiting-company retrieval with company data;
- underlying web-visit search when visit-level evidence is materially useful;
- company search and company matching using basic company information.

The configured tools are `get_account_info`, `usage`,
`get_web_visits_custom_feeds`, `get_web_visits_custom_feed`,
`get_web_visits_companies`, `search_web_visits`, `search_companies`, and
`match_companies`.

## Cost Boundary

Accepted runs use zero paid or credit-consuming calls. Full company detail,
financials, IP addresses, company signals, contact data, enrichment jobs, and
all other credit-bearing capabilities are outside this workflow. Missing data
remains unknown; it does not open a paid branch.

The agent may read the account credit balance or usage to verify that no credit
was spent. Those verification reads are themselves no-credit operations.

## Transient Data Use

Leadfeeder responses may be inspected in transient Codex context and supplied
to the supporting skills. The Codex SDK runtime must not add a second transport,
log raw MCP payloads, or rewrite evidence before the owner skills reason over
it.

Credentials, OAuth tokens, API keys, raw account exports, generated dumps,
contact exports, and personal visitor datasets must not be written to this
repository. Live response content is used for the current run and is not copied
into fixtures or reports.

## External Actions

This profile is strictly read-only. Custom Feed creation/update/delete, CRM
changes, lists, tags, campaigns, workflows, enrichment, outreach, and every
other external mutation are unavailable with no approval exception. Every
accepted run must finish with `mutations: 0`.

Contract `2.0` retains the legacy closed Source Gate fields
`feed_creation_impact` and `creation_approved` for compatibility. Under this
profile they must always be `null` and `false`, respectively; they do not expose
a write path.
