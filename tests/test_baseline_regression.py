"""Known limitation remains visible; new failures are regression gates."""

import json
from pathlib import Path

from atlas.chaos_adapter import run
from chaoslab.__main__ import evaluate


def test_fault_cases_and_known_extraction_gap():
    cases = json.loads(Path("datasets/golden.json").read_text())["cases"]
    outcomes = {case["id"]: evaluate(case, run(case["input"], case.get("fault"))) for case in cases}
    assert {key for key, value in outcomes.items() if not value["passed"]} == {
        "extraction-heldout-language"
    }
    heldout = outcomes["extraction-heldout-language"]
    assert heldout["extraction_tp"] == 1 and heldout["extraction_expected"] == 2
    assert heldout["checks"]["citation_integrity"]
