
"""
orchestrator.py

process_claim() is the single entry point both the batch runner and the
interactive CLI call. Flow is fixed and code-driven at the top level —
appropriate for a workflow where every case should go through the same
checks in the same order. Inside step 2, interpretation itself is now a
bounded agentic loop (Claude decides when to call lookup_policy and when
to conclude) — agentic where genuine uncertainty exists, fixed elsewhere.
"""

import anthropic

from extraction_agent import extract_claim
from interpretation_agent import interpret_claim
from decision_engine import decide

MODEL = "claude-sonnet-4-6"


def _write_reviewer_summary(claim_id, extracted, policy_lookup, interpretation, decision) -> str:
    client = anthropic.Anthropic()

    prompt = f"""Write a 1-2 sentence plain-English summary for a human
claims reviewer, based on this record. Do not add new information or
change the decision — just summarize it clearly.

Claim ID: {claim_id}
Extracted: {extracted}
Policy lookup: {policy_lookup}
Interpretation: {interpretation}
Decision: {decision.outcome} ({decision.escalation_type}) — {decision.reason}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


def process_claim(claim: dict) -> dict:
    claim_id = claim["claim_id"]

    extracted = extract_claim(
        raw_text=claim["submitted_text"],
        claimed_amount=claim.get("claimed_amount"),
        currency=claim.get("currency"),
        incident_date=claim.get("incident_date"),
    )

    interpretation = interpret_claim(extracted)
    policy_lookup = interpretation.pop("_policy_lookup", None)

    decision = decide(extracted, policy_lookup, interpretation)

    summary = _write_reviewer_summary(
        claim_id, extracted, policy_lookup, interpretation, decision
    )

    return {
        "claim_id": claim_id,
        "extracted_claim": extracted,
        "policy_lookup": policy_lookup,
        "interpretation": interpretation,
        "decision": decision.outcome,
        "escalation_type": decision.escalation_type,
        "escalation_reason": decision.reason,
        "human_reviewer_summary": summary,
    }
