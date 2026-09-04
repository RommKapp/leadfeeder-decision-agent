---
name: leadfeeder-icp-scoring
description: Interpret one contract-2.0 Evidence handoff against the human Leadfeeder ICP and deterministically emit criteria, coverage, confidence, score, bands, and scoring disqualifiers. Never call tools or make recommendations.
---

# Leadfeeder ICP Scoring

Score one valid retrieved company after Evidence and return exactly one closed
contract-`2.0` `ICP_SCORING` JSON envelope. This skill owns all evidence
interpretation against the human ICP, criterion states and weights, scoring
disqualifiers, arithmetic, half-up rounding, coverage, confidence, null-score
behavior, and score bands.

Never call MCP, another tool, a browser, a subprocess, or another skill. Never
fetch or normalize evidence, repair a result, choose a decision, rank companies,
or propose a human action.

## Load Before Scoring

Read completely:

- `../../../policies/ICP.md`
- `../../../specs/001-evidence-gated-decision/contracts/stage-handoffs.md`

`ICP_DEMO_V1` defines what an attractive company means in business language.
Contract `2.0` defines the closed handoff shapes. The algorithms in this file
are the sole normative processing rules.

## Input Boundary

Accept one validated contract-`2.0` `EVIDENCE_GATE: PASS` envelope with
`next_stage: "ICP_SCORING"`. Require a non-empty company ID, all Evidence Items
to use that company ID, envelope `evidence_ids` to equal the unique Evidence
Item IDs, and every item reference to resolve within the same run.

Accept zero items, unknown-only items, normalization issues, broad or dynamic
page/source provenance, additional Leadfeeder fields, and any relevant
no-credit Leadfeeder read path. Do not require a request mode, pricing source,
fixed mapping ID, projected record, exact URL operator, minimum coverage, or
named core evidence prerequisite. The same Evidence payload must produce the
same score result regardless of the user's wording or the orchestrator's batch.

If the Evidence envelope is structurally invalid, return control to the
orchestrator for its contract-correction path rather than fabricating evidence
or a score. Normalization issue codes and low or zero evidence are valid routed
input, not structural failure.

## Evidence Interpretation

Interpret semantic field meaning and values against the human ICP. A source
field need not have a Revision 2 name, but its meaning must be unambiguous.
Use only supplied Evidence Items and cite every item used. Never infer from a
company name or identity alone, an absent field, an unrelated location, a
retrieval-window boundary, or unsupported assumptions.

Use evidence strength consistently:

1. Direct `OBSERVED` evidence outranks `INFERRED` evidence.
2. `INFERRED` evidence may support a conservative `PARTIAL`, but cannot by
   itself establish a disqualifier.
3. `UNKNOWN` items never earn points or prove a no-match or disqualifier.
4. Materially conflicting direct evidence for a criterion makes that criterion
   `UNKNOWN` with `CONFLICTING_<CRITERION_ID>` unless one item clearly refers
   to a different time, entity, or semantic field.
5. An explicit current direct fact may supersede an older fact only when the
   timestamps and meanings make that ordering unambiguous.

Interpret the five criteria as follows.

### B2B and website-led fit

- `MATCH`: direct evidence establishes both that the company primarily sells
  to businesses and that its buyer journey materially uses the website.
- `PARTIAL`: evidence establishes only one of those two elements, or an
  unambiguously business-serving industry supports a B2B model without proving
  the full website-led journey.
- `NO_MATCH`: direct evidence establishes a materially different model without
  establishing the consumer-only disqualifier below.
- `UNKNOWN`: the evidence is absent, ambiguous, unknown-only, or materially
  conflicting.

### Company size fit

Prefer a direct employee count. Counts from 50 through 2,000 inclusive are
`MATCH`; other positive counts are `NO_MATCH`. If only a credible range is
available, a range wholly inside 50–2,000 is `MATCH`, a range wholly outside is
`NO_MATCH`, and a range crossing either boundary is `PARTIAL`. Treat separators
and open-ended range notation according to their ordinary numeric meaning.
Unparseable, absent, or conflicting size evidence is `UNKNOWN`. Do not change
the result merely because the source labels a count as estimated.

