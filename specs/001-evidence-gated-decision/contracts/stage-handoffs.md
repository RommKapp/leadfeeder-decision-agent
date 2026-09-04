# Stage Handoff Contract

**Contract version**: `2.0`
**Compatibility**: breaking replacement for Revision 2 contract `1.2`

This contract defines closed JSON shapes, field types, stage vocabulary,
terminal-state vocabulary, and provenance links. It does not define page
selection, tool order, date chunking, pagination, deduplication, batching,
retries, evidence interpretation, score arithmetic, repair decisions, decision
mapping, or ranking. Those rules belong only to their owner skills.

Every object described here is closed: unlisted fields are invalid. Arrays have
no product-level maximum unless the field explicitly says otherwise. Provider
page sizes and context limits are execution concerns recorded by the
Orchestrator, not contract limits.

## Common Envelope

Every stage handoff contains exactly:

| Field | Type |
|---|---|
| `schema_version` | constant string `2.0` |
| `run_id` | non-empty string |
| `stage` | stage enum |
| `company_id` | non-empty string or `null` |
| `status` | `PASS`, `STOP`, `NEEDS_REPAIR`, or `FAIL` |
| `evidence_ids` | array of unique non-empty strings |
| `unknown_codes` | array of unique non-empty code strings |
| `payload` | the closed stage-specific object |
| `next_stage` | stage enum or `null` |

Stage enums are:

- `REQUEST_ROUTING`
- `SOURCE_GATE`
- `CANDIDATE_INTAKE`
- `EVIDENCE_GATE`
- `ICP_SCORING`
- `RUBRIC_EVALUATION`
- `REPAIR`
- `FINAL_DECISION`

Codes used in `unknown_codes`, `reason_codes`, `stop_reason`, and
`disqualifier_codes` are non-empty `SCREAMING_SNAKE_CASE` strings.
Their operational meaning is owned by the skill that emits them.

## Shared Closed Objects

### Period

| Field | Type |
|---|---|
| `start` | ISO-8601 timestamp |
| `end` | ISO-8601 timestamp |
| `timezone` | IANA timezone string |
| `today_partial` | boolean |

### Selected Page

| Field | Type |
|---|---|
| `page_id` | unique non-empty string within the run |
| `url` | absolute public HTTPS URL |
| `selected_by` | `USER`, `PUBLIC_WEB`, or `EXISTING_SOURCE` |
| `selection_rationale` | non-empty human-readable string |
| `filter_operator` | `IS`, `CONTAINS`, `BEGINS_WITH`, or `OTHER` |
| `filter_value` | non-empty string |
| `scope_label` | `EXACT`, `SUBSTRING`, `PREFIX`, or `OTHER` |

### Source Reference

| Field | Type |
|---|---|
| `source_ref` | unique non-empty string within the run |
| `source_type` | `CUSTOM_FEED`, `VISITING_COMPANIES`, `WEB_VISITS`, or `LOCAL_TEST_FIXTURE` |
| `source_id` | string or `null` |
| `source_name` | string or `null` |
| `page_ids` | array of selected-page IDs |
| `persistent` | boolean |
| `created_during_run` | boolean |

### Date Chunk

| Field | Type |
|---|---|
| `chunk_id` | unique non-empty string |
| `start` | ISO-8601 timestamp |
| `end` | ISO-8601 timestamp |
| `status` | `PENDING`, `COMPLETE`, or `FAILED` |

### Pagination State

| Field | Type |
|---|---|
| `path_id` | unique non-empty string |
| `tool` | non-empty tool-name string |
| `date_chunk_id` | date-chunk ID or `null` |
| `pages_fetched` | non-negative integer |
| `items_received` | non-negative integer |
| `next_cursor` | string or `null` |
| `next_page` | positive integer or `null` |
| `complete` | boolean |
| `error_code` | code string or `null` |

### Processing Batch

| Field | Type |
|---|---|
| `batch_id` | unique non-empty string |
| `company_ids` | array of unique non-empty company IDs |
| `status` | `PENDING`, `COMPLETE`, or `FAILED` |

### Tool Counters

| Field | Type |
|---|---|
| `leadfeeder_read_calls` | non-negative integer |
| `paid_calls` | non-negative integer |
| `known_credit_spend` | non-negative integer |
| `mutations` | non-negative integer |

### Raw Response Reference

| Field | Type |
|---|---|
| `response_ref` | unique non-empty run-scoped string |
| `tool` | non-empty tool-name string |
| `received_at` | ISO-8601 timestamp |
| `source_ref` | source-reference ID or `null` |

