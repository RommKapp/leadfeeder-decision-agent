---
name: leadfeeder-evidence
description: Normalize transient Leadfeeder company evidence, preserve provenance, and classify items as observed, inferred, or unknown for an EVIDENCE_GATE handoff. Never call tools or score ICP fit.
---

# Leadfeeder Evidence

Normalize the relevant transient Leadfeeder material for one retrieved company
and return exactly one closed contract-`2.0` `EVIDENCE_GATE` JSON envelope.
Never call MCP, another tool, a browser, a subprocess, or another skill. Never
interpret ICP fit, calculate coverage or points, apply a disqualifier, decide an
outcome, or skip Scoring because evidence is sparse.

## Load Before Normalizing

Read completely:

- `../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md`
- `../../../policies/TOOLS.md`

Contract `2.0` owns the closed envelope and evidence-item shapes. Tool Policy
defines the transient-data and authority boundary. This skill alone owns
normalization, provenance, `OBSERVED`/`INFERRED`/`UNKNOWN` classification,
raw-response references, and normalization issues.

## Accepted Input

Accept an orchestrator-provided invocation containing:

- one validated contract-`2.0` `SOURCE_GATE: PASS` envelope;
- one validated contract-`2.0` `CANDIDATE_INTAKE: PASS` envelope for the same
  `run_id` whose `candidate_ids` and exactly one processing batch contain the
  non-empty selected `company_id`;
- the relevant direct transient Leadfeeder MCP responses for that company;
- one Raw Response Reference for each supplied response; and
- any run-scoped source, page, period, and response linkage needed to resolve
  those references.

The input may contain fields beyond those known from Revision 2. Do not require
a projection wrapper, safe-field schema, fixed mapping ID, pricing source,
request mode, page operator, or particular MCP response shape. Additional
fields do not make a response unsafe. Normalize relevant company and activity
facts and ignore irrelevant material.

Reject only a structurally invalid invocation: mismatched runs or companies,
an unselected company, unresolved or cross-run provenance, a response without
its Raw Response Reference, duplicate IDs, or a non-contract upstream
envelope. Return control to Orchestrator's contract-correction path without
emitting or inventing an Evidence envelope. Orchestrator records the invocation
outcome in the Terminal Company Trace. Do not repair upstream state or invent
identifiers.

## Normalize Without A Projection Gate

For each response, inspect the whole transient object but retain only facts
material to company identity, company characteristics, location, sales or
marketing context, selected-page/source membership, or website activity.
Never copy credentials, tokens, personal contact details, personal visitor
data, or an entire raw response into an Evidence Item.

Create stable run-scoped evidence IDs deterministically from company ID,
response reference, semantic field, and a stable ordinal when needed. The same
input order and content must produce the same IDs and item order. Preserve
native scalar, object, or array values when they are already meaningful; make
only lossless canonicalizations such as trimming whitespace, normalizing a
country code's case, or representing a numeric employee count as a number.
Lossless canonicalization does not change an otherwise direct item from
`OBSERVED` to `INFERRED`.

Use semantic `field` names that describe the fact rather than the source's
presentation label. Source-specific aliases may normalize to the same semantic
field, but this stage does not map that field to an ICP criterion. Keep
materially different facts as separate items instead of collapsing them.

### Preserve engagement-ranking inputs

When a direct in-period website-visit response exposes a native visit or
session ID and an observed page URL that matches a Source Gate selected public
commercial page, emit these dedicated Evidence Items in addition to any other
material activity facts:

- `qualifying_commercial_visit_id`: one `OBSERVED` string value for each
  distinct native visit or session ID represented in that Raw Response
  Reference; and
- `qualifying_canonical_public_url`: one `INFERRED` string value for each
  distinct qualifying URL in that Raw Response Reference after deterministic
  canonicalization.

Canonicalize a qualifying URL by lowercasing its scheme and host, removing a
default port, and removing its query string and fragment. Preserve the host
and path otherwise: do not merge a bare host with `www`, do not merge distinct
paths, and do not silently collapse trailing-slash variants. Set
`observed_at` to the most recent real source observation represented by that
item when present. Recommendation deduplicates the same value across Raw
Response References, so repeated events and pageviews cannot increase either
ranking count.

Emit these fields only from direct qualifying activity. Do not derive a visit
ID from pageview volume, an aggregate visit count, timestamps alone, or source
membership. Do not emit a canonical URL for application, authenticated,
private, out-of-period, non-selected, malformed, or ambiguous activity. When
otherwise qualifying activity lacks a native visit ID or usable URL, preserve
the remaining evidence and record the applicable missing or invalid condition
instead of inventing a ranking value.

