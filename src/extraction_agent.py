
"""
extraction_agent.py

Turns a raw, unstructured claim submission into typed fields.

Uses forced tool-use (tool_choice) so the output is a strict JSON object,
not prose we then have to parse and hope is well-formed.

Confidence is asked for explicitly per extracted field group, not as one
overall number — a claim can have a clear amount but a vague cause, and
those shouldn't collapse into a single blended score. Missing information
must come back as null/low-confidence, never inferred to make the record
look complete.
"""

import anthropic

MODEL = "claude-sonnet-4-6"

_TOOL_SCHEMA = {
    "name": "record_extracted_claim",
    "description": "Record the structured fields extracted from a raw claim submission.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "electronics_damage",
                    "property_damage",
                    "travel_cancellation",
                    "unknown",
                ],
                "description": (
                    "Best-fit category. Use 'unknown' if the submission "
                    "does not clearly match a known category — do not "
                    "force a fit."
                ),
            },
            "amount": {
                "type": ["number", "null"],
                "description": "Claimed amount if stated. Null if absent.",
            },
            "currency": {"type": ["string", "null"]},
            "incident_date": {
                "type": ["string", "null"],
                "description": "ISO date if the submission states or clearly implies one. Null otherwise — do not guess a date.",
            },
            "customer_stated_belief": {
                "type": ["string", "null"],
                "description": (
                    "If the customer explicitly states what they believe "
                    "the policy allows (e.g. 'I was told there's no time "
                    "limit'), capture that claim verbatim-ish here. Null "
                    "if the customer made no such statement."
                ),
            },
            "purchase_date": {
                "type": ["string", "null"],
                "description": (
                    "Purchase date of the item, if stated. Many coverage "
                    "clauses (e.g. Extended Protection Plan) depend on a "
                    "24-month window from this date, so it directly "
                    "affects eligibility. If only a partial date is given "
                    "(e.g. a month with no year), record what was stated "
                    "in extraction_notes and set this field to null rather "
                    "than guessing the year — a partial date is not a "
                    "usable date."
                ),
            },
            "category_confidence": {
                "type": "number",
                "description": "0.0-1.0 confidence in the category classification alone.",
            },
            "field_completeness_confidence": {
                "type": "number",
                "description": (
                    "0.0-1.0 confidence that the required fields (amount, "
                    "incident date, cause) are actually present and clear "
                    "in the submission — not a guess at what they might be."
                ),
            },
            "extraction_notes": {
                "type": "string",
                "description": "Short note on anything ambiguous, missing, or noteworthy in the raw text.",
            },
        },
        "required": [
            "category",
            "amount",
            "currency",
            "incident_date",
            "customer_stated_belief",
            "purchase_date",
            "category_confidence",
            "field_completeness_confidence",
            "extraction_notes",
        ],
    },
}

_SYSTEM_PROMPT = """You extract structured fields from raw insurance claim submissions.

Rules:
- Never infer a value that is not stated or clearly implied by the text.
- If the incident date, cause, or category is unclear, reflect that with
  lower confidence and/or a null field — do not fill gaps with plausible
  guesses.
- If the customer states a belief about what the policy allows, capture
  it separately from the factual fields — it is their claim, not a
  verified fact.
- Confidence scores must be honest. A vague, one-line submission should
  not receive high confidence just because a category is technically
  assignable.
- If eligibility for the claimed category depends on a date you cannot
  fully confirm (e.g. a purchase date given without a year, needed to
  verify a 24-month coverage window), this is a field-completeness
  problem, not a footnote. Reflect it directly by lowering
  field_completeness_confidence — do not let it exist only as prose in
  extraction_notes while the confidence number stays high. A fact that
  cannot be verified is functionally the same as a missing fact."""


def extract_claim(raw_text: str, claimed_amount, currency, incident_date) -> dict:
    client = anthropic.Anthropic()

    user_content = f"""Raw claim submission:
\"\"\"{raw_text}\"\"\"

Metadata provided alongside the submission (may be incomplete):
claimed_amount: {claimed_amount}
currency: {currency}
incident_date: {incident_date}

Extract the structured fields."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "record_extracted_claim"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_extracted_claim":
            return block.input

    return {
        "category": "unknown",
        "amount": claimed_amount,
        "currency": currency,
        "incident_date": incident_date,
        "customer_stated_belief": None,
        "category_confidence": 0.0,
        "field_completeness_confidence": 0.0,
        "extraction_notes": "Extraction tool call failed to return structured output.",
    }
