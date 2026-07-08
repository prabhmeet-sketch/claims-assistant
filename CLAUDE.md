# Claims Intake & Triage Assistant

## What this project is
A claims processing pipeline: raw claim text in, a structured decision
packet out (auto-approved or escalated, with reasoning). Built as a
teaching reference for architecting production systems with Claude —
every file maps to a specific architectural decision, not just "code
that works."

## Non-negotiable architecture rules

1. **`decision_engine.py` must NEVER import `anthropic` or call the API.**
   The approve/escalate outcome must be reproducible and identical for
   identical inputs, every run. If a task seems to require an LLM call
   inside this file, the task is wrong — route it through
   `interpretation_agent.py` instead and pass the result in as data.

2. **`policy_tool.py` lookups must always return one of three statuses**
   — `found`, `not_found`, `lookup_failed` — never a plain boolean or a
   collapsed "no". A failed lookup is not evidence of denial.

3. **Confidence is per-field-group, never a single blended score.**
   Extraction confidence and interpretation confidence are tracked and
   thresholded separately (`LOW_CONFIDENCE_THRESHOLD = 0.5` for
   extraction, `INTERPRETATION_CONFIDENCE_THRESHOLD = 0.8` for
   interpretation — deliberately stricter, see decision_engine.py
   comments for why).

4. **Authorization escalations and uncertainty escalations are separate
   checks, and authorization is checked first.** Confidence must never
   override a policy-mandated human review (e.g. amount over cap).

5. **`extraction_agent.py` stays single-shot; `interpretation_agent.py`
   stays agentic.** Don't add a tool-calling loop to extraction — there's
   nothing for it to decide mid-task. Don't remove the loop from
   interpretation — whether to call `lookup_policy` genuinely depends on
   what it doesn't yet know.

6. **`process_claim()` in `orchestrator.py` is the only entry point.**
   Both batch and interactive interfaces must call it — never duplicate
   pipeline logic in a new entry point.

## File map

| File | Role | Calls Claude? |
|---|---|---|
| `policy_tool.py` | Coverage lookup | No |
| `extraction_agent.py` | Raw text → typed fields | Yes, single-shot |
| `interpretation_agent.py` | Coverage assessment, conflict flagging | Yes, agentic loop (max 3 tool calls) |
| `decision_engine.py` | Approve/escalate outcome | Never |
| `orchestrator.py` | Wires everything, writes reviewer summary | Yes, single-shot (summary only) |

## Testing
`run_batch_mock.py` validates wiring with canned agent outputs — no API
calls, no cost. Run this after any structural change before spending a
real API call via `run_batch.py`.

## Known findings worth preserving
CLM-1004 (portable projector claim) initially auto-approved despite
Claude's own interpretation_confidence reflecting real doubt
(0.72) — the decision engine wasn't reading that field. This is why
rule 3 above exists. Don't remove the interpretation-confidence check
without understanding this case first.