A raw response reference identifies transient model-context material. It is not
a repository path, export, dump, or authorization to persist the response.

### Evidence Item

| Field | Type |
|---|---|
| `evidence_id` | unique non-empty string |
| `company_id` | non-empty string |
| `classification` | `OBSERVED`, `INFERRED`, or `UNKNOWN` |
| `field` | non-empty semantic field string |
| `value` | any JSON value |
| `source_tool` | non-empty tool-name string |
| `source_ref` | source-reference ID or `null` |
| `raw_response_ref` | raw-response-reference ID or `null` |
| `observed_at` | ISO-8601 timestamp or `null` |
| `period` | Period object or `null` |

### Terminal Stage Attempt

| Field | Type |
|---|---|
| `stage` | `EVIDENCE_GATE`, `ICP_SCORING`, or `RUBRIC_EVALUATION` |
| `outcome` | `VALID_ENVELOPE`, `INVALID_ENVELOPE`, or `INPUT_REJECTED` |
| `attempt_count` | positive integer |
| `envelope_status` | `PASS`, `STOP`, `NEEDS_REPAIR`, `FAIL`, or `null` |
| `reason_codes` | array of unique code strings |

### Terminal Company Trace

| Field | Type |
|---|---|
| `company_id` | non-empty string |
| `stage_attempts` | array of Terminal Stage Attempt objects |
| `repair_attempts_used` | non-negative integer |
| `terminal_code` | non-empty code string |

The trace records invocation and structural outcome even when a supporting
skill could not emit a valid envelope. It does not replace any valid stage
envelope and contains no evidence, score, decision, action, ordering, or rank.

## Stage Payloads

### `REQUEST_ROUTING`

Payload contains exactly:

- `objective`: non-empty human-readable string;
- `account_reference`: string or `null`;
- `company_references`: array of unique non-empty strings;
- `explicit_page_urls`: array of unique absolute public HTTPS URLs;
- `period`: Period object or `null`;
- `clarification_questions`: array of human-readable strings;
- `stop_reason`: code string or `null`.

### `SOURCE_GATE`

Payload contains exactly:

- `connector_available`: boolean;
- `account_id`, `account_name`: string or `null`;
- `selected_pages`: array of Selected Page objects;
- `sources`: array of Source Reference objects;
- `period`: Period object or `null`;
- `date_chunks`: array of Date Chunk objects;
- `feed_creation_impact`: one closed object or `null`, containing exactly
  `name` (string), `filters` (array of strings), `notifications` (array of
  strings), and `persistent` (boolean);
- `creation_approved`: boolean;
- `tool_counters`: Tool Counters object;
- `stop_reason`: code string or `null`.

### `CANDIDATE_INTAKE`

Payload contains exactly:

- `account_id`: non-empty string;
- `source_refs`: array of unique source-reference IDs;
- `period`: Period object;
- `date_chunks`: array of Date Chunk objects;
- `pagination`: array of Pagination State objects;
- `raw_candidate_count`: non-negative integer;
- `deduplicated_candidate_count`: non-negative integer;
- `candidate_ids`: array of unique non-empty company IDs;
- `batch_size`: positive integer;
- `batches`: array of Processing Batch objects;
- `retrieval_complete`: boolean;
- `tool_counters`: Tool Counters object;
- `stop_reason`: code string or `null`.

### `EVIDENCE_GATE`

Payload contains exactly:

- `raw_response_refs`: array of Raw Response Reference objects;
- `items`: array of Evidence Item objects for the envelope company;
- `normalization_issue_codes`: array of unique code strings;
- `reason_codes`: array of unique code strings.

Evidence may contain zero items. Coverage, points, score, confidence, decisions,
ranking, and human actions are not fields in this stage.

### `ICP_SCORING`

Payload contains exactly:

- `criteria`: array of closed criterion objects;
- `disqualifier_codes`: array of unique code strings;
- `coverage_pct`: number from 0 through 100;
- `total_score`: integer from 0 through 100 or `null`;
- `score_band`: `HIGH_FIT`, `MEDIUM_FIT`, `LOW_FIT`, or `null`;
- `confidence`: `HIGH`, `MEDIUM`, `LOW`, `VERY_LOW`, or `NONE`;
- `reason_codes`: array of unique code strings.

Each criterion object contains exactly:

