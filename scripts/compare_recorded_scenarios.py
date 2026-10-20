"""Execute a fresh offline baseline, then compare with an unchanged historical recording.

No provider calls are made. Never overwrites the original model report.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from chaoslab.__main__ import source_digest
from chaoslab.artifacts import publish_report
from chaoslab.execution import invoke
from chaoslab.scenarios import export_inputs


def main():
    recorder_raw = Path(__file__).read_bytes()
    model_path = Path("var/bedrock/scenarios-live-v4.json")
    historical_path = Path("reports/scenarios-live-v4.json")
    model_raw, historical_raw = model_path.read_bytes(), historical_path.read_bytes()
    historical = json.loads(historical_raw)
    if hashlib.sha256(model_raw).hexdigest() != historical["execution"]["input_artifact_sha256"]:
        raise ValueError("Historical recording no longer matches its original public report")
    model = json.loads(model_raw)
    if (
        model.get("live_model") is not True
        or model.get("source_unchanged_at_completion") is not True
    ):
        raise ValueError("Expected the completed historical recording")
    dataset_path = Path("datasets/scenarios.json")
    dataset_raw = dataset_path.read_bytes()
    dataset = json.loads(dataset_raw)
    manifest = export_inputs(dataset, dataset_raw)
    if model["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Historical dataset differs")
    frozen = source_digest()
    directory = Path("var/comparison") / uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    rows = []
    for row in manifest["cases"]:
        try:
            output = invoke("atlas.chaos_adapter:run", row["input"])
            output["documents"] = [row["input"]["rfp"], *row["input"]["knowledge"]]
            rows.append({**row, "status": "succeeded", "output": output})
        except Exception:
            rows.append({**row, "status": "failed"})
    baseline_path = directory / "baseline.json"
    publish_report(baseline_path, {"dataset_sha256": manifest["dataset_sha256"], "results": rows})
    result_path = directory / "comparison.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "chaoslab.comparison",
            "--dataset",
            str(dataset_path),
            "--reference",
            str(baseline_path),
            "--candidate",
            str(model_path),
            "--output",
            str(result_path),
        ],
        check=True,
    )
    report = json.loads(result_path.read_bytes())
    if (
        Path(__file__).read_bytes() != recorder_raw
        or source_digest() != frozen
        or dataset_path.read_bytes() != dataset_raw
        or model_path.read_bytes() != model_raw
        or historical_path.read_bytes() != historical_raw
    ):
        raise ValueError("Source or saved evidence changed during experiment")
    report["experiment"] = {
        "reference": "Fresh locally executed extractive baseline, three trusted adapter subprocesses.",
        "candidate": "Historical Bedrock source-selection-v4 recording from October 16; no new inference.",
        "historical_public_report_sha256": hashlib.sha256(historical_raw).hexdigest(),
        "baseline_source_sha256": frozen,
        "recorder_sha256": hashlib.sha256(recorder_raw).hexdigest(),
        "new_provider_calls": 0,
        "limits": "Same-author three-scenario/nine-obligation development set. Earlier held-out and hostile-evidence failures remain separate and unchanged. No controlled latency/cost comparison or superiority claim.",
    }
    publish_report(Path("reports/scenario-comparison.json"), report)


if __name__ == "__main__":
    main()
