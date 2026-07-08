
"""
interpretation_agent.py (v2 — agentic)

Previously this made one forced tool_choice call, with policy_tool
invoked separately by the orchestrator and handed to Claude as a
pre-fetched result. Claude never decided to look anything up.

Now: Claude receives two tools — lookup_policy (gather evidence) and
record_interpretation (commit to a final answer) — and decides for
itself when it has enough to conclude. The loop runs until Claude calls
record_interpretation, or until the scoped contract's tool-call budget
is exhausted.

This is a genuinely agentic loop (Domain 1), built against a real tool
contract Claude reasons about directly (Domain 2) — not just internal
code we call on Claude's behalf.
"""

import anthropic
from policy_tool import lookup_policy

MODEL = "claude-sonnet-4-6"

INTERPRETATION_AGENT_CONTRACT = {
    "objective": "Determine coverage position for a single claim and flag conflicts.",
    "decision_boundary": "May NOT decide approve, deny, or escalate. That is decision_engine.py's job.",
    "allowed_tools": ["lookup_policy"],
    "must_call_lookup_before_concluding": True,
    "must_return_indeterminate_if": [
        "lookup_policy returns lookup_failed",
        "customer statement conflicts with policy evidence",
    ],
    "max_tool_calls": 3,
}

_LOOKUP_POLICY_TOOL = {
    "name": "lookup_policy",
    "description": (
        "Look up coverage policy for a claim category. Use the EXACT "
        "category value from the extracted claim you were given — do "
        "not invent a more specific or different category string; a "
        "close variant that is not in the coverage table will return "
        "lookup_failed even when the correct category would have "
        "succeeded. Returns status: 'found' (a matching clause exists), "
        "'not_found' (search completed, genuinely no matching category), "
        "or 'lookup_failed' (could not be completed with confidence, "
        "e.g. an unrecognized category). A failed lookup is NOT evidence "
        "of non-coverage — do not treat it as a denial. Call this once "
        "per claim; do not re-query with alternate phrasings of the "
        "same category."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "The claim category to check coverage for.",
            }
        },
        "required": ["category"],
    },
}

_RECORD_INTERPRETATION_TOOL = {
    "name": "record_interpretation",
    "description": (
        "Call this ONLY when you are ready to commit to a final "
        "interpretation. Calling this ends the process — you will not "
        "get another turn. Make sure you have called lookup_policy "
        "first if you have not already confirmed coverage."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_position": {
                "type": "string",
                "enum": ["covered", "not_covered", "indeterminate"],
                "description": (
                    "'indeterminate' must be used whenever the policy "
                    "lookup failed/was incomplete, or a genuine conflict "
                    "prevents a clean call — never resolved by guessing."
                ),
            },
            "conflict_detected": {"type": "boolean"},
            "conflict_description": {"type": ["string", "null"]},
            "interpretation_confidence": {
                "type": "number",
                "description": "0.0-1.0 confidence in this coverage position.",
            },
            "reasoning_summary": {
                "type": "string",
                "description": "1-3 sentence plain explanation of how this position was reached.",
            },
        },
        "required": [
            "coverage_position",
            "conflict_detected",
            "conflict_description",
            "interpretation_confidence",
            "reasoning_summary",
        ],
    },
}

_SYSTEM_PROMPT = f"""You interpret insurance claims against policy evidence.
You do not approve, deny, or escalate claims — you only assess coverage
and flag conflicts. A downstream system makes the actual decision.

Your contract for this task:
{INTERPRETATION_AGENT_CONTRACT}

Rules:
- You must call lookup_policy before concluding, unless the extracted
  claim gives you no usable category at all.
- If the customer's stated belief about the policy contradicts the
  actual policy evidence, set conflict_detected to true and describe
  both positions. Do not silently resolve the conflict.
- Do not average, split the difference, or hedge past what the evidence
  actually shows.
- When you are ready to conclude, call record_interpretation. That call
  ends the process."""


def _execute_tool(tool_name: str, tool_input: dict) -> dict:
    """The only tool we actually execute server-side. record_interpretation
    is never 'executed' — seeing that call IS the exit condition."""
    if tool_name == "lookup_policy":
        result = lookup_policy(tool_input.get("category", ""))
        return {
            "status": result.status,
            "category": result.category,
            "clause": result.clause,
            "evidence_excerpt": result.evidence_excerpt,
            "auto_approval_cap": result.auto_approval_cap,
            "known_conflict": result.known_conflict,
            "failure_reason": result.failure_reason,
        }
    raise ValueError(f"No server-side handler for tool: {tool_name}")


def interpret_claim(extracted_claim: dict, policy_result=None) -> dict:
    """
    Note: policy_result parameter is kept for backward-compatible call
    signature, but is no longer used — Claude now calls lookup_policy
    itself, on its own schedule, inside this loop.
    """
    client = anthropic.Anthropic()

    messages = [
        {
            "role": "user",
            "content": f"""Extracted claim:
{extracted_claim}

Assess coverage position and flag any conflicts. Call lookup_policy
first to gather evidence, then call record_interpretation with your
conclusion.""",
        }
    ]
    tools = [_LOOKUP_POLICY_TOOL, _RECORD_INTERPRETATION_TOOL]
    max_calls = INTERPRETATION_AGENT_CONTRACT["max_tool_calls"]

    all_policy_lookups = []  # every lookup_policy call this turn, in order

    for turn in range(max_calls + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=_SYSTEM_PROMPT,
            tools=tools,
            tool_choice={"type": "auto"},
            messages=messages,
        )

        # Claude can return MULTIPLE tool_use blocks in a single turn.
        # The API requires a tool_result for every tool_use block before
        # the next message — missing even one causes a 400 error. Collect
        # all of them, not just the first.
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": "You must respond by calling a tool, not plain text.",
                }
            )
            continue

        # If record_interpretation is among the calls, that's the final
        # answer — we can return immediately without needing to supply
        # tool_results, since we're ending the conversation here, not
        # continuing it.
        final_block = next(
            (b for b in tool_use_blocks if b.name == "record_interpretation"), None
        )
        if final_block is not None:
            result = dict(final_block.input)
            # Prefer a successful lookup over a later failed/exploratory
            # one — Claude may make more than one lookup_policy call, and
            # the LAST call is not necessarily the one its answer is
            # actually grounded in.
            found_lookup = next(
                (l for l in all_policy_lookups if l["status"] == "found"), None
            )
            result["_policy_lookup"] = found_lookup or (
                all_policy_lookups[-1] if all_policy_lookups else None
            )
            return result

        # Otherwise, execute every tool call in this turn and respond
        # with a matching tool_result for each one, in order.
        messages.append({"role": "assistant", "content": response.content})
        tool_result_blocks = []
        for block in tool_use_blocks:
            if block.name == "lookup_policy":
                tool_result = _execute_tool("lookup_policy", block.input)
                all_policy_lookups.append(tool_result)
            else:
                tool_result = {"error": f"Unknown tool: {block.name}"}
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(tool_result),
                }
            )
        messages.append({"role": "user", "content": tool_result_blocks})
        continue

    found_lookup = next(
        (l for l in all_policy_lookups if l["status"] == "found"), None
    )
    return {
        "coverage_position": "indeterminate",
        "conflict_detected": False,
        "conflict_description": None,
        "interpretation_confidence": 0.0,
        "reasoning_summary": (
            f"Tool-call budget ({max_calls}) exhausted without the agent "
            f"reaching a final interpretation."
        ),
        "_policy_lookup": found_lookup or (
            all_policy_lookups[-1] if all_policy_lookups else None
        ),
    }
