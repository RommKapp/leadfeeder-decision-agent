---
name: leadfeeder-decision-orchestrator
description: Run a complete Leadfeeder visitor-to-company investigation from a natural-language objective, including autonomous page choice, mandatory MCP retrieval, complete batching, four supporting stages, and one full-set ranking.
---

# Leadfeeder Decision Orchestrator

Own the complete control loop for this project. Receive the caller's natural-language
visitor-analysis objective, select relevant public pages, choose and call the
no-credit Leadfeeder tools, inspect results, retrieve the complete company set,
and sequence every company through Evidence, ICP Scoring, Rubric, and
Recommendation.

Do not add or launch a runner, CLI, server, application, scheduler, or nested
Codex task. This project-local skill is the runtime.

## Load Before Running

Read completely:

1. `../../../policies/OFFER.md`
2. `../../../policies/ICP.md`
3. `../../../policies/OUTREACH.md`
4. `../../../policies/TOOLS.md`
5. `../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md`

Load each supporting skill immediately before its stage:

- `../leadfeeder-evidence/SKILL.md`
- `../leadfeeder-icp-scoring/SKILL.md`
- `../leadfeeder-rubric/SKILL.md`
- `../leadfeeder-recommendation/SKILL.md`

The business documents define what the company values. Contract `2.0` defines
handoff shapes. This skill alone owns page choice, MCP tool choice, date
chunking, pagination, deduplication, batching, retries, stage sequencing, and
completion accounting.

## Understand The Objective

Build one `REQUEST_ROUTING` envelope that preserves the user's actual business
objective. Do not force the request into cohort, assessment, or comparison
modes.

Extract any account, period, named companies, and explicit pages. Use a
reasonable stated default for harmless omissions other than the account. When
the caller selects an accessible account, use it. When the account is omitted,
use `get_account_info` to discover the accessible accounts and proceed only if
exactly one account is available. If account selection remains absent or
ambiguous, ask the caller to choose; never substitute a project or remembered
default. Ask another question only when the answer would materially change the
retrieved population or its interpretation; there is no arbitrary clarification
count.

This skill handles visitor-to-company sales and marketing analysis. A request
outside that bounded domain stops visibly as `UNSUPPORTED_OBJECTIVE` without
calling Leadfeeder.

## Select Commercially Relevant Pages

Choose pages from the user's objective rather than defaulting to pricing. Use
any combination of:

- pages the caller named;
- relevant rules in existing Custom Feeds;
- public web search and public site navigation;
- additional public pages that materially serve the objective.

Public research is for page discovery and commercial interpretation only. It
never proves that a company visited.

Pages may include roots, multiple public hosts, and any number justified by the
objective. Exclude private, local, credential-bearing, or non-public URLs. Do
not treat product-app or internal telemetry as buyer activity unless the
objective explicitly concerns product usage.

For each selected page, record the URL, why it matters, selection origin, filter
value, and honest scope. Choose the supported page operator that matches the
question:

- `IS` only for an exact-page claim;
- `BEGINS_WITH` for a path family;
- `CONTAINS` for a deliberately broader substring;
- `OTHER` only when a currently verified Leadfeeder filter supports it.

A broad operator is not unsafe merely because it is broad. Describe what it can
and cannot establish.

## Require Leadfeeder MCP

Visitor analysis cannot complete from public web evidence. The following
project tools must be available as needed:

- `get_account_info` and `usage`;
- `get_web_visits_custom_feeds` and `get_web_visits_custom_feed`;
- `get_web_visits_companies` and `search_web_visits`;
- `search_companies` and `match_companies`;

Do not stop because the remote server exposes additional tools; use only the
project-configured surface. Missing MCP or a missing required read produces a
`SOURCE_GATE: STOP` with `CONNECTOR_UNAVAILABLE`. Do not replace it with
public research, a browser session, direct REST, a subprocess, or nested Codex.

Resolve the selected account with `get_account_info` before account-scoped
reads. Keep every account-scoped call in the run bound to that account. If an
explicit account is inaccessible or cannot be uniquely resolved, stop and ask
the caller to select an accessible account.

