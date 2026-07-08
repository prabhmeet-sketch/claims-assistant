"""
run_batch.py

Batch entry point. Processes every claim in data/sample_claims.json
through the same pipeline the interactive CLI uses, and writes results
to output/decision_packets.json.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from orchestrator import process_claim

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_claims.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "decision_packets.json")


def main():
    with open(DATA_PATH) as f:
        claims = json.load(f)

    results = []
    for claim in claims:
        print(f"Processing {claim['claim_id']}...")
        packet = process_claim(claim)
        results.append(packet)
        print(f"  -> {packet['decision']} ({packet['escalation_type']})")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nDone. {len(results)} decision packets written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
