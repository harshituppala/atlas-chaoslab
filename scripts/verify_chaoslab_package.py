"""Build and exercise the local wheel without ATLAS or third-party runtime packages.

Controlled outputs exercise installation and failure gates, not agent quality.
No registry upload or network installation is performed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def fingerprints():
    files = sorted((ROOT / "src/chaoslab").glob("*.py")) + [
        ROOT / "src/chaoslab/pyproject.toml",
        Path(__file__).resolve(),
        ROOT / "scripts/verify_demo_walkthrough.py",
        *sorted((ROOT / "examples/review-regression").glob("*.json")),
        *sorted((ROOT / "examples/reading-qa").glob("*.json")),
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    frozen = fingerprints()
    work = ROOT / "var/chaoslab-package" / uuid4().hex[:12]
    stage, wheels, outside = work / "source", work / "wheels", work / "outside"
    for directory in (stage, wheels, outside):
        directory.mkdir(parents=True)
    for source in (ROOT / "src/chaoslab").iterdir():
        if source.suffix == ".py" or source.name == "pyproject.toml":
            shutil.copyfile(source, stage / source.name)
    env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_CACHE_DIR": str(ROOT / ".cache/pip")}
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    def run(args, *, cwd=outside, expected=0, environment=env):
        result = subprocess.run(args, cwd=cwd, env=environment, capture_output=True, text=True)
        if result.returncode != expected:
            raise RuntimeError(f"Package check failed: {args[1:3]}\n{result.stderr[-1500:]}")
        return result.stdout

    run(
        [
            sys.executable,
            "-c",
            "from setuptools.build_meta import build_wheel; " + f"build_wheel({str(wheels)!r})",
        ],
        cwd=stage,
    )
    (wheel,) = wheels.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any(name.startswith("atlas/") for name in names)
        (metadata,) = [name for name in names if name.endswith(".dist-info/METADATA")]
        assert "Requires-Dist:" not in archive.read(metadata).decode()
    runtime = work / "runtime"
    run([sys.executable, "-m", "venv", str(runtime)])
    python = str(runtime / "bin/python")
    run([python, "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)])
    run(
        [
            python,
            "-c",
            "import importlib.util; "
            "assert all(importlib.util.find_spec(m) is None "
            "for m in ['atlas', 'fastapi', 'sqlalchemy', 'pytest']); "
            "from chaoslab.__main__ import source_digest; "
            "import hashlib; assert source_digest() != hashlib.sha256(b'').hexdigest()",
        ]
    )

    rfp = {"id": "request", "text": "The service must recover within four hours."}
    record = {"id": "record", "text": "Recovery is guaranteed within eight hours."}

    def citation(document):
        return {
            "document_id": document["id"],
            "start": 0,
            "end": len(document["text"]),
            "quote": document["text"],
            "digest": hashlib.sha256(document["text"].encode()).hexdigest(),
        }

    inputs = {"rfp": rfp, "knowledge": [record]}
    dataset = {
        "scope": "Controlled installation check, not a measured agent answer.",
        "cases": [
            {
                "id": "recovery-threshold",
                "input": inputs,
                "expected": [
                    {"text": rfp["text"], "relation": "contradicted", "evidence_ids": ["record"]}
                ],
            }
        ],
    }
    raw = json.dumps(dataset).encode()
    (outside / "dataset.json").write_bytes(raw)
    normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    dataset_hash = hashlib.sha256(raw).hexdigest()
    output = {
        "documents": [rfp, record],
        "assessments": [
            {
                "requirement": {"id": "r1", "text": rfp["text"], "source": citation(rfp)},
                "status": "conflicting_evidence",
                "evidence": [citation(record)],
                "review_state": "pending",
                "version": 1,
                "draft": "Evidence excerpts for human assessment:\n" + record["text"],
            }
        ],
    }
    bundle = {
        "dataset_sha256": dataset_hash,
        "results": [
            {
                "id": hashlib.sha256((dataset_hash + ":recovery-threshold").encode()).hexdigest(),
                "input": inputs,
                "input_sha256": hashlib.sha256(normalized).hexdigest(),
                "status": "succeeded",
                "output": output,
            }
        ],
    }
    (outside / "reference.json").write_text(json.dumps(bundle))
    results = {}
    for name in ("unchanged", "corrupt-citation", "missing-attempt"):
        candidate = deepcopy(bundle)
        if name == "corrupt-citation":
            candidate["results"][0]["output"]["assessments"][0]["evidence"][0]["digest"] = "wrong"
        elif name == "missing-attempt":
            candidate["results"] = []
        (outside / "candidate.json").write_text(json.dumps(candidate))
        run(
            [
                str(runtime / "bin/chaoslab-compare"),
                "--dataset",
                "dataset.json",
                "--reference",
                "reference.json",
                "--candidate",
                "candidate.json",
                "--output",
                "result.json",
                "--require-fixture-gate",
            ],
            expected=0 if name == "unchanged" else 1,
        )
        observed = json.loads((outside / "result.json").read_text())
        assert observed["fixture_gate_passed"] == (name == "unchanged")
        if name == "corrupt-citation":
            assert observed["requirement_transitions"]["regressed"] == 1
        if name == "missing-attempt":
            assert observed["requirement_transitions"]["unpaired"] == 1
        results[name] = {
            key: observed[key]
            for key in ("fixture_gate_passed", "scenario_transitions", "requirement_transitions")
        }
        for name_in_report, digest in observed["scorer_sha256"].items():
            assert digest == frozen[name_in_report]
    invalid_dataset = deepcopy(dataset)
    invalid_dataset["cases"][0]["expected"][0]["relation"] = "invalid"
    (outside / "dataset.json").write_text(json.dumps(invalid_dataset))
    previous = (outside / "result.json").read_bytes()
    run(
        [
            str(runtime / "bin/chaoslab-compare"),
            "--dataset",
            "dataset.json",
            "--reference",
            "reference.json",
            "--candidate",
            "candidate.json",
            "--output",
            "result.json",
            "--require-fixture-gate",
        ],
        expected=2,
    )
    assert (outside / "result.json").read_bytes() == previous
    results["invalid-golden-relation"] = {"exit_code": 2, "previous_report_preserved": True}
    (outside / "dataset.json").write_bytes(raw)
    for name, malformed in (
        ("array-artifact", "[]"),
        ("null-row", json.dumps({"dataset_sha256": dataset_hash, "results": [None]})),
        ("overflow-number", '{"extra":1e9999}'),
        ("deep-nesting", "[" * 80 + "]" * 80),
    ):
        (outside / "candidate.json").write_text(malformed)
        previous = (outside / "result.json").read_bytes()
        run(
            [
                str(runtime / "bin/chaoslab-compare"),
                "--dataset",
                "dataset.json",
                "--reference",
                "reference.json",
                "--candidate",
                "candidate.json",
                "--output",
                "result.json",
                "--require-fixture-gate",
            ],
            expected=2,
        )
        assert (outside / "result.json").read_bytes() == previous
        results[name] = {"exit_code": 2, "previous_report_preserved": True}
    # The installed child process must resolve an external trusted adapter, too.
    (outside / "external_adapter.py").write_text(
        "def run(body, fault):\n    return {'seen': body}\n"
    )
    run(
        [
            python,
            "-c",
            "from chaoslab.execution import invoke; "
            "assert invoke('external_adapter:run', {'value': 7}) == {'seen': {'value': 7}}",
        ],
        environment={**env, "PYTHONPATH": str(outside)},
    )
    # A separate task runs with neither ATLAS nor third-party runtime packages.
    contract_control = {
        "labels": {"promise": {"hypothesis": "The fictional promise continues."}},
        "documents": [
            {
                "id": 1,
                "text": "The promise remains.",
                "spans": [[0, 20]],
                "annotation_sets": [
                    {"annotations": {"promise": {"choice": "Entailment", "spans": [0]}}}
                ],
            }
        ],
    }
    (outside / "contract-control.json").write_text(json.dumps(contract_control))
    run(
        [
            python,
            "-c",
            "import json; from pathlib import Path; "
            "from chaoslab.contractnli import evaluate; "
            "data=json.loads(Path('contract-control.json').read_text()); "
            "result=evaluate(data, 'chaoslab.contractnli:always_not_mentioned'); "
            "assert result['claims']==1 and result['label_accuracy']==0; "
            "assert result['evidence']['micro_precision'] is None; "
            "assert result['evidence']['micro_recall']==0",
        ]
    )
    # Capture and replay raw output in the installed package, using fictional input only.
    run(
        [
            python,
            "-c",
            """