## Choose The Read Path

Inspect existing Custom Feeds and their details when their rules may represent
the selected pages. Reuse a suitable feed and describe its filter scope
accurately; exact, prefix, and substring feeds are all eligible when they match
the objective.

For broad discovery or "whom should I outreach?" objectives without an
explicit page restriction, candidate intake must use the complete population
of companies with at least one public, non-app website visit in the selected
period. Page-specific feeds, including pricing or other high-intent feeds, may
contribute scoring evidence but must not be the sole candidate source. Include
both identified and unidentified company visits unless the user explicitly
asks to narrow them.

If no existing feed is suitable, use only the read-only fallback: retrieve
visiting companies for the period, then use company-filtered
`search_web_visits` where needed to establish selected-page membership from
visit records. Do not create, update, or delete a Custom Feed. Every Source
Reference must therefore keep `created_during_run: false`.

Use `search_companies` or `match_companies` to resolve named-company inputs
from the fields the caller actually supplied. Process the full named set; do not
sample it or request narrowing merely because it is large.

### Control Every Custom Feed Candidate Source

Whenever candidate intake uses one or more Custom Feeds, make one unfiltered
control read for every date chunk. Call `get_web_visits_companies` with the same
account, start date, and end date, omit `custom_feed_id` and `include`, and use
`page_num: 1` with `page_size: 1`. Consume only its pagination metadata. The
returned row is not a candidate source and must not be forwarded to the
supporting stages merely because it appeared in the control.

Require valid `total_count` and `page_count` metadata from every control read,
and count each call in the run's read counters. Apply the same bounded retry
rule as other no-credit reads. If a control remains incomplete, stop as
`CONTROL_READ_INCOMPLETE`; do not interpret the filtered result as empty.

After all selected Custom Feed paths and their controls are complete:

- if the combined filtered candidate population is zero while any matching
  unfiltered control has `total_count > 0`, stop before Evidence, ICP Scoring,
  Rubric, and Recommendation as `FILTERED_SOURCE_EMPTY`;
- say that the selected feed or its rules returned no companies while the
  account had visiting-company records in the same period, so the filtered
  source may be empty or mismatched;
- never turn that state into "the account has no companies", "there was no
  traffic", or another account-wide empty-data claim, and do not automatically
  widen the period solely because the feed was empty;
- if every filtered path and every unfiltered control is zero, report only that
  Leadfeeder returned no visiting-company records for that account and period.
  This does not prove that the site had no traffic.

If the filtered candidate population is non-zero, continue normally. This
control protects interpretation; it does not broaden the requested cohort or
authorize a different source.

## Use MCP Responses Directly

Call approved reads normally. Their responses may enter transient model context
and may be supplied to Evidence with a contract `Raw Response Reference`.
There is no projection, redaction, or safe-field wrapper gate.

Do not write credentials, tokens, raw account exports, raw visitor/contact
datasets, generated dumps, or live response copies to the repository, fixtures,
logs, or reports. Do not surface personal visitor fields in the final
company-level answer when they are unnecessary to the objective.

## Normalize Periods And Retrieve Completely

Resolve the requested period in the selected account timezone. For an omitted
period, state the reasonable business window chosen. Split longer periods into
inclusive chunks that the current tool can reliably accept; use chunks of at
most 31 calendar days unless a freshly verified schema supports a larger
request. A 90-day or longer objective is therefore multiple retrieval chunks,
not a refusal.

Retrieve until each path is exhausted:

- `get_web_visits_companies`: request up to 100 items, start at page 1, and
  continue through the reported `page_count`;
- `search_web_visits`: request up to 100 items and continue through its
  reported page count;
- `search_companies`: follow `next_cursor` until it is absent;
- `match_companies`: divide the supplied named set only when the current
  payload or context requires it, then merge every response.

Record date-chunk and pagination state in contract `2.0`. On a transient read
failure, retry the same no-credit read up to two times with the same account,
filters, and period. Do not convert a failed page into an empty result. If the
provider remains unavailable, preserve completed chunks/pages and report the
exact remaining work.

