# Claims Intake & Triage Assistant

Reference implementation for the whitepaper **"Architecting Production
Systems with Claude: A Reference Implementation."**

A five-file pipeline that takes an unstructured insurance claim submission
and produces a structured, auditable decision packet — auto-approved or
escalated, with a documented reason. Built to demonstrate specific
architectural decisions, not just that Claude can process a claim.

## What this is

- Extraction (single-shot, structured output) → Interpretation (bounded
  agentic tool-calling loop) → Decision (fully deterministic, zero Claude
  calls) → Summary
- Governance enforced via `CLAUDE.md`, a `PreToolUse` hook, and a project skill
- Two real defects found during testing, documented with root cause and fix
  in the whitepaper (Section 8)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic
export ANTHROPIC_API_KEY="your-key-here"

# Wiring test — no API calls, no cost
python3 src/run_batch_mock.py

# Real run — calls the Anthropic API
python3 src/run_batch.py
```

## Where things are

| File | Role |
|---|---|
| `src/policy_tool.py` | Deterministic coverage lookup |
| `src/extraction_agent.py` | Claude, single-shot, forced structured output |
| `src/interpretation_agent.py` | Claude, bounded agentic loop |
| `src/decision_engine.py` | Deterministic decision logic — no Claude calls |
| `src/orchestrator.py` | Pipeline entry point |
| `CLAUDE.md` | Architecture rules for this project |
| `.claude/hooks/` | Enforcement: blocks API calls in the decision layer |
| `.claude/skills/` | Guided extension of coverage categories |

## Read the whitepaper

The architectural reasoning, decision log, and two documented defects
(found via real testing, not staged) are in the accompanying whitepaper —
see Section 5 for the domain-by-domain code walkthrough and Section 8 for
the case studies.

## License

MIT — see `LICENSE`.