### Sales-motion fit

- `MATCH`: direct evidence establishes a repeatable B2B sales or marketing
  motion and a revenue team able to act on account-level website signals.
- `PARTIAL`: evidence establishes a revenue team or relevant sales/marketing
  motion but not the complete repeatability and actionability described above.
- `NO_MATCH`: direct evidence establishes that no relevant sales or marketing
  motion exists.
- `UNKNOWN`: the evidence is absent, ambiguous, unknown-only, or materially
  conflicting.

### Behavioral fit

- `MATCH`: direct in-period evidence establishes activity on a selected
  commercially relevant public page.
- `PARTIAL`: aggregate source membership or a broader page filter establishes
  relevant public website activity but not an exact selected-page event.
- `NO_MATCH`: direct evidence establishes that the observed activity does not
  concern a selected commercially relevant public page, without triggering a
  disqualifier.
- `UNKNOWN`: only identity, unlinked activity, out-of-period activity, or
  unknown/ambiguous evidence is available.

Do not turn any visit into buying intent. A selected-page visit establishes
behavioral relevance only.

### Geography fit

Use the company's primary country or region when directly identified. Europe
or North America is `MATCH`; another region is `NO_MATCH`. An inferred but
unambiguous primary geography may be `PARTIAL`. Missing, invalid, multi-region
without a primary company location, or materially conflicting geography is
`UNKNOWN`.

## Scoring Disqualifiers

Apply a disqualifier only from explicit, unambiguous, current `OBSERVED`
evidence. Preserve these fixed codes:

- `B2C_ONLY`: the company is explicitly consumer-only or primarily consumer
  with no business-selling model; mark `B2B_WEB_LED_FIT` `DISQUALIFIED`.
- `NO_RELEVANT_WEB_SIGNAL`: direct evidence establishes that there is no
  relevant selected-page or commercial-site activity in the period; mark
  `BEHAVIORAL_FIT` `DISQUALIFIED`.
- `INTERNAL_TEST_OR_PRODUCT_TELEMETRY`: all matched activity is explicitly
  internal, test, or product-app telemetry rather than public buyer activity;
  mark `BEHAVIORAL_FIT` `DISQUALIFIED`.
- `NOT_SALES_ELIGIBLE`: direct account evidence explicitly marks the company
  ineligible for sales review; mark `SALES_MOTION_FIT` `DISQUALIFIED`.

Do not disqualify from absence, an inference, a broad source alone, an industry
guess, or a stale/contradictory statement. Emit all established disqualifier
codes uniquely. Evaluate the remaining criteria normally, but when any
disqualifier exists set `total_score: null`, `score_band: null`, and include
`SCORING_DISQUALIFIED` in payload `reason_codes`. Coverage still reports the
non-disqualified assessable weight, and confidence follows the normal coverage
bands, including `NONE` only when coverage is zero. Also include
`NO_ASSESSABLE_EVIDENCE` when that weight is zero.

## Fixed Criteria And Points

Emit exactly these criteria in this order:

1. `B2B_WEB_LED_FIT` — `max_points: 25`
2. `COMPANY_SIZE_FIT` — `max_points: 20`
3. `SALES_MOTION_FIT` — `max_points: 20`
4. `BEHAVIORAL_FIT` — `max_points: 25`
5. `GEOGRAPHY_FIT` — `max_points: 10`

Allowed results and points are:

- `MATCH`: full `max_points`;
- `PARTIAL`: exactly half of `max_points`, including `12.5` for a 25-point
  criterion;
- `NO_MATCH`: `0`;
- `UNKNOWN`: `null` and excluded from assessable weight;
- `DISQUALIFIED`: `null` and excluded from assessable weight.