Merge results from every page, chunk, source, and named-set batch. Deduplicate
by stable Leadfeeder company ID while retaining all source, page, period, and
raw-response provenance. Never treat company label alone as identity.

## Build Complete Processing Batches

Create deterministic sequential batches sized for the current payload and
context. Batch size is an execution choice, not a product cap. Every
deduplicated company must appear in exactly one processing batch, and processing
continues until all batches are terminal.

For every company:

1. invoke Evidence with that company's relevant transient MCP material and
   provenance;
2. invoke ICP Scoring after Evidence even when Evidence produced few or zero
   assessable items, or record its rejected invocation if the corrected
   Evidence handoff is still structurally invalid;
3. invoke Rubric on the valid Evidence and Scoring results or on their terminal
   structural-attempt trace;
4. perform only the bounded repair Rubric requests, then revalidate;
5. retain one closed Terminal Company Trace for Recommendation.

Low coverage never skips Scoring. Zero assessable weight must reach Scoring and
produce its explicit null-score result. A company-level failure remains visible
and does not stop other batches. A structurally invalid supporting handoff may
receive one correction request with the identical input and no MCP call; if it
is still invalid, do not consume or fabricate that envelope. Invoke the
remaining supporting stages in order, record each invocation as
`INVALID_ENVELOPE` or `INPUT_REJECTED`, and let Rubric validate the upstream
failure trace when it can emit a valid result. Mark the completed company trace
`CONTRACT_FAILED` and continue. The trace must contain exactly one Evidence,
Scoring, and Rubric attempt record; an attempt count may include the one
contract correction.

After every company is terminal, invoke Recommendation exactly once with the
entire deduplicated population and all completed batch records. Never rank or
truncate per batch.

## Cost And External-Action Boundary

Track read calls, paid calls, known credit spend, and mutations from zero.
Accepted analysis must finish with:

- `paid_calls: 0`;
- `known_credit_spend: 0`;
- `mutations: 0`.

Never call full-company detail, financial, IP, signal, contact, enrichment, or
other credit-consuming tools. Missing evidence stays unknown. Use
`get_account_info` or `usage` when a before/after no-credit check materially
helps verify the zero-paid claim.

Never create or change a Custom Feed, CRM record, list, tag, campaign,
workflow, enrichment, outreach, or any other external state. There are no
exceptions or approval paths for mutations in this profile.

## Contract Validation

Validate every envelope against contract `2.0` before consuming it:

- exact top-level and payload keys;
- types, enums, nullability, uniqueness, and run/company linkage;
- page, source, date-chunk, pagination, raw-response, and evidence references;
- monotonic completion counts and tool counters.

Contract `2.0` retains the closed legacy Source Gate fields
`feed_creation_impact` and `creation_approved`; under this read-only profile
they must always be `null` and `false`, respectively.

This is structural validation. Rubric owns semantic validation and bounded
repair. Do not copy Scoring, Rubric, or Recommendation algorithms into this
skill.

## Fixture Mode

Use fixture mode only when the caller explicitly asks for a labelled file under
`../../../tests/fixtures/leadfeeder-decision/`. Require
`LOCAL_TEST_FIXTURE — not Leadfeeder evidence`, no real Leadfeeder or personal
data, and zero MCP/public-web calls. Exercise the same contract and supporting
stages; never represent fixture outcomes as live evidence.

## Visible Result

Return a concise business-readable answer before any optional technical trace:

1. outcome and one consolidated full-set ranking;
2. selected pages and why they were relevant;
3. requested period, date chunks, sources, retrieved/deduplicated/evaluated/
   failed/remaining counts, and batch completion;
4. score, coverage, confidence, decision, evidence, unknowns, and human action
   for every company;
5. MCP read, paid, credit, and mutation counters plus any external interruption;
6. one practical next action for the caller.

Do not dump raw MCP responses or hidden reasoning. Return contract JSON only
when the caller explicitly asks for a technical trace, and include the terminal
`FINAL_DECISION` exactly once.
