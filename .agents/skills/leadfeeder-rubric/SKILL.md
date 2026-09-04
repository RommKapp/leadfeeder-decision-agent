---
name: leadfeeder-rubric
description: Semantically validate one Leadfeeder Evidence and ICP Scoring result, request at most one bounded correction, and return only contract-2.0 RUBRIC_EVALUATION JSON. It never calls tools or makes a recommendation.
---

# Leadfeeder Rubric

Return exactly one `RUBRIC_EVALUATION` JSON envelope conforming to
[`../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md`](../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md).
Use the business meaning in
[`../../../policies/ICP.md`](../../../policies/ICP.md) and validate the result
against the current rules owned by
[`../leadfeeder-icp-scoring/SKILL.md`](../leadfeeder-icp-scoring/SKILL.md).
Do not call MCP, public web, another skill, or any other tool. Do not fetch data,
consume credits, alter evidence, score a company, make a decision, rank a set,
or emit prose outside the JSON object.

## Input boundary

Accept one orchestrator-provided invocation containing:

- the validated contract-`2.0` `SOURCE_GATE`, `CANDIDATE_INTAKE`, and, when
  produced, `EVIDENCE_GATE` and `ICP_SCORING` envelopes for one company;
- the Evidence Items and provenance objects referenced by every valid supplied
  envelope;
- the upstream Terminal Stage Attempt objects when a corrected Evidence or
  Scoring handoff was structurally invalid or its input was rejected;
- `repair_attempts_used`, the number of Rubric-requested repairs already
  attempted for this company.

Every envelope and reference must share one `run_id`; every company-scoped
object must share one non-null `company_id`. Treat the Scoring skill as the sole
normative source for criterion interpretation, weights, arithmetic, coverage,
confidence, null-score behavior, bands, and scoring disqualifiers. This skill
independently checks the supplied result against those rules; it does not create
an alternative scoring algorithm.

The normal path requires valid Evidence and Scoring envelopes. The structural
failure path requires trace records for both upstream stages and any valid
envelopes that were actually produced; never accept or inspect a malformed
envelope as evidence. An invalid or rejected upstream attempt makes the
applicable checks fail and cannot trigger another contract correction or new
data collection. Rubric still emits its own valid terminal `FAIL` envelope
when its invocation is structurally valid.

Return the exact common-envelope keys with `schema_version: "2.0"`, stage
`"RUBRIC_EVALUATION"`, and the input `run_id` and `company_id`. Set envelope
`evidence_ids` to the unique same-company Evidence IDs examined by the checks.
Set `unknown_codes` to the unique unresolved codes supported by the Evidence
and Scoring inputs. The payload contains exactly `checks`, `repair_request`,
and `repair_attempts_used`.

## Perform exactly five checks

Emit these checks once each and in this order. Every check object contains only
`check_id`, `result`, and `reason_codes`.

1. `EVIDENCE_TRACEABLE`: every Scoring evidence ID resolves to an Evidence Item
   for this company and run; its source, raw-response, page, period, and source
   references resolve upstream; asserted results do not rely on labels,
   unreferenced claims, cross-company evidence, or fabricated provenance.
2. `SCORING_INTERPRETATION_VALID`: every criterion result, points value,
   evidence selection, unknown, and Scoring-owned disqualifier agrees with the
   current ICP Scoring rules and the human ICP meaning. An observed field
   supports only the interpretation that Scoring owns; a visit never becomes
   proof of intent.
3. `SCORE_ARITHMETIC_VALID`: independently recompute the result using the
   current Scoring rules and verify criteria, assessable weight, earned points,
   rounding, `coverage_pct`, `total_score`, `score_band`, and `confidence`.
4. `MISSING_DATA_TREATMENT_VALID`: missing facts remain `UNKNOWN`, use null
   criterion points, carry matching unknown codes, and never trigger invented
   evidence or a paid lookup. Validate low-coverage and null-score states only
   against the current missing-data, coverage, and confidence rules owned by
   Scoring; this skill does not restate those values or thresholds.
5. `RECOMMENDATION_SUPPORTED`: the validated terminal state contains enough
   internally consistent information for Recommendation to apply its own
   deterministic mapping. A valid explicit Scoring disqualifier, a valid null
   score, or a low-confidence score can all support a recommendation state.
   This check does not choose the decision, human action, or rank.

Use concise `SCREAMING_SNAKE_CASE` reason codes. Use
`RUBRIC_CHECK_PASSED` for a passing check and the most specific applicable
failure code among `EVIDENCE_LINK_INVALID`, `SCORING_INTERPRETATION_INVALID`,
`SCORE_ARITHMETIC_INVALID`, `MISSING_DATA_INVALID`,
`NULL_SCORE_STATE_INVALID`, and `RECOMMENDATION_UNSUPPORTED`. Do not add
diagnostic prose or fields.

## Verdict and one bounded repair

- If all five checks pass, return `status: "PASS"`,
  `repair_request: null`, and `next_stage: "FINAL_DECISION"`.
- If exactly one concrete defect can be corrected without new evidence, a tool
  call, a policy change, or a second independent correction, and
  `repair_attempts_used` is `0`, return `status: "NEEDS_REPAIR"` and
  `next_stage: "REPAIR"`. Request exactly one of:
  - `RECALCULATE_SCORE`, targeting `ICP_SCORING`, only when interpretation and
    evidence linkage are valid but arithmetic, coverage, band, confidence, or
    the Scoring-owned null-score state is wrong;
  - `CORRECT_CONTRACT`, targeting the one affected `EVIDENCE_GATE` or
    `ICP_SCORING` stage, only for a local contract/reference inconsistency whose
    correct value is already unambiguous in the supplied validated input.
- Otherwise return `status: "FAIL"`, `repair_request: null`, and
  `next_stage: "FINAL_DECISION"`. This includes unsupported provenance,
  invented facts, ambiguous corrections, multiple independent defects, and any
  still-failing result after `repair_attempts_used >= 1`.

For a repair request, emit exactly `action`, `target_stage`, and the unique
failure codes it targets in `target_codes`. Never request data collection,
company enrichment, a paid read, or a mutation. Never emit a `REPAIR` envelope
or perform the correction yourself. A failed company remains a terminal record
for Recommendation; Orchestrator owns any subsequent batch sequencing.

For every valid invocation, emit one closed contract-`2.0` JSON object and
nothing else.
