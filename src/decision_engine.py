
"""
decision_engine.py

Deterministic policy application. No LLM call happens here on purpose:
the actual approve/escalate outcome must be reproducible, auditable, and
identical for identical inputs every time — a property a model call
cannot guarantee run to run.

policy_lookup is now a plain dict (not a dataclass) — it comes from
interpretation_agent.py's own tool call, since Claude now looks up
policy itself as part of its agentic loop. One source of truth, one
lookup, instead of the orchestrator calling it a second time separately.
"""

from dataclasses import dataclass

AUTO_APPROVAL_CAP_DEFAULT = 5000
LOW_CONFIDENCE_THRESHOLD = 0.5

INTERPRETATION_CONFIDENCE_THRESHOLD = 0.8


@dataclass
class Decision:
    outcome: str
    escalation_type: str
    reason: str


def decide(extracted_claim: dict, policy_lookup: dict, interpretation: dict) -> Decision:
    amount = extracted_claim.get("amount")
    cap = (policy_lookup or {}).get("auto_approval_cap") or AUTO_APPROVAL_CAP_DEFAULT

    if amount is not None and amount > cap:
        return Decision(
            outcome="escalate",
            escalation_type="authorization",
            reason=f"Claimed amount {amount} exceeds auto-approval cap of {cap}.",
        )

    if not policy_lookup or policy_lookup.get("status") == "lookup_failed":
        failure_reason = (policy_lookup or {}).get("failure_reason", "no lookup performed")
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason=(
                f"Policy lookup could not be completed ({failure_reason}). "
                f"This is an evidence gap, not a confirmed denial."
            ),
        )

    if interpretation.get("conflict_detected"):
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason="Conflicting evidence detected between customer statement and policy record.",
        )

    if interpretation.get("coverage_position") == "indeterminate":
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason="Coverage position could not be determined from available evidence.",
        )

    field_conf = extracted_claim.get("field_completeness_confidence", 0.0)
    category_conf = extracted_claim.get("category_confidence", 0.0)
    if field_conf < LOW_CONFIDENCE_THRESHOLD or category_conf < LOW_CONFIDENCE_THRESHOLD:
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason=(
                f"Extraction confidence too low to auto-decide "
                f"(field_completeness={field_conf}, category={category_conf})."
            ),
        )

    interp_conf = interpretation.get("interpretation_confidence", 0.0)
    if interp_conf < INTERPRETATION_CONFIDENCE_THRESHOLD:
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason=(
                f"Interpretation confidence too low to auto-approve "
                f"(interpretation_confidence={interp_conf}, "
                f"threshold={INTERPRETATION_CONFIDENCE_THRESHOLD})."
            ),
        )

    if interpretation.get("coverage_position") == "not_covered":
        return Decision(
            outcome="escalate",
            escalation_type="uncertainty",
            reason="Claim appears not covered by policy — routed for human confirmation before denial.",
        )

    return Decision(
        outcome="auto_approved",
        escalation_type="none",
        reason="Claim is within cap, clearly covered, and no conflicts or gaps detected.",
    )