Use `ICP_MATCH`, `ICP_PARTIAL`, or `ICP_NO_MATCH` only for its matching result.
For `UNKNOWN`, use the matching missing code in criterion `unknown_codes`:

- `MISSING_B2B_FIT`
- `MISSING_COMPANY_SIZE`
- `MISSING_SALES_MOTION`
- `MISSING_BEHAVIORAL_FIT`
- `MISSING_GEOGRAPHY`

Add a conflict code when applicable. For `DISQUALIFIED`, cite the direct
evidence and use the disqualifier code as the criterion reason code. Envelope
`unknown_codes` is the ordered unique union of criterion `unknown_codes`.

## Deterministic Calculation

For every result, calculate assessable weight and coverage from the five
criteria:

```text
assessable_weight = sum(max_points for MATCH, PARTIAL, NO_MATCH)
earned_points = sum(points for MATCH, PARTIAL, NO_MATCH)
coverage_pct = assessable_weight / 100 * 100
```

All weights sum to 100, but retain the explicit coverage formula. Map
confidence from coverage even when a disqualifier makes the score null.

If any disqualifier exists, do not calculate a score: return
`total_score: null` and `score_band: null` as specified above. If
`assessable_weight` is also zero, include `NO_ASSESSABLE_EVIDENCE`.

Without a disqualifier, if `assessable_weight` is zero, do not divide. Return
exactly:

- `coverage_pct: 0`;
- `total_score: null`;
- `score_band: null`;
- `confidence: "NONE"`; and
- payload reason code `NO_ASSESSABLE_EVIDENCE`.

Any non-zero assessable weight produces a provisional numeric score, even when
coverage is low. Calculate:

```text
total_score = floor((earned_points / assessable_weight * 100) + 0.5)
```

Half-up rounding is required; do not use banker's rounding. Calculate
programmatically when arithmetic execution is available, but never call an
external tool. Map score bands:

- `HIGH_FIT`: 80–100
- `MEDIUM_FIT`: 60–79
- `LOW_FIT`: 0–59

Map confidence from coverage only:

- `HIGH`: 85–100
- `MEDIUM`: 70–84
- `LOW`: 40–69
- `VERY_LOW`: greater than 0 and less than 40
- `NONE`: 0

Normal numeric scoring includes `SCORING_COMPLETE` in payload `reason_codes`.
The score must always be consumed together with coverage, confidence, unknowns,
and cited evidence.

## Output

For every valid invocation, set `schema_version: "2.0"`,
`stage: "ICP_SCORING"`, `status: "PASS"`, and
`next_stage: "RUBRIC_EVALUATION"`. Preserve `run_id` and `company_id`. Set
envelope `evidence_ids` to the ordered unique IDs cited by criteria or
disqualifiers. Emit no coverage gate, recommendation, decision, rank, repair,
human action, Markdown, or free prose.

Return only this closed shape:

```json
{
  "schema_version": "2.0",
  "run_id": "<evidence run_id>",
  "stage": "ICP_SCORING",
  "company_id": "<evidence company_id>",
  "status": "PASS",
  "evidence_ids": ["<IDs cited by criteria or disqualifiers>"],
  "unknown_codes": ["<ordered unique criterion unknown codes>"],
  "payload": {
    "criteria": [
      {
        "criterion_id": "B2B_WEB_LED_FIT",
        "result": "MATCH",
        "points": 25,
        "max_points": 25,
        "evidence_ids": ["<supporting evidence IDs>"],
        "unknown_codes": [],
        "reason_codes": ["ICP_MATCH"]
      }
    ],
    "disqualifier_codes": [],
    "coverage_pct": 100,
    "total_score": 100,
    "score_band": "HIGH_FIT",
    "confidence": "HIGH",
    "reason_codes": ["SCORING_COMPLETE"]
  },
  "next_stage": "RUBRIC_EVALUATION"
}
```
