---
name: leadfeeder-recommendation
description: Map the complete deduplicated terminal Leadfeeder population to decisions and human actions, produce one full-set ranking, and return only contract-2.0 FINAL_DECISION JSON. It never calls tools.
---

# Leadfeeder Recommendation

Return exactly one `FINAL_DECISION` JSON envelope conforming to
[`../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md`](../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md).
Use the product and human-follow-up meaning in
[`../../../policies/OFFER.md`](../../../policies/OFFER.md) and
[`../../../policies/OUTREACH.md`](../../../policies/OUTREACH.md). This skill is
the sole owner of decision mapping, suggested human action, full-set ordering,
and ranks. Do not call MCP, public web, another skill, or any other tool. Do not
fetch, enrich, repair, rescore, mutate external state, or emit prose outside the
JSON object.

## Input boundary

Accept one orchestrator-provided, structurally validated contract-`2.0` run
containing:

- the `REQUEST_ROUTING`, `SOURCE_GATE`, and complete `CANDIDATE_INTAKE`
  envelopes;
- every valid terminal Evidence, Scoring, Rubric, and optional Repair envelope
  that was actually produced;
- one closed Terminal Company Trace per deduplicated `candidate_id`, including
  the outcome of every Evidence, Scoring, and Rubric invocation;
- one traceable company label or null per candidate;
- the final status of every processing batch.

All objects must share one `run_id`. The terminal company IDs must equal the
complete deduplicated candidate set exactly: no omission, duplicate, sample,
top-N subset, or per-batch subset is valid. Every evidence ID belongs to its
item's company. Every valid-envelope attempt resolves to its same-company
envelope. An `INVALID_ENVELOPE` or `INPUT_REJECTED` attempt carries no
fabricated envelope; its trace reason codes are the only admissible basis for
the failed-chain mapping. Do not invent a company, label, score, Rubric result,
fact, timestamp, unknown, or reason.

Require Intake `retrieval_complete: true`, every processing batch terminal,
and every deduplicated candidate terminal before producing the result. An
external interruption before that point remains Orchestrator-owned incomplete
work; do not rank a partial population.

Only accept cumulative counters that reconcile with Source Gate and Intake and
have `paid_calls: 0`, `known_credit_spend: 0`, and `mutations: 0`. Source Gate
must also keep the legacy closed fields `feed_creation_impact: null` and
`creation_approved: false`, and every source must have
`created_during_run: false`. Any mutation or creation approval makes the input
invalid. Copy the final Intake counters unchanged into the output.

## Deterministic decision and human action mapping

Apply this precedence to every terminal company:

1. A Terminal Company Trace containing an invalid or rejected stage, a final
   Rubric `FAIL`, or an unsuccessful repair
   maps to `INSUFFICIENT_EVIDENCE`, score and band null, coverage `0`,
   confidence `NONE`, human action `Review the invalid or missing no-credit
   evidence before making a sales decision.`, and a supported failure reason
   and stop code.
2. After a Rubric `PASS`, any explicit Scoring disqualifier maps to
   `NO_ACTION`, with score and band null, the Scoring-owned coverage across
   assessable non-disqualified criteria, its corresponding confidence (or
   `NONE` at zero coverage), human action `Leave this account alone; do not
   pursue outreach from this analysis.`, reason `NO_ACTION_DISQUALIFIER`, and
   stop reason `NO_ACTION_DISQUALIFIER`.
3. After a Rubric `PASS`, `total_score: null` maps to
   `INSUFFICIENT_EVIDENCE`, score and band null, the validated coverage and
   confidence, human action `Review the missing no-credit evidence before
   making a sales decision.`, reason `NO_ASSESSABLE_EVIDENCE`, and stop reason
   `INSUFFICIENT_EVIDENCE`.
4. `HIGH_FIT` with `HIGH` or `MEDIUM` confidence maps to `REVIEW` and human
   action `Review the account and its evidence before deciding whether
   relevant, respectful outreach is warranted.`
5. `HIGH_FIT` with `LOW` or `VERY_LOW` confidence, and `MEDIUM_FIT` with
   `HIGH`, `MEDIUM`, `LOW`, or `VERY_LOW` confidence, maps to `MONITOR` and
   human action `Wait for stronger or fresher context, then reassess the
   account.`