Do not reject or stop the company because one field is unfamiliar, missing,
null, malformed, stale, broad, or contradictory. Preserve usable items and
record the affected condition in `normalization_issue_codes`. Useful issue
codes include:

- `UNRESOLVED_FIELD_MEANING` for a relevant field whose meaning is ambiguous;
- `INVALID_FIELD_VALUE` for a relevant value that cannot be normalized safely;
- `MISSING_FIELD_VALUE` for an explicitly present but absent value;
- `CONFLICTING_OBSERVATIONS` for incompatible direct facts that both retain
  valid provenance;
- `INCOMPLETE_PERIOD_PROVENANCE` when activity lacks the time linkage needed
  to place it confidently in the requested period.

These issues are normalization facts, not ICP conclusions. Do not resolve a
conflict by choosing the more favorable value.

## Classification And Provenance

Classify every Evidence Item independently:

- `OBSERVED`: the Leadfeeder response directly states the value or event.
- `INFERRED`: a conservative, reproducible normalization derives the value
  from one or more direct fields in the same referenced response without
  deciding ICP fit. The item must retain that source and raw-response
  provenance.
- `UNKNOWN`: the response explicitly reports the relevant fact as unknown,
  unavailable, denied, ambiguous, or null. Use `value: null` unless the source
  supplies a meaningful unknown-state value.

Omission alone does not require an invented Evidence Item. When an expected
relevant fact is absent across all supplied responses, add a deterministic
`UNKNOWN_<SEMANTIC_FIELD>` code to the envelope when the missing semantic field
is known. If nothing relevant can be normalized, return zero items and add
`NO_NORMALIZABLE_EVIDENCE` to `unknown_codes` and `reason_codes`.

For every item:

- use the exact selected company ID;
- set `source_tool` to the tool that returned the source response;
- resolve `source_ref` within the same run when one applies;
- resolve `raw_response_ref` to the supplied Raw Response Reference;
- use the source event/observation timestamp for `observed_at` when present,
  otherwise `null` rather than a fabricated activity time; and
- attach the applicable contract Period when the response is period-scoped,
  otherwise `null`.

An inference never upgrades provenance. Do not treat a retrieval-window
boundary or response-receipt time as an observed visit time. Identity is
evidence of identity only. Do not label a company, industry, size, geography,
page membership, or activity as an ICP match, partial match, no-match, or
disqualifier; ICP Scoring owns that interpretation.

## Valid-Company Handoff

Every structurally valid retrieved company produces `status: "PASS"` and
`next_stage: "ICP_SCORING"`, including when:

- `items` is empty;
- every item is `UNKNOWN`;
- relevant values conflict;
- evidence would previously have been considered too sparse to score;
- the source, page set, filter, tool, or additional response fields were not
  known to Revision 2.

Set:

- envelope `evidence_ids` to the unique IDs of all emitted items, in item order;
- envelope `unknown_codes` to unique unknown-state codes in deterministic
  order;
- `raw_response_refs` to the closed references for the supplied responses;
- `normalization_issue_codes` to unique normalization issues in deterministic
  order; and
- `reason_codes` to `EVIDENCE_NORMALIZED`, plus
  `NORMALIZATION_ISSUES_PRESENT` or `NO_NORMALIZABLE_EVIDENCE` when applicable.

Evidence does not calculate assessable weight, coverage, confidence, score,
score band, disqualifiers, decision, ranking, or human action.

## Output

Emit only this closed contract-`2.0` shape, with no Markdown or free prose:

```json
{
  "schema_version": "2.0",
  "run_id": "<upstream run_id>",
  "stage": "EVIDENCE_GATE",
  "company_id": "<selected company_id>",
  "status": "PASS",
  "evidence_ids": ["<all emitted evidence IDs>"],
  "unknown_codes": ["<normalization-owned unknown codes>"],
  "payload": {
    "raw_response_refs": [
      {
        "response_ref": "<run-scoped response reference>",
        "tool": "<Leadfeeder tool name>",
        "received_at": "<ISO-8601 timestamp>",
        "source_ref": "<source reference or null>"
      }
    ],
    "items": [
      {
        "evidence_id": "<stable run-scoped evidence ID>",
        "company_id": "<selected company_id>",
        "classification": "OBSERVED",
        "field": "<semantic field>",
        "value": "<any JSON value>",
        "source_tool": "<Leadfeeder tool name>",
        "source_ref": "<source reference or null>",
        "raw_response_ref": "<raw response reference or null>",
        "observed_at": "<ISO-8601 timestamp or null>",
        "period": "<contract Period object or null>"
      }
    ],
    "normalization_issue_codes": [],
    "reason_codes": ["EVIDENCE_NORMALIZED"]
  },
  "next_stage": "ICP_SCORING"
}
```
