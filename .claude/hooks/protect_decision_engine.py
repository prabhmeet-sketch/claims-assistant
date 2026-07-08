#!/usr/bin/env python3
"""
protect_decision_engine.py

PreToolUse hook. Blocks any Write/Edit to decision_engine.py that would
introduce an Anthropic API call. This is the enforcement layer for the
architecture rule stated in CLAUDE.md: the approve/escalate outcome must
stay deterministic. CLAUDE.md is advisory (Claude reads and usually
follows it); this hook is enforcement (it runs every time, regardless
of what Claude "remembers" from context).
"""

import json
import sys

FORBIDDEN_PATTERNS = [
    "import anthropic",
    "from anthropic",
    ".messages.create(",
    "Anthropic()",
]


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path.endswith("decision_engine.py"):
        sys.exit(0)

    # Content lives under different keys depending on tool
    candidate_text = " ".join(
        str(tool_input.get(key, ""))
        for key in ("content", "new_string", "new_str")
    )

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in candidate_text:
            print(
                f"BLOCKED: decision_engine.py must never call the "
                f"Anthropic API (matched pattern: '{pattern}'). "
                f"The approve/escalate outcome must stay deterministic "
                f"and reproducible — see CLAUDE.md, architecture rule 1. "
                f"If this task genuinely needs Claude's judgment, route "
                f"it through interpretation_agent.py instead and pass "
                f"the result into decision_engine.py as plain data.",
                file=sys.stderr,
            )
            sys.exit(2)  # exit 2 = block, stderr shown to Claude

    sys.exit(0)


if __name__ == "__main__":
    main()