6. `LOW_FIT` with `HIGH`, `MEDIUM`, `LOW`, or `VERY_LOW` confidence maps to
   `NO_ACTION` and human action `Leave this account alone; do not pursue
   outreach from this analysis.`

Rules 4-6 use reason and stop code `DECISION_COMPLETE`. A `NONE` confidence
with a numeric score, or any other combination not supported by a passing
Rubric, maps conservatively to `INSUFFICIENT_EVIDENCE` with the invalid-state
action in rule 1 and `UNSUPPORTED_SCORING_STATE`. Never interpret a visit as
buyer intent, choose a contact, draft or send outreach, or change an external
system.

Set `rubric_result` to the terminal valid Rubric outcome. If Rubric did not
produce a valid envelope, use `NOT_COMPLETED`; do not relabel a missing Rubric
result as `FAIL`. For a failed chain use only same-company evidence IDs that
remain traceable; never promote a defective numeric value into the final item.
For every other item copy the validated Scoring score, band, coverage,
confidence, unknown codes, and supported reason codes. Start its evidence IDs
with the validated Scoring evidence IDs, then append in stable Evidence order
the dedicated engagement-ranking Evidence IDs actually used below, removing
duplicates. This preserves the ranking basis without changing any score or
criterion result. Each item must include all and only the contract-`2.0` Final
Item fields.

## One complete-set ranking

Sort the entire terminal population once, after every batch is terminal, using
these keys in order:

1. decision priority: `REVIEW`, `MONITOR`, `INSUFFICIENT_EVIDENCE`,
   `NO_ACTION`;
2. present score before null, then score descending;
3. confidence: `HIGH`, `MEDIUM`, `LOW`, `VERY_LOW`, `NONE`;
4. commercial engagement strength from the same-company, in-period dedicated
   Evidence fields emitted by Evidence: count distinct non-empty string values
   of `qualifying_commercial_visit_id` only when classified `OBSERVED`, sorting
   a present count before missing and then descending; next count distinct
   non-empty string values of `qualifying_canonical_public_url` only when
   classified `INFERRED`, again sorting present before missing and then
   descending. Deduplicate values across Raw Response References. Do not use
   raw pageview volume, aggregate visit/page counts, repeated events, or any
   other field as a substitute;
5. most recent `observed_at` descending among same-company Evidence Items that
   actually support Scoring or supply the dedicated ranking values above, with
   a missing timestamp after a present one;
6. `company_id` ascending.

Assign contiguous positive ranks `1..N` after sorting. Apply this one algorithm
to every objective and every population size. There is no single-company rank
exception, request-mode exception, per-batch ranking, top-ten limit, truncation,
or sampling. A source period boundary is not an activity timestamp.

## Final envelope

Return the exact common-envelope keys with `schema_version: "2.0"`, stage
`"FINAL_DECISION"`, `company_id: null`, `status: "STOP"`, and
`next_stage: null`. Set envelope `evidence_ids` and `unknown_codes` to the
unique unions across all ranked items.

The payload contains exactly the contract fields:

- copy `objective` from Routing;
- copy `account_id`, `account_name`, `selected_pages`, `sources`, and `period`
  from Source Gate;
- set `counts.retrieved` to Intake `raw_candidate_count`,
  `counts.deduplicated` to Intake `deduplicated_candidate_count`, and
  `counts.evaluated` to the number of ranked items;
- set `counts.insufficient_evidence` to the number of
  `INSUFFICIENT_EVIDENCE` items, `counts.failed` to the number of failed
  terminal chains, and `counts.remaining` to deduplicated minus evaluated;
- copy the terminal batch records into `batch_completion` and set
  `ranking_scope: "FULL_DEDUPLICATED_SET"`;
- include every company in `ranked_items` and copy the verified cumulative
  `tool_counters` unchanged;
- use `batch_stop_reason: null` when the entire deduplicated population is
  terminal;
- make `batch_summary` a concise factual summary of completeness, decisions,
  failures, remaining work, and the zero-paid/allowed-mutation counters.

For a complete invocation, ranked-item count equals the deduplicated count and
`remaining` is `0`, even when individual companies failed or have insufficient
evidence. A failed company stays visible, and other batches remain unaffected.
Recommendation does not emit a partial-set ranking.

For every valid invocation, emit one closed contract-`2.0` JSON object and
nothing else.
