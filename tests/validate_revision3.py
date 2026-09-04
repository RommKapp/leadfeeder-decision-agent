#!/usr/bin/env python3
"""Dependency-free deterministic Revision 3 contract, fixture, and ownership checks."""

import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "leadfeeder-decision"
SKILLS = ROOT / ".agents" / "skills"

EXPECTED_TOOLS = [
    "get_account_info",
    "usage",
    "get_web_visits_custom_feeds",
    "get_web_visits_custom_feed",
    "get_web_visits_companies",
    "search_web_visits",
    "search_companies",
    "match_companies",
]
EXPECTED_SCOPES = [
    "accounts:read",
    "usage:read",
    "companies:read",
    "web_visits:read",
]
SKILL_NAMES = [
    "leadfeeder-decision-orchestrator",
    "leadfeeder-evidence",
    "leadfeeder-icp-scoring",
    "leadfeeder-rubric",
    "leadfeeder-recommendation",
]
STAGES = {
    "REQUEST_ROUTING",
    "SOURCE_GATE",
    "CANDIDATE_INTAKE",
    "EVIDENCE_GATE",
    "ICP_SCORING",
    "RUBRIC_EVALUATION",
    "REPAIR",
    "FINAL_DECISION",
}
COMMON_KEYS = {
    "schema_version",
    "run_id",
    "stage",
    "company_id",
    "status",
    "evidence_ids",
    "unknown_codes",
    "payload",
    "next_stage",
}
PAYLOAD_KEYS = {
    "REQUEST_ROUTING": {
        "objective",
        "account_reference",
        "company_references",
        "explicit_page_urls",
        "period",
        "clarification_questions",
        "stop_reason",
    },
    "SOURCE_GATE": {
        "connector_available",
        "account_id",
        "account_name",
        "selected_pages",
        "sources",
        "period",
        "date_chunks",
        "feed_creation_impact",
        "creation_approved",
        "tool_counters",
        "stop_reason",
    },
    "CANDIDATE_INTAKE": {
        "account_id",
        "source_refs",
        "period",
        "date_chunks",
        "pagination",
        "raw_candidate_count",
        "deduplicated_candidate_count",
        "candidate_ids",
        "batch_size",
        "batches",
        "retrieval_complete",
        "tool_counters",
        "stop_reason",
    },
    "EVIDENCE_GATE": {
        "raw_response_refs",
        "items",
        "normalization_issue_codes",
        "reason_codes",
    },
    "ICP_SCORING": {
        "criteria",
        "disqualifier_codes",
        "coverage_pct",
        "total_score",
        "score_band",
        "confidence",
        "reason_codes",
    },
    "RUBRIC_EVALUATION": {
        "checks",
        "repair_request",
        "repair_attempts_used",
    },
    "REPAIR": {
        "attempt",
        "action",
        "target_stage",
        "target_codes",
        "result_codes",
    },
    "FINAL_DECISION": {
        "objective",
        "account_id",
        "account_name",
        "selected_pages",
        "sources",
        "period",
        "counts",
        "batch_completion",
        "ranking_scope",
        "ranked_items",
        "tool_counters",
        "batch_stop_reason",
        "batch_summary",
    },
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def exact_keys(value, expected, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == set(expected), f"{label} closed keys")


def unique_strings(values, label):
    require(isinstance(values, list), f"{label} must be an array")
    require(all(isinstance(value, str) and value for value in values), f"{label} values")
    require(len(values) == len(set(values)), f"{label} unique")


def iso8601(value, label):
    require(isinstance(value, str) and value, f"{label} timestamp")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def toml_array(text, key):
    match = re.search(rf"(?ms)^\s*{re.escape(key)}\s*=\s*\[(.*?)^\s*\]", text)
    require(match, f"missing TOML array {key}")
    return re.findall(r'"([^"]+)"', match.group(1))


def validate_period(value, label):
    exact_keys(value, {"start", "end", "timezone", "today_partial"}, label)
    iso8601(value["start"], f"{label}.start")
    iso8601(value["end"], f"{label}.end")
    require(isinstance(value["timezone"], str) and value["timezone"], f"{label}.timezone")
    require(isinstance(value["today_partial"], bool), f"{label}.today_partial")


def validate_page(value):
    exact_keys(
        value,
        {
            "page_id",
            "url",
            "selected_by",
            "selection_rationale",
            "filter_operator",
            "filter_value",
            "scope_label",
        },
        "Selected Page",
    )
    require(value["url"].startswith("https://"), "Selected Page public HTTPS URL")
    require(value["selected_by"] in {"USER", "PUBLIC_WEB", "EXISTING_SOURCE"}, "Selected Page selected_by")
    require(value["filter_operator"] in {"IS", "CONTAINS", "BEGINS_WITH", "OTHER"}, "Selected Page operator")
    require(value["scope_label"] in {"EXACT", "SUBSTRING", "PREFIX", "OTHER"}, "Selected Page scope")
    require(value["selection_rationale"] and value["filter_value"], "Selected Page rationale/filter")


def validate_source(value):
    exact_keys(
        value,
        {
            "source_ref",
            "source_type",
            "source_id",
            "source_name",
            "page_ids",
            "persistent",
            "created_during_run",
        },
        "Source Reference",
    )
    require(value["source_type"] in {"CUSTOM_FEED", "VISITING_COMPANIES", "WEB_VISITS", "LOCAL_TEST_FIXTURE"}, "Source Reference type")
    unique_strings(value["page_ids"], "Source Reference page_ids")
    require(isinstance(value["persistent"], bool) and isinstance(value["created_during_run"], bool), "Source Reference booleans")


def validate_chunk(value):
    exact_keys(value, {"chunk_id", "start", "end", "status"}, "Date Chunk")
    iso8601(value["start"], "Date Chunk start")
    iso8601(value["end"], "Date Chunk end")
    require(value["status"] in {"PENDING", "COMPLETE", "FAILED"}, "Date Chunk status")


def validate_pagination(value):
    exact_keys(
        value,
        {
            "path_id",
            "tool",
            "date_chunk_id",
            "pages_fetched",
            "items_received",
            "next_cursor",
            "next_page",
            "complete",
            "error_code",
        },
        "Pagination State",
    )
    require(isinstance(value["pages_fetched"], int) and value["pages_fetched"] >= 0, "Pagination pages")
    require(isinstance(value["items_received"], int) and value["items_received"] >= 0, "Pagination items")
    require(isinstance(value["complete"], bool), "Pagination complete")


def validate_batch(value):
    exact_keys(value, {"batch_id", "company_ids", "status"}, "Processing Batch")
    unique_strings(value["company_ids"], "Processing Batch company_ids")
    require(value["status"] in {"PENDING", "COMPLETE", "FAILED"}, "Processing Batch status")


def validate_counters(value):
    exact_keys(value, {"leadfeeder_read_calls", "paid_calls", "known_credit_spend", "mutations"}, "Tool Counters")
    require(all(isinstance(item, int) and item >= 0 for item in value.values()), "Tool Counters non-negative")


def validate_stage_attempt(value):
    exact_keys(
        value,
        {"stage", "outcome", "attempt_count", "envelope_status", "reason_codes"},
        "Terminal Stage Attempt",
    )
    require(value["stage"] in {"EVIDENCE_GATE", "ICP_SCORING", "RUBRIC_EVALUATION"}, "Terminal Stage Attempt stage")
    require(value["outcome"] in {"VALID_ENVELOPE", "INVALID_ENVELOPE", "INPUT_REJECTED"}, "Terminal Stage Attempt outcome")
    require(isinstance(value["attempt_count"], int) and value["attempt_count"] > 0, "Terminal Stage Attempt count")
    unique_strings(value["reason_codes"], "Terminal Stage Attempt reason_codes")
    if value["outcome"] == "VALID_ENVELOPE":
        require(value["envelope_status"] in {"PASS", "STOP", "NEEDS_REPAIR", "FAIL"}, "valid attempt envelope status")
    else:
        require(value["envelope_status"] is None, "invalid or rejected attempt has no fabricated status")


def validate_terminal_trace(value):
    exact_keys(
        value,
        {"company_id", "stage_attempts", "repair_attempts_used", "terminal_code"},
        "Terminal Company Trace",
    )
    require(isinstance(value["company_id"], str) and value["company_id"], "Terminal Company Trace company")
    require(isinstance(value["repair_attempts_used"], int) and value["repair_attempts_used"] >= 0, "Terminal Company Trace repair count")
    require(re.fullmatch(r"[A-Z][A-Z0-9_]*", value["terminal_code"]), "Terminal Company Trace code")
    for attempt in value["stage_attempts"]:
        validate_stage_attempt(attempt)
    require(
        [attempt["stage"] for attempt in value["stage_attempts"]]
        == ["EVIDENCE_GATE", "ICP_SCORING", "RUBRIC_EVALUATION"],
        "Terminal Company Trace covers supporting stages once and in order",
    )


def validate_raw_ref(value):
    exact_keys(value, {"response_ref", "tool", "received_at", "source_ref"}, "Raw Response Reference")
    iso8601(value["received_at"], "Raw Response Reference received_at")


def validate_evidence_item(value, company_id):
    exact_keys(
        value,
        {
            "evidence_id",
            "company_id",
            "classification",
            "field",
            "value",
            "source_tool",
            "source_ref",
            "raw_response_ref",
            "observed_at",
            "period",
        },
        "Evidence Item",
    )
    require(value["company_id"] == company_id, "Evidence Item company linkage")
    require(value["classification"] in {"OBSERVED", "INFERRED", "UNKNOWN"}, "Evidence classification")
    if value["observed_at"] is not None:
        iso8601(value["observed_at"], "Evidence observed_at")
    if value["period"] is not None:
        validate_period(value["period"], "Evidence period")


def validate_criterion(value):
    exact_keys(
        value,
        {
            "criterion_id",
            "result",
            "points",
            "max_points",
            "evidence_ids",
            "unknown_codes",
            "reason_codes",
        },
        "Scoring criterion",
    )
    require(value["result"] in {"MATCH", "PARTIAL", "NO_MATCH", "UNKNOWN", "DISQUALIFIED"}, "criterion result")
    require(isinstance(value["max_points"], (int, float)) and value["max_points"] > 0, "criterion max_points")
    expected_points = {
        "MATCH": value["max_points"],
        "PARTIAL": value["max_points"] / 2,
        "NO_MATCH": 0,
        "UNKNOWN": None,
        "DISQUALIFIED": None,
    }
    require(value["points"] == expected_points[value["result"]], "criterion result-to-points mapping")
    unique_strings(value["evidence_ids"], "criterion evidence_ids")
    unique_strings(value["unknown_codes"], "criterion unknown_codes")
    unique_strings(value["reason_codes"], "criterion reason_codes")


def validate_scoring_math(payload):
    criteria = payload["criteria"]
    require(
        [(item["criterion_id"], item["max_points"]) for item in criteria]
        == [
            ("B2B_WEB_LED_FIT", 25),
            ("COMPANY_SIZE_FIT", 20),
            ("SALES_MOTION_FIT", 20),
            ("BEHAVIORAL_FIT", 25),
            ("GEOGRAPHY_FIT", 10),
        ],
        "exact five scoring criteria and weights",
    )
    assessable = [item for item in criteria if item["result"] in {"MATCH", "PARTIAL", "NO_MATCH"}]
    assessable_weight = sum(item["max_points"] for item in assessable)
    earned = sum(item["points"] for item in assessable)
    require(payload["coverage_pct"] == assessable_weight, "coverage equals assessable weight")
    if payload["disqualifier_codes"]:
        require(payload["total_score"] is None and payload["score_band"] is None, "disqualifier null score")
    elif assessable_weight == 0:
        require(payload["total_score"] is None and payload["score_band"] is None, "zero assessable null score")
        require(payload["confidence"] == "NONE" and "NO_ASSESSABLE_EVIDENCE" in payload["reason_codes"], "zero assessable NONE state")
    else:
        expected = int((Decimal(str(earned)) / Decimal(str(assessable_weight)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        require(payload["total_score"] == expected, "half-up normalized score")
        expected_band = "HIGH_FIT" if expected >= 80 else "MEDIUM_FIT" if expected >= 60 else "LOW_FIT"
        require(payload["score_band"] == expected_band, "score band")
    coverage = payload["coverage_pct"]
    confidence = "HIGH" if coverage >= 85 else "MEDIUM" if coverage >= 70 else "LOW" if coverage >= 40 else "VERY_LOW" if coverage > 0 else "NONE"
    require(payload["confidence"] == confidence, "coverage-derived confidence")


def validate_final_item(value):
    exact_keys(
        value,
        {
            "rank",
            "company_id",
            "company_label",
            "score",
            "score_band",
            "coverage_pct",
            "confidence",
            "evidence_ids",
            "unknown_codes",
            "rubric_result",
            "decision",
            "human_action",
            "reason_codes",
            "stop_reason",
        },
        "Final Item",
    )
    require(isinstance(value["rank"], int) and value["rank"] > 0, "Final Item rank")
    require(value["decision"] in {"REVIEW", "MONITOR", "NO_ACTION", "INSUFFICIENT_EVIDENCE"}, "Final Item decision")
    require(value["rubric_result"] in {"PASS", "FAIL", "NOT_COMPLETED"}, "Final Item rubric_result")
    require(value["confidence"] in {"HIGH", "MEDIUM", "LOW", "VERY_LOW", "NONE"}, "Final Item confidence")
    unique_strings(value["evidence_ids"], "Final Item evidence_ids")
    unique_strings(value["unknown_codes"], "Final Item unknown_codes")
    unique_strings(value["reason_codes"], "Final Item reason_codes")
    require(isinstance(value["human_action"], str) and value["human_action"], "Final Item human action")


def validate_envelope(value):
    exact_keys(value, COMMON_KEYS, "stage envelope")
    require(value["schema_version"] == "2.0", "contract version 2.0")
    require(isinstance(value["run_id"], str) and value["run_id"], "run_id")
    require(value["stage"] in STAGES, "stage enum")
    require(value["status"] in {"PASS", "STOP", "NEEDS_REPAIR", "FAIL"}, "status enum")
    unique_strings(value["evidence_ids"], "envelope evidence_ids")
    unique_strings(value["unknown_codes"], "envelope unknown_codes")
    require(value["next_stage"] is None or value["next_stage"] in STAGES, "next_stage enum")
    exact_keys(value["payload"], PAYLOAD_KEYS[value["stage"]], f"{value['stage']} payload")
    payload = value["payload"]

    if value["stage"] == "REQUEST_ROUTING":
        validate_period(payload["period"], "Routing period")
        unique_strings(payload["company_references"], "Routing company_references")
        unique_strings(payload["explicit_page_urls"], "Routing explicit_page_urls")
    elif value["stage"] == "SOURCE_GATE":
        for page in payload["selected_pages"]:
            validate_page(page)
        for source in payload["sources"]:
            validate_source(source)
        validate_period(payload["period"], "Source Gate period")
        for chunk in payload["date_chunks"]:
            validate_chunk(chunk)
        validate_counters(payload["tool_counters"])
        require(payload["feed_creation_impact"] is None, "read-only Source Gate has no feed creation impact")
        require(payload["creation_approved"] is False, "read-only Source Gate has no creation approval")
        require(all(not source["created_during_run"] for source in payload["sources"]), "read-only Source Gate has no run-created source")
        require(payload["tool_counters"]["mutations"] == 0, "read-only Source Gate has zero mutations")
    elif value["stage"] == "CANDIDATE_INTAKE":
        validate_period(payload["period"], "Intake period")
        for chunk in payload["date_chunks"]:
            validate_chunk(chunk)
        for path in payload["pagination"]:
            validate_pagination(path)
        unique_strings(payload["source_refs"], "Intake source_refs")
        unique_strings(payload["candidate_ids"], "Intake candidate_ids")
        for batch in payload["batches"]:
            validate_batch(batch)
        validate_counters(payload["tool_counters"])
        require(payload["tool_counters"]["mutations"] == 0, "read-only Intake has zero mutations")
    elif value["stage"] == "EVIDENCE_GATE":
        refs = payload["raw_response_refs"]
        for ref in refs:
            validate_raw_ref(ref)
        for item in payload["items"]:
            validate_evidence_item(item, value["company_id"])
        require(value["evidence_ids"] == [item["evidence_id"] for item in payload["items"]], "Evidence envelope IDs match items")
        ref_ids = {ref["response_ref"] for ref in refs}
        require(all(item["raw_response_ref"] in ref_ids for item in payload["items"]), "Evidence raw-response provenance")
    elif value["stage"] == "ICP_SCORING":
        for criterion in payload["criteria"]:
            validate_criterion(criterion)
        unique_strings(payload["disqualifier_codes"], "Scoring disqualifier_codes")
        unique_strings(payload["reason_codes"], "Scoring reason_codes")
        used = []
        for criterion in payload["criteria"]:
            used.extend(criterion["evidence_ids"])
        require(value["evidence_ids"] == list(dict.fromkeys(used)), "Scoring envelope evidence union")
        validate_scoring_math(payload)
    elif value["stage"] == "RUBRIC_EVALUATION":
        require(len(payload["checks"]) == 5, "Rubric has five checks")
        for check in payload["checks"]:
            exact_keys(check, {"check_id", "result", "reason_codes"}, "Rubric check")
            require(check["result"] in {"PASS", "FAIL"}, "Rubric check result")
            unique_strings(check["reason_codes"], "Rubric reason_codes")
        if payload["repair_request"] is not None:
            exact_keys(payload["repair_request"], {"action", "target_stage", "target_codes"}, "repair request")
    elif value["stage"] == "REPAIR":
        require(payload["target_stage"] in STAGES, "Repair target stage")
    elif value["stage"] == "FINAL_DECISION":
        if payload["period"] is not None:
            validate_period(payload["period"], "Final period")
        for page in payload["selected_pages"]:
            validate_page(page)
        for source in payload["sources"]:
            validate_source(source)
        require(all(not source["created_during_run"] for source in payload["sources"]), "read-only Final Decision has no run-created source")
        exact_keys(payload["counts"], {"retrieved", "deduplicated", "evaluated", "insufficient_evidence", "failed", "remaining"}, "Final Counts")
        for batch in payload["batch_completion"]:
            validate_batch(batch)
        for item in payload["ranked_items"]:
            validate_final_item(item)
        validate_counters(payload["tool_counters"])
        require(payload["tool_counters"]["mutations"] == 0, "read-only Final Decision has zero mutations")


def test_runtime_and_contract():
    config = (ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")
    require(re.search(r'(?m)^url\s*=\s*"https://mcp\.leadfeeder\.com/mcp"$', config), "official MCP endpoint")
    require(re.search(r'(?m)^auth\s*=\s*"oauth"$', config), "OAuth authentication")
    require(re.search(r"(?m)^enabled\s*=\s*true$", config), "MCP enabled")
    require(re.search(r"(?m)^required\s*=\s*true$", config), "MCP required")
    require(re.search(r"(?m)^startup_timeout_sec\s*=\s*60$", config), "startup timeout")
    require(re.search(r"(?m)^tool_timeout_sec\s*=\s*60$", config), "tool timeout")
    require(toml_array(config, "enabled_tools") == EXPECTED_TOOLS, "exact eight-tool read-only allowlist")
    require(toml_array(config, "scopes") == EXPECTED_SCOPES, "exact four read-only scopes")
    require("create_web_visits_custom_feed" not in config, "no create tool")
    require("web_visits:write" not in config, "no write scope")
    require("approval_mode" not in config, "no mutation approval configuration")
    contract = (ROOT / "specs" / "001-evidence-gated-decision" / "contracts" / "stage-handoffs.md").read_text(encoding="utf-8")
    for term in (
        "**Contract version**: `2.0`",
        "Selected Page",
        "Date Chunk",
        "Pagination State",
        "Processing Batch",
        "Raw Response Reference",
        "Terminal Stage Attempt",
        "Terminal Company Trace",
        "FULL_DEDUPLICATED_SET",
        "VERY_LOW",
        "NONE",
    ):
        require(term in contract, f"contract 2.0 term: {term}")


def test_forward_cases(forward):
    cases = {case["case_id"]: case for case in forward["cases"]}
    expected = {
        "autonomous_nonpricing_page_choice",
        "mcp_required_for_visitor_analysis",
        "dynamic_page_filters",
        "low_coverage_scores",
        "zero_assessable_no_divide_by_zero",
        "direct_mcp_context_is_accepted",
        "engagement_tie_break_handoff",
        "zero_paid_calls",
        "all_external_mutations_denied",
        "unsupported_request_no_mcp",
        "empty_cohort",
        "filtered_source_empty_control",
        "single_contract_correction",
        "single_rubric_repair",
        "second_invalid_handoff",
        "rubric_invalid_output",
    }
    require(set(cases) == expected, "complete forward and retained regression set")
    page = cases["autonomous_nonpricing_page_choice"]["selected_pages"][0]
    require("pricing" not in page["url"] and page["selected_by"] == "PUBLIC_WEB" and page["selection_rationale"], "autonomous non-pricing page")
    mcp = cases["mcp_required_for_visitor_analysis"]
    require(mcp["success"]["connector_available"] and mcp["success"]["leadfeeder_read_calls"] > 0 and mcp["success"]["visitor_retrieval_calls"] > 0, "MCP mandatory success")
    require(mcp["missing_connector"] == {"stop_reason": "CONNECTOR_UNAVAILABLE", "company_claims": 0}, "missing MCP stops safely")
    require(cases["dynamic_page_filters"]["rules"] == [["IS", "EXACT"], ["BEGINS_WITH", "PREFIX"], ["CONTAINS", "SUBSTRING"]], "dynamic exact prefix substring filters")
    low = cases["low_coverage_scores"]
    require(low["coverage_pct"] == 25 and low["total_score"] == 50 and low["score_band"] == "LOW_FIT" and low["confidence"] == "VERY_LOW", "valid low-coverage score")
    require(low["stages"] == ["EVIDENCE_GATE", "ICP_SCORING", "RUBRIC_EVALUATION", "FINAL_DECISION"], "low coverage continues")
    zero = cases["zero_assessable_no_divide_by_zero"]
    require(zero["coverage_pct"] == 0 and zero["total_score"] is None and zero["score_band"] is None and zero["confidence"] == "NONE" and zero["decision"] == "INSUFFICIENT_EVIDENCE", "zero-assessable null state")
    require(zero["stages"] == ["EVIDENCE_GATE", "ICP_SCORING", "RUBRIC_EVALUATION", "FINAL_DECISION"], "zero state continues")
    direct = cases["direct_mcp_context_is_accepted"]
    require(direct["raw_response_ref"] and direct["extra_fields"] and not direct["projection_required"] and not direct["unsafe_source"] and not direct["persisted_response"] and direct["stop_reason"] is None, "direct transient MCP context")
    engagement = cases["engagement_tie_break_handoff"]
    require(
        engagement["visit_field"] == "qualifying_commercial_visit_id"
        and engagement["visit_classification"] == "OBSERVED"
        and engagement["url_field"] == "qualifying_canonical_public_url"
        and engagement["url_classification"] == "INFERRED",
        "dedicated Evidence-to-Recommendation engagement fields",
    )
    engagement_order = sorted(
        engagement["companies"],
        key=lambda company: (
            -len(set(company["visit_ids"])),
            -len(set(company["canonical_urls"])),
            company["company_id"],
        ),
    )
    require(
        [company["company_id"] for company in engagement_order]
        == engagement["expected_order"]
        and engagement["companies"][1]["raw_pageviews"]
        > engagement["companies"][0]["raw_pageviews"],
        "distinct visits and URLs rank before raw pageview volume",
    )
    paid = cases["zero_paid_calls"]
    require(paid["paid_calls"] == paid["known_credit_spend"] == 0 and not set(paid["trace_tools"]).intersection(paid["forbidden_trace_tools"]), "zero paid calls")
    mutation_denial = cases["all_external_mutations_denied"]
    require(
        mutation_denial["feed_creation_impact"] is None
        and mutation_denial["creation_approved"] is False
        and mutation_denial["mutations"] == 0,
        "strict read-only profile has no mutation approval path",
    )
    require(
        set(mutation_denial["denied_mutations"])
        >= {
            "create_web_visits_custom_feed",
            "update_web_visits_custom_feed",
            "delete_web_visits_custom_feed",
            "create_crm_record",
            "send_outreach",
        },
        "all representative external mutations are denied",
    )
    unsupported = cases["unsupported_request_no_mcp"]
    require(unsupported["stop_reason"] == "UNSUPPORTED_OBJECTIVE" and unsupported["leadfeeder_read_calls"] == 0, "unsupported objective stops without MCP")
    empty = cases["empty_cohort"]
    require(empty == {"case_id": "empty_cohort", "retrieved": 0, "deduplicated": 0, "ranked_items": 0}, "empty cohort completes visibly")
    filtered_empty = cases["filtered_source_empty_control"]
    require(
        filtered_empty["source_type"] == "CUSTOM_FEED"
        and filtered_empty["filtered"]
        == {"returned_on_page": 0, "total_count": 0, "page_count": 0}
        and filtered_empty["unfiltered_control"]["page_size"] == 1
        and filtered_empty["unfiltered_control"]["returned_on_page"] == 1
        and filtered_empty["unfiltered_control"]["total_count"] > 0
        and filtered_empty["unfiltered_control"]["page_count"] > 0
        and filtered_empty["stop_reason"] == "FILTERED_SOURCE_EMPTY"
        and not filtered_empty["account_empty_claim"]
        and filtered_empty["downstream_stage_invocations"] == 0
        and filtered_empty["leadfeeder_read_calls"] == 2
        and filtered_empty["paid_calls"] == 0
        and filtered_empty["known_credit_spend"] == 0
        and filtered_empty["mutations"] == 0,
        "empty Custom Feed is distinguished from an active account by an unfiltered control",
    )
    correction = cases["single_contract_correction"]
    require(correction["correction_requests"] == 1 and correction["additional_mcp_calls"] == 0 and correction["terminal"] == "COMPLETE", "single no-tool contract correction")
    repair = cases["single_rubric_repair"]
    require(repair["repair_requests"] == 1 and repair["additional_mcp_calls"] == 0 and not repair["second_repair_allowed"] and repair["terminal"] == "PASS", "single bounded rubric repair")
    invalid = cases["second_invalid_handoff"]
    require(invalid["correction_requests"] == 1 and invalid["additional_mcp_calls"] == 0 and invalid["terminal"] == "CONTRACT_FAILED", "second invalid handoff terminates")
    validate_terminal_trace(invalid["terminal_trace"])
    attempts = invalid["terminal_trace"]["stage_attempts"]
    require(
        [attempt["outcome"] for attempt in attempts]
        == ["INVALID_ENVELOPE", "INPUT_REJECTED", "VALID_ENVELOPE"]
        and attempts[-1]["envelope_status"] == "FAIL",
        "contract failure reaches a valid terminal Rubric failure without fabrication",
    )
    validate_final_item(invalid["final_item"])
    require(
        invalid["final_item"]["rubric_result"] == "FAIL"
        and invalid["final_item"]["decision"] == "INSUFFICIENT_EVIDENCE"
        and invalid["final_item"]["score"] is None
        and invalid["final_item"]["coverage_pct"] == 0
        and invalid["final_item"]["stop_reason"] == "CONTRACT_FAILED",
        "contract failure has reachable conservative final mapping",
    )
    rubric_invalid = cases["rubric_invalid_output"]
    validate_terminal_trace(rubric_invalid["terminal_trace"])
    validate_final_item(rubric_invalid["final_item"])
    require(
        rubric_invalid["terminal_trace"]["stage_attempts"][-1]["outcome"] == "INVALID_ENVELOPE"
        and rubric_invalid["final_item"]["rubric_result"] == "NOT_COMPLETED"
        and rubric_invalid["final_item"]["decision"] == "INSUFFICIENT_EVIDENCE"
        and rubric_invalid["final_item"]["stop_reason"] == "CONTRACT_FAILED",
        "invalid Rubric output remains visible without inventing a Rubric result",
    )


def test_pipeline(pipeline):
    run = pipeline["run"]
    for envelope_name in ("routing", "source_gate", "candidate_intake", "final_decision"):
        validate_envelope(run[envelope_name])
    examples = run["contract_examples"]
    main_run_id = run["routing"]["run_id"]
    for example in examples.values():
        for stage in ("evidence", "scoring", "rubric"):
            validate_envelope(example[stage])
        require(example["evidence"]["next_stage"] == "ICP_SCORING", "Evidence transition")
        require(example["scoring"]["next_stage"] == "RUBRIC_EVALUATION", "Scoring transition")
        require(example["rubric"]["next_stage"] == "FINAL_DECISION", "Rubric transition")
        evidence_ids = set(example["evidence"]["evidence_ids"])
        require(set(example["scoring"]["evidence_ids"]).issubset(evidence_ids), "Scoring evidence resolves")
        require(set(example["rubric"]["evidence_ids"]).issubset(evidence_ids), "Rubric evidence resolves")
        validate_terminal_trace(example["terminal_trace"])
        company_ids = {
            example["evidence"]["company_id"],
            example["scoring"]["company_id"],
            example["rubric"]["company_id"],
            example["terminal_trace"]["company_id"],
        }
        require(len(company_ids) == 1 and None not in company_ids, "supporting chain company linkage")
        require(
            {example[stage]["run_id"] for stage in ("evidence", "scoring", "rubric")}
            == {main_run_id},
            "supporting chain run linkage",
        )
        require(all(attempt["outcome"] == "VALID_ENVELOPE" for attempt in example["terminal_trace"]["stage_attempts"]), "normal terminal trace resolves valid envelopes")
        require(
            [attempt["envelope_status"] for attempt in example["terminal_trace"]["stage_attempts"]]
            == [example["evidence"]["status"], example["scoring"]["status"], example["rubric"]["status"]],
            "Terminal trace statuses resolve to actual envelopes",
        )

    routing = run["routing"]
    source_gate = run["source_gate"]
    intake = run["candidate_intake"]
    final = run["final_decision"]
    run_ids = {routing["run_id"], source_gate["run_id"], intake["run_id"], final["run_id"]}
    require(len(run_ids) == 1, "one run_id across run envelopes")
    require(routing["next_stage"] == "SOURCE_GATE" and source_gate["next_stage"] == "CANDIDATE_INTAKE" and intake["next_stage"] == "EVIDENCE_GATE", "run-level transitions")
    require(routing["payload"]["period"] == source_gate["payload"]["period"] == intake["payload"]["period"] == final["payload"]["period"], "period preserved across stages")
    require(source_gate["payload"]["date_chunks"] == intake["payload"]["date_chunks"], "date chunks preserved into Intake")

    selected_page_ids = {page["page_id"] for page in source_gate["payload"]["selected_pages"]}
    source_refs = {source["source_ref"] for source in source_gate["payload"]["sources"]}
    require(all(set(source["page_ids"]).issubset(selected_page_ids) for source in source_gate["payload"]["sources"]), "Source page IDs resolve")
    require(set(intake["payload"]["source_refs"]).issubset(source_refs), "Intake source refs resolve")
    require(final["payload"]["selected_pages"] == source_gate["payload"]["selected_pages"], "Final pages preserve Source Gate")
    require(final["payload"]["sources"] == source_gate["payload"]["sources"], "Final sources preserve Source Gate")

    chunks = intake["payload"]["date_chunks"]
    require(len(chunks) == 3 and all(chunk["status"] == "COMPLETE" for chunk in chunks), "three complete chunks")
    chunk_ranges = [
        (
            datetime.fromisoformat(chunk["start"].replace("Z", "+00:00")),
            datetime.fromisoformat(chunk["end"].replace("Z", "+00:00")),
        )
        for chunk in chunks
    ]
    require(all((end.date() - start.date()).days + 1 <= 31 for start, end in chunk_ranges), "each chunk at most 31 days")
    require((chunk_ranges[-1][1].date() - chunk_ranges[0][0].date()).days + 1 == 90, "90-day period")
    require(all(chunk_ranges[index][1].date().toordinal() + 1 == chunk_ranges[index + 1][0].date().toordinal() for index in range(2)), "contiguous chunks")
    paths = intake["payload"]["pagination"]
    require(len(paths) == 3 and all(path["complete"] and path["pages_fetched"] == 2 for path in paths), "all paths fully paginated")
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    require(all(path["date_chunk_id"] in chunk_ids for path in paths), "pagination chunk IDs resolve")

    rows = run["retrieval_rows_by_path"]
    require({row["path_id"] for row in rows} == {path["path_id"] for path in paths}, "retrieval rows resolve to paths")
    raw_ids = [company_id for row in rows for company_id in row["company_ids"]]
    candidate_ids = intake["payload"]["candidate_ids"]
    require(len(raw_ids) == intake["payload"]["raw_candidate_count"] == 135, "raw count 135")
    require(len(candidate_ids) == len(set(candidate_ids)) == intake["payload"]["deduplicated_candidate_count"] == 121, "121 unique candidates")
    require(set(raw_ids) == set(candidate_ids) and len(raw_ids) > len(set(raw_ids)), "chunk overlap deduplicated by stable ID")
    batch_ids = [company_id for batch in intake["payload"]["batches"] for company_id in batch["company_ids"]]
    require(batch_ids == candidate_ids and len(batch_ids) == len(set(batch_ids)), "batches cover population once")
    require(len(routing["payload"]["company_references"]) == 12 and set(routing["payload"]["company_references"]).issubset(candidate_ids), "large named set complete")
    require(len(examples) == 121, "one closed supporting-stage chain per candidate")
    require({example["evidence"]["company_id"] for example in examples.values()} == set(candidate_ids), "closed supporting-stage chains cover every candidate")

    evidence_by_id = {}
    for example in examples.values():
        evidence = example["evidence"]
        raw_refs = {ref["response_ref"]: ref for ref in evidence["payload"]["raw_response_refs"]}
        require(len(raw_refs) == len(evidence["payload"]["raw_response_refs"]), "Raw Response References unique")
        require(all(ref["source_ref"] in source_refs for ref in raw_refs.values()), "Raw Response source refs resolve")
        for item in evidence["payload"]["items"]:
            require(item["source_ref"] in source_refs, "Evidence source ref resolves")
            require(item["raw_response_ref"] in raw_refs, "Evidence raw response ref resolves")
            require(item["source_tool"] == raw_refs[item["raw_response_ref"]]["tool"], "Evidence source tool matches Raw Response")
            require(item["period"] == intake["payload"]["period"], "Evidence period matches run period")
            evidence_by_id[item["evidence_id"]] = item

    final_payload = final["payload"]
    items = final_payload["ranked_items"]
    require(final["status"] == "STOP" and final["next_stage"] is None, "terminal Final Decision")
    require(final_payload["ranking_scope"] == "FULL_DEDUPLICATED_SET", "full-set ranking scope")
    require(len(items) == 121 and {item["company_id"] for item in items} == set(candidate_ids), "Final contains every candidate once")
    require([item["rank"] for item in items] == list(range(1, 122)), "contiguous ranks 1..121")
    require(final_payload["counts"] == {"retrieved": 135, "deduplicated": 121, "evaluated": 121, "insufficient_evidence": 119, "failed": 0, "remaining": 0}, "complete final counts")
    require(final_payload["batch_completion"] == intake["payload"]["batches"], "final batches match Intake")
    require(final_payload["tool_counters"] == intake["payload"]["tool_counters"], "final counters reconcile")
    require(final_payload["tool_counters"]["paid_calls"] == final_payload["tool_counters"]["known_credit_spend"] == final_payload["tool_counters"]["mutations"] == 0, "zero paid/credit/mutations")
    decision_priority = {"REVIEW": 0, "MONITOR": 1, "INSUFFICIENT_EVIDENCE": 2, "NO_ACTION": 3}
    confidence_priority = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "VERY_LOW": 3, "NONE": 4}

    def ranking_key(item):
        observed = [
            datetime.fromisoformat(evidence_by_id[evidence_id]["observed_at"].replace("Z", "+00:00")).timestamp()
            for evidence_id in item["evidence_ids"]
            if evidence_id in evidence_by_id and evidence_by_id[evidence_id]["observed_at"] is not None
        ]
        return (
            decision_priority[item["decision"]],
            item["score"] is None,
            -(item["score"] or 0),
            confidence_priority[item["confidence"]],
            -max(observed) if observed else float("inf"),
            item["company_id"],
        )

    require([item["company_id"] for item in items] == [item["company_id"] for item in sorted(items, key=ranking_key)], "global Recommendation ranking algorithm")
    require(items[0]["company_id"] == "fictional-company-121" and items[0]["decision"] == "REVIEW", "late-batch company ranks first globally")
    low_item = next(item for item in items if item["company_id"] == "fictional-company-120")
    require(low_item["score"] == 50 and low_item["coverage_pct"] == 25 and low_item["confidence"] == "VERY_LOW", "low-coverage company visible")
    zero_item = next(item for item in items if item["company_id"] == "fictional-company-1")
    require(zero_item["score"] is None and zero_item["score_band"] is None and zero_item["confidence"] == "NONE" and zero_item["decision"] == "INSUFFICIENT_EVIDENCE", "zero-assessable company visible")
    evidence_ids = set(evidence_by_id)
    require(set(final["evidence_ids"]) == evidence_ids, "Final evidence union resolves")
    require(all(set(item["evidence_ids"]).issubset(evidence_ids) for item in items), "Final item evidence resolves")


def test_mutation_guards(pipeline):
    mutations = []

    orphan = deepcopy(pipeline)
    orphan["run"]["contract_examples"]["high"]["evidence"]["payload"]["raw_response_refs"][0]["source_ref"] = "orphan-source"
    mutations.append(("orphan provenance", orphan))

    unknown_points = deepcopy(pipeline)
    unknown_points["run"]["contract_examples"]["zero"]["scoring"]["payload"]["criteria"][0]["points"] = 1
    mutations.append(("UNKNOWN criterion points", unknown_points))

    ranking = deepcopy(pipeline)
    items = ranking["run"]["final_decision"]["payload"]["ranked_items"]
    items[0], items[1] = items[1], items[0]
    items[0]["rank"], items[1]["rank"] = 1, 2
    mutations.append(("global ranking priority", ranking))

    period = deepcopy(pipeline)
    period["run"]["candidate_intake"]["payload"]["period"]["end"] = "2026-07-28T23:59:59Z"
    mutations.append(("cross-stage period", period))

    scoring_company = deepcopy(pipeline)
    scoring_company["run"]["contract_examples"]["high"]["scoring"]["company_id"] = "fictional-company-120"
    mutations.append(("Scoring company linkage", scoring_company))

    rubric_company = deepcopy(pipeline)
    rubric_company["run"]["contract_examples"]["high"]["rubric"]["company_id"] = "fictional-company-120"
    mutations.append(("Rubric company linkage", rubric_company))

    for stage in ("evidence", "scoring", "rubric"):
        wrong_run = deepcopy(pipeline)
        wrong_run["run"]["contract_examples"]["high"][stage]["run_id"] = "wrong-run"
        mutations.append((f"{stage} run linkage", wrong_run))

    for label, mutated in mutations:
        try:
            test_pipeline(mutated)
        except AssertionError:
            continue
        raise AssertionError(f"mutation guard failed to reject {label}")


def test_ownership(ownership):
    for path in ownership["policy_files"]:
        text = (ROOT / path).read_text(encoding="utf-8")
        for term in ownership["forbidden_policy_terms"]:
            require(term.lower() not in text.lower(), f"policy has no processing term {term}: {path}")
    skill_texts = {
        name: (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        for name in SKILL_NAMES
    }
    for name, text in skill_texts.items():
        require("2.0" in text and "contract" in text.lower(), f"{name} uses contract 2.0")
        for term in ownership["required_skill_terms"][name]:
            require(term.lower() in text.lower(), f"{name} owns {term}")
    for owner, terms in ownership["unique_owner_terms"].items():
        for term in terms:
            matches = [name for name, text in skill_texts.items() if term.lower() in text.lower()]
            require(matches == [owner], f"{term} has exactly one owner: {owner}")


def main():
    fixtures = [
        load("forward-cases.json"),
        load("pipeline-90d-121.json"),
        load("ownership-cases.json"),
    ]
    for fixture in fixtures:
        require(
            fixture["fixture_label"] == "LOCAL_TEST_FIXTURE — not Leadfeeder evidence"
            and fixture["fictional_non_pii"]
            and fixture["fixture_version"] == "3.0",
            "fixture safety label",
        )
    test_runtime_and_contract()
    test_forward_cases(fixtures[0])
    test_pipeline(fixtures[1])
    test_mutation_guards(fixtures[1])
    test_ownership(fixtures[2])
    print(
        "Revision 3 validation passed: 16 forward cases, closed contract-2.0 "
        "envelopes, 121 closed company chains, 9 mutation guards, and ownership audit."
    )


if __name__ == "__main__":
    try:
        main()
    except (
        AssertionError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Revision 3 validation failed: {error}", file=sys.stderr)
        sys.exit(1)