import json
from pathlib import Path
from chaoslab.contractnli import evaluate, adapter_input
from chaoslab.contract_journal import ObservationJournal, read_observations
from chaoslab.__main__ import source_digest

data = json.loads(Path('contract-control.json').read_text())
inputs = {d['id']: adapter_input(d, data['labels']) for d in data['documents']}
journal = ObservationJournal('var/contract-run', dataset={'fixture': True},
    adapter='unavailable.task:never_import', scorer_sha256=source_digest())
try:
    captured = evaluate(data, 'unavailable.task:never_import',
        invoke_adapter=lambda *_: {'predictions': []}, observer=journal.record)
    receipt = journal.finish()
finally:
    journal.close()
header, records, saved = read_observations('var/contract-run/observations.jsonl',
    dataset={'fixture': True}, inputs=inputs)
replayed = evaluate(data, header['adapter'],
    invoke_adapter=lambda _, body: records[body['document']['id']]['output'])
assert captured == replayed and receipt == saved and saved['records'] == 1
""",
        ]
    )
    run(
        [
            python,
            "-c",
            """
import hashlib, json, sys, zipfile
from pathlib import Path
from chaoslab import contract_holdout as holdout, contractnli
from chaoslab.contract_journal import ObservationJournal

data = json.loads(Path('contract-control.json').read_text())
archive = Path('fictional-contracts.zip')
with zipfile.ZipFile(archive, 'w') as target:
    for split in ['dev', 'test']:
        target.writestr('contract-nli/' + split + '.json', json.dumps(data))
fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()
# This is an explicit fictional installation control, not admission of an external archive.
holdout.ARCHIVE_SHA256 = fingerprint
holdout.load_development = lambda path: contractnli.load_development(path, expected_sha256=fingerprint)
_, provenance = holdout.load_development(archive)
journal = ObservationJournal('var/protocol-dev', dataset=provenance,
    adapter='unavailable.task:never_import', scorer_sha256='a' * 64)
result = contractnli.evaluate(data, 'unavailable.task:never_import',
    invoke_adapter=lambda *_: {'predictions': []}, observer=journal.record)
receipt = journal.finish()
report = Path('development-control.json')
report.write_text(json.dumps({'dataset':provenance, 'results':result,
    'observations':receipt, 'replay_matches_recorded_results':True}))
protocol = Path('var/protocol.json')
pin = holdout.freeze(archive, report, journal.final, {'fictional':True}, protocol)
test, test_provenance = holdout.load_test(archive, protocol, pin)
journal = ObservationJournal('var/protocol-test', dataset=test_provenance,
    adapter='unavailable.task:never_import', scorer_sha256='a' * 64, task=holdout.TASK)
expected = contractnli.evaluate(test, 'unavailable.task:never_import',
    invoke_adapter=lambda *_: {'predictions': []}, observer=journal.record, task=holdout.TASK)
journal.finish()
sys.argv = ['test', '--archive', str(archive), '--protocol', str(protocol),
    '--protocol-sha256', pin, '--replay', str(journal.final), '--output', 'test-replayed.json']
holdout.main()
assert json.loads(Path('test-replayed.json').read_text())['results'] == expected
try:
    holdout.load_test(archive, protocol, '0' * 64)
except ValueError:
    pass
else:
    raise AssertionError('Wrong protocol pin admitted')
""",
        ],
    )
    run([str(runtime / "bin/chaoslab-contractnli-test"), "--help"])
    run([str(runtime / "bin/chaoslab-contractnli"), "--help"])
    run(
        [sys.executable, str(ROOT / "scripts/verify_demo_walkthrough.py"), "--python", python],
        cwd=ROOT,
    )
    qa_checks = {}
    qa = ROOT / "examples/reading-qa"
    for name, answer, citations, expected_exit in (
        ("correct", "reference", "reference-citations", 0),
        ("wrong-answer", "wrong-answer", "reference-citations", 1),
        ("missing-answer", "missing-answer", "reference-citations", 1),
        ("broken-citation", "reference", "broken-citations", 1),
    ):
        destination = outside / ("qa-" + name + ".json")
        run(
            [
                str(runtime / "bin/chaoslab-qa"),
                "--dataset",
                str(qa / "dataset.json"),
                "--reference",
                str(qa / "reference.json"),
                "--candidate",
                str(qa / (answer + ".json")),
                "--reference-citations",
                str(qa / "reference-citations.json"),
                "--candidate-citations",
                str(qa / (citations + ".json")),
                "--output",
                str(destination),
                "--require-fixture-gate",
            ],
            expected=expected_exit,
        )
        result = json.loads(destination.read_text())
        assert result["fixture_gate_passed"] == (expected_exit == 0)
        qa_checks[name] = {
            "exit_code": expected_exit,
            "transitions": result["transitions"],
            "candidate_exact": result["candidate"]["exact"],
            "candidate_missing": result["candidate"]["missing"],
        }
    (ROOT / "reports/reading-qa-installation.json").write_text(
        json.dumps(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "scope": "Four actual standalone CLI invocations on authored fictional SQuAD-style saved artifacts. No external dataset download, model execution or third-party adoption.",
                "atlas_installed": False,
                "checks": qa_checks,
                "source_sha256": frozen,
                "new_model_calls": 0,
            },
            indent=2,
        )
        + "\n"
    )
    assert fingerprints() == frozen, "Package source changed during verification"
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "scope": "Local wheel installation and controlled regression checks, not agent quality or model inference.",
        "python": sys.version.split()[0],
        "source_sha256": frozen,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "wheel_name": wheel.name,
        "runtime_dependencies": [],
        "atlas_installed": False,
        "outside_repository_execution": True,
        "external_trusted_adapter": True,
        "reading_qa_checks": qa_checks,
        "comparison_checks": results,
        "frozen_test_installation": "Fictional archive freeze, test-task journal, independent CLI replay and wrong-pin refusal passed without ATLAS or provider libraries. No actual test data or model calls.",
        "contractnli_installation": "Fictional one-claim baseline, private capture/replay with an unavailable adapter, and CLI help passed without ATLAS; no external contract used in this installation check.",
        "limits": "POSIX process controls. ATLAS adapters and database/retrieval probes still require their own dependencies. External dataset results are separate from this installation check. Wheel hashes identify this build, not reproducible byte-for-byte builds or signed provenance.",
    }
    destination = ROOT / "reports/chaoslab-package.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({"status": report["status"], "checks": list(results), "atlas_installed": False})
    )


if __name__ == "__main__":
    main()
