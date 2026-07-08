"""
run_batch_mock.py

Validates the deterministic parts of the pipeline (policy_tool,
decision_engine, orchestrator wiring, packet assembly) WITHOUT calling
the real Anthropic API. Monkeypatches the two Claude-calling functions
with canned outputs.

Since interpretation_agent now calls lookup_policy itself as part of
its agentic loop, the mock interpretation attaches a real (deterministic,
non-Claude) policy_tool lookup under "_policy_lookup" — exactly like the
real agent would after calling the actual tool.

This is a wiring test, not a model-quality test.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import orchestrator
from policy_tool import lookup_policy

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_claims.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "decision_packets_mock.json")

_MOCK_EXTRACTIONS = {
    "CLM-1001": {
        "category": "electronics_damage", "amount": 1200, "currency": "USD",
        "incident_date": "2026-06-20", "customer_stated_belief": None,
        "purchase_date": None,
        "category_confidence": 0.95, "field_completeness_confidence": 0.9,
        "extraction_notes": "Clear, complete submission.",
    },
    "CLM-1002": {
        "category": "property_damage", "amount": 6500, "currency": "USD",
        "incident_date": "2026-05-15", "customer_stated_belief": None,
        "purchase_date": None,
        "category_confidence": 0.92, "field_completeness_confidence": 0.9,
        "extraction_notes": "Clear submission, amount exceeds cap.",
    },
    "CLM-1003": {
        "category": "travel_cancellation", "amount": 850, "currency": "USD",
        "incident_date": "2026-06-01",
        "customer_stated_belief": "Support told me cancellation is free with no time limit.",
        "purchase_date": None,
        "category_confidence": 0.9, "field_completeness_confidence": 0.85,
        "extraction_notes": "Customer statement conflicts with policy on file.",
    },
    "CLM-1004": {
        "category": "unknown", "amount": 400, "currency": "USD",
        "incident_date": "2026-06-10", "customer_stated_belief": None,
        "purchase_date": None,
        "category_confidence": 0.4, "field_completeness_confidence": 0.7,
        "extraction_notes": "Device category not clearly mappable to a known coverage category.",
    },
    "CLM-1005": {
        "category": "electronics_damage", "amount": 900, "currency": "USD",
        "incident_date": None, "customer_stated_belief": None,
        "purchase_date": None,
        "category_confidence": 0.3, "field_completeness_confidence": 0.2,
        "extraction_notes": "No incident date, no clear cause stated.",
    },
}

_MOCK_INTERPRETATIONS = {
    "CLM-1001": {
        "coverage_position": "covered", "conflict_detected": False,
        "conflict_description": None, "interpretation_confidence": 0.9,
        "reasoning_summary": "Matches Extended Protection Plan clause, within cap.",
    },
    "CLM-1002": {
        "coverage_position": "covered", "conflict_detected": False,
        "conflict_description": None, "interpretation_confidence": 0.88,
        "reasoning_summary": "Matches property damage clause but exceeds auto-approval cap.",
    },
    "CLM-1003": {
        "coverage_position": "indeterminate", "conflict_detected": True,
        "conflict_description": "Customer believes cancellation is free with no time limit; current policy requires 48-hour notice.",
        "interpretation_confidence": 0.5,
        "reasoning_summary": "Conflict between customer's stated understanding and current policy clause.",
    },
    "CLM-1004": {
        "coverage_position": "indeterminate", "conflict_detected": False,
        "conflict_description": None, "interpretation_confidence": 0.2,
        "reasoning_summary": "Policy lookup failed — device category not in coverage table.",
    },
    "CLM-1005": {
        "coverage_position": "indeterminate", "conflict_detected": False,
        "conflict_description": None, "interpretation_confidence": 0.15,
        "reasoning_summary": "Insufficient information to assess coverage confidently.",
    },
}


def _mock_extract_claim(raw_text, claimed_amount, currency, incident_date):
    for cid, data in _MOCK_EXTRACTIONS.items():
        if data["amount"] == claimed_amount:
            return data
    raise ValueError("No mock extraction found for this claim")


def _mock_interpret_claim(extracted_claim, policy_result=None):
    for cid, data in _MOCK_EXTRACTIONS.items():
        if data["amount"] == extracted_claim["amount"]:
            interpretation = dict(_MOCK_INTERPRETATIONS[cid])
            real_lookup = lookup_policy(data["category"])
            interpretation["_policy_lookup"] = {
                "status": real_lookup.status,
                "category": real_lookup.category,
                "clause": real_lookup.clause,
                "evidence_excerpt": real_lookup.evidence_excerpt,
                "auto_approval_cap": real_lookup.auto_approval_cap,
                "known_conflict": real_lookup.known_conflict,
                "failure_reason": real_lookup.failure_reason,
            }
            return interpretation
    raise ValueError("No mock interpretation found for this claim")


def _mock_summary(claim_id, extracted, policy_lookup, interpretation, decision):
    return f"[MOCK SUMMARY] {claim_id}: {decision.outcome} ({decision.escalation_type}) — {decision.reason}"


def main():
    orchestrator.extract_claim = _mock_extract_claim
    orchestrator.interpret_claim = _mock_interpret_claim
    orchestrator._write_reviewer_summary = _mock_summary

    with open(DATA_PATH) as f:
        claims = json.load(f)

    results = []
    all_pass = True
    for claim in claims:
        packet = orchestrator.process_claim(claim)
        expected = claim.get("expected_outcome", "")

        outcome_map = {
            "auto_approve": ("auto_approved", "none"),
            "escalate_authorization": ("escalate", "authorization"),
            "escalate_conflict": ("escalate", "uncertainty"),
            "escalate_evidence_gap": ("escalate", "uncertainty"),
            "escalate_low_confidence": ("escalate", "uncertainty"),
        }
        expected_decision, expected_esc_type = outcome_map.get(expected, (None, None))
        matched = (packet["decision"] == expected_decision and packet["escalation_type"] == expected_esc_type)
        all_pass = all_pass and (matched if expected else True)

        print(f"{claim['claim_id']}: got={packet['decision']}/{packet['escalation_type']}  "
              f"expected={expected_decision}/{expected_esc_type}  "
              f"{'PASS' if matched else 'N/A' if not expected else 'FAIL'}")
        results.append(packet)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'ALL PASS' if all_pass else 'SOME FAILED'} — output written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
