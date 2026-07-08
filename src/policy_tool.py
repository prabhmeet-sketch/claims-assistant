"""
policy_tool.py

Deterministic policy lookup. Intentionally NOT an LLM call — coverage
rules need to be reproducible and auditable, so this is plain code that
reads a small structured coverage table.

Returns one of three distinct statuses. Callers must not collapse these
into a single "no" — they mean different things downstream:
  - "found"          : a matching policy clause exists, returned as-is
  - "not_found"      : the lookup ran successfully and genuinely has
                        no matching category (a real negative)
  - "lookup_failed"  : the lookup could not be completed with confidence
                        (e.g. an unrecognized/unlisted device category) —
                        this is NOT the same as "not covered"
"""

from dataclasses import dataclass
from typing import Optional


_COVERAGE_TABLE = {
    "electronics_damage": {
        "clause": "Extended Protection Plan (Electronics)",
        "excerpt": (
            "Devices purchased with the Extended Protection Plan are covered "
            "for accidental damage, including damage in transit, for 24 "
            "months from purchase date. No deductible applies for "
            "shipping-related damage."
        ),
        "auto_approval_cap": 5000,
    },
    "property_damage": {
        "clause": "Property Damage (Water, Fire, Weather)",
        "excerpt": (
            "Claims for property damage require an incident date within "
            "the policy period and a repair invoice or damage estimate."
        ),
        "auto_approval_cap": 5000,
    },
    "travel_cancellation": {
        "clause": "Travel Cancellation — Hotel Bookings",
        "excerpt": (
            "Free cancellation is permitted only if cancellation occurs at "
            "least 48 hours before scheduled check-in. Cancellations within "
            "the 48-hour window are NOT covered by this policy, unless the "
            "property itself issued a refund."
        ),
        "auto_approval_cap": 5000,
        "known_conflicting_source": {
            "source": "Legacy Support FAQ (v2.9, retired 2026-02-01)",
            "conflicting_claim": "Cancellations are free with no time limit.",
            "status": "deprecated_but_still_circulating",
        },
    },
}


@dataclass
class PolicyLookupResult:
    status: str  # "found" | "not_found" | "lookup_failed"
    category: str
    clause: Optional[str] = None
    evidence_excerpt: Optional[str] = None
    auto_approval_cap: Optional[int] = None
    known_conflict: Optional[dict] = None
    failure_reason: Optional[str] = None


_RECOGNIZED_CATEGORIES = set(_COVERAGE_TABLE.keys())


def lookup_policy(category: str) -> PolicyLookupResult:
    """
    Look up coverage for a claim category.

    An empty/unrecognized category is NOT treated as "no coverage" — it's
    treated as an incomplete lookup, because we have no basis to confirm
    or deny it.
    """
    if not category:
        return PolicyLookupResult(
            status="lookup_failed",
            category=category or "unknown",
            failure_reason="no_category_extracted",
        )

    if category not in _RECOGNIZED_CATEGORIES:
        return PolicyLookupResult(
            status="lookup_failed",
            category=category,
            failure_reason="category_not_in_coverage_table",
        )

    entry = _COVERAGE_TABLE[category]
    return PolicyLookupResult(
        status="found",
        category=category,
        clause=entry["clause"],
        evidence_excerpt=entry["excerpt"],
        auto_approval_cap=entry["auto_approval_cap"],
        known_conflict=entry.get("known_conflicting_source"),
    )
