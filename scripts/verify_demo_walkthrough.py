"""Exercise public controlled fixtures using an installed, ATLAS-free evaluator."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="Installed evaluator Python")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = args.python.absolute()
    example = root / "examples/review-regression"
    files = sorted(example.glob("*.json"))

    def hashes():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

    before = hashes()
    work = root / "var/demo-walkthrough" / uuid4().hex
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.util; import chaoslab.comparison; "
            "assert all(importlib.util.find_spec(m) is None for m in "
            "['atlas', 'fastapi', 'sqlalchemy'])",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    del probe
    results = {}
    scorer = None
    for name, expected_exit, transition in (
        ("reference", 0, "both_passed"),
        ("wrong-decision", 1, "regressed"),
        ("broken-citation", 1, "regressed"),
        ("missing-answer", 1, "unpaired"),
    ):
        output = work / f"{name}.json"
        run = subprocess.run(
            [
                str(python),
                "-m",
                "chaoslab.comparison",
                "--dataset",
                str(example / "dataset.json"),
                "--reference",
                str(example / "reference.json"),
                "--candidate",
                str(example / f"{name}.json"),
                "--output",
                str(output),
                "--require-fixture-gate",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
        )
        if run.returncode != expected_exit:
            raise ValueError(f"Unexpected command outcome: {name}")
        report = json.loads(output.read_text())
        if report["fixture_gate_passed"] != (expected_exit == 0):
            raise ValueError(f"Unexpected fixture gate: {name}")
        if scorer is not None and report["scorer_sha256"] != scorer:
            raise ValueError("Installed scorer changed between cases")
        scorer = report["scorer_sha256"]
        counts = report["requirement_transitions"]
        if counts[transition] != 1 or sum(counts.values()) != 1:
            raise ValueError(f"Unexpected paired accounting: {name}")
        results[name] = {
            "exit_code": run.returncode,
            "fixture_gate_passed": report["fixture_gate_passed"],
            "requirement_transitions": counts,
        }
    if hashes() != before:
        raise ValueError("Example inputs changed during rehearsal")
    record = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Four actual installed evaluator CLI invocations outside the source checkout, using handwritten fictional answers. Not model execution, model accuracy, adapter sandboxing or hosted acceptance.",
        "atlas_installed": False,
        "input_sha256": before,
        "scorer_sha256": scorer,
        "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": results,
        "new_model_provider_calls": 0,
    }
    (root / "reports/demo-walkthrough.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"checks_passed": len(results), "atlas_installed": False}))


if __name__ == "__main__":
    main()