| Field | Type |
|---|---|
| `criterion_id` | non-empty string |
| `result` | `MATCH`, `PARTIAL`, `NO_MATCH`, `UNKNOWN`, or `DISQUALIFIED` |
| `points` | number or `null` |
| `max_points` | positive number |
| `evidence_ids` | array of unique evidence IDs |
| `unknown_codes` | array of unique code strings |
| `reason_codes` | array of unique code strings |

The Scoring skill owns the criterion set, weights, interpretation, arithmetic,
coverage, confidence, null-score behavior, bands, and disqualifier semantics.

### `RUBRIC_EVALUATION`

Payload contains exactly:

- `checks`: array of closed check objects;
- `repair_request`: one closed repair-request object or `null`;
- `repair_attempts_used`: non-negative integer.

Each check object contains exactly `check_id` (non-empty string), `result`
(`PASS` or `FAIL`), and `reason_codes` (array of unique code strings).

A repair-request object contains exactly `action` (non-empty code string),
`target_stage` (stage enum), and `target_codes` (array of unique code
strings). The Rubric skill owns the checks and bounded repair rules.

### `REPAIR`

Payload contains exactly:

- `attempt`: positive integer;
- `action`: non-empty code string;
- `target_stage`: stage enum;
- `target_codes`: array of unique code strings;
- `result_codes`: array of unique code strings.

### `FINAL_DECISION`

Payload contains exactly:

- `objective`: non-empty human-readable string;
- `account_id`, `account_name`: string or `null`;
- `selected_pages`: array of Selected Page objects;
- `sources`: array of Source Reference objects;
- `period`: Period object or `null`;
- `counts`: Final Counts object;
- `batch_completion`: array of Processing Batch objects;
- `ranking_scope`: constant `FULL_DEDUPLICATED_SET`;
- `ranked_items`: array of Final Item objects;
- `tool_counters`: Tool Counters object;
- `batch_stop_reason`: code string or `null`;
- `batch_summary`: human-readable string.

Final Counts contains exactly:

| Field | Type |
|---|---|
| `retrieved` | non-negative integer |
| `deduplicated` | non-negative integer |
| `evaluated` | non-negative integer |
| `insufficient_evidence` | non-negative integer |
| `failed` | non-negative integer |
| `remaining` | non-negative integer |

Each Final Item contains exactly:

| Field | Type |
|---|---|
| `rank` | positive integer |
| `company_id` | non-empty string |
| `company_label` | string or `null` |
| `score` | integer 0-100 or `null` |
| `score_band` | score-band enum or `null` |
| `coverage_pct` | number 0-100 |
| `confidence` | confidence enum |
| `evidence_ids` | array of unique evidence IDs |
| `unknown_codes` | array of unique code strings |
| `rubric_result` | `PASS`, `FAIL`, or `NOT_COMPLETED` |
| `decision` | `REVIEW`, `MONITOR`, `NO_ACTION`, or `INSUFFICIENT_EVIDENCE` |
| `human_action` | non-empty human-readable string |
| `reason_codes` | array of unique code strings |
| `stop_reason` | code string |

The Recommendation skill owns decision mapping, item order, ranks, and human
actions. The contract records the resulting complete-set output only.

For a completed run, `ranked_items` contains exactly one terminal item for
every unique Intake `candidate_id`, including failed and
`INSUFFICIENT_EVIDENCE` companies. Its company-ID set therefore equals the
deduplicated candidate set, its length equals `counts.deduplicated`, ranks are
unique and contiguous from `1` through that length, `counts.evaluated` equals
that length, and `counts.remaining` is `0`. These are completeness and shape
invariants; Recommendation owns how the items are ordered and ranked.

## Provenance Invariants

- Every non-null `company_id`, source reference, page ID, raw response
  reference, and evidence ID must resolve within the same `run_id`.
- Evidence IDs in Scoring, Rubric, and Final must refer to Evidence Items for
  the same company.
- Each Terminal Company Trace contains one attempt record for Evidence,
  Scoring, and Rubric. A valid-envelope attempt resolves to its same-company
  envelope; an invalid or rejected attempt carries no fabricated envelope.
- Date-chunk IDs used by pagination states must resolve to Source Gate or Intake
  chunks in the same run.
- Final selected pages, sources, period, batches, and counters must be
  traceable to earlier validated envelopes in the same run.
- Final company IDs must equal the complete deduplicated Intake candidate set;
  every Intake batch must be terminal before `FINAL_DECISION` is valid.
- Raw response references are transient identifiers and must not resolve to
  repository files or committed exports.

These are linkage rules, not instructions for how a skill chooses, calculates,
repairs, or ranks.
