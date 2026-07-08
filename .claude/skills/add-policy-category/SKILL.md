---
name: add-policy-category
description: Use this skill whenever adding, extending, or modifying a claim coverage category in this project — e.g. "add coverage for X", "add a new claim category", "extend policy_tool.py", or "what if a claim is about Y". Ensures new categories stay consistent with the three-way status contract and the extraction agent's schema. Do not add a category to policy_tool.py without also using this skill.
---

# Adding a policy coverage category

This project's reliability guarantees depend on two files staying in
sync whenever a new claim category is added. Skipping either step
reintroduces exactly the kind of bug documented in CLAUDE.md
("Known findings worth preserving" — CLM-1004).

## Step 1 — Add the category to `policy_tool.py`

Add an entry to `_COVERAGE_TABLE` with all required fields:

```python
"new_category_name": {
    "clause": "Human-readable clause name",
    "excerpt": "The exact policy text a human reviewer could verify against.",
    "auto_approval_cap": 5000,  # or the category-specific cap
    # "known_conflicting_source": {...}  # only if a real conflicting
    #                                       source is known to exist
},
```

Do **not** change the three-way status contract (`found` /
`not_found` / `lookup_failed`) while doing this. `lookup_policy()`
should require no changes — it already generalizes to any key added
to `_COVERAGE_TABLE`.

## Step 2 — Add the category to `extraction_agent.py`'s schema

The `category` field in `_TOOL_SCHEMA` is a closed enum. A category
that exists in `policy_tool.py` but not in this enum can never be
extracted, so `lookup_policy` will always receive an unmapped category
and return `lookup_failed` for it — silently, with no error, which is
easy to miss.

```python
"enum": [
    "electronics_damage",
    "property_damage",
    "travel_cancellation",
    "new_category_name",  # <-- add here too
    "unknown",
],
```

## Step 3 — Do not skip validation

After adding a category, run the mock test before spending any real
API calls:

```bash
.venv/bin/python src/run_batch_mock.py
```

This won't test the new category's real extraction quality (mock
mode doesn't call Claude), but it confirms nothing in the wiring —
`decision_engine.py`'s cap logic, the packet assembly — broke.

## Step 4 — Update CLAUDE.md if the category changes an architecture rule

If the new category needs a different confidence threshold, a
different escalation rule, or any other exception to the standing
rules in CLAUDE.md, update CLAUDE.md in the same change — don't leave
an undocumented exception living only in `decision_engine.py`.

## What NOT to do

- Don't add a category directly to `decision_engine.py`'s logic —
  category-specific behavior belongs in `policy_tool.py`'s table, not
  in the deterministic decision rules, which should stay
  category-agnostic.
- Don't loosen the `enum` to a free-form string to "make it easier" —
  the closed enum is what forces `extraction_agent.py` to say
  `"unknown"` instead of inventing a category, which is what keeps
  low-confidence claims escalating correctly.
