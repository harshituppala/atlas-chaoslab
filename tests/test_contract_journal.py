"""Fictional private observations; no model calls or licensed corpus required."""

import hashlib
import json
from pathlib import Path

import pytest
from test_contractnli import fixture, oracle

from chaoslab import contractnli
from chaoslab.contract_journal import ObservationJournal, canonical, read_observations
from chaoslab.contractnli import adapter_input, evaluate
from chaoslab.execution import AdapterDeadline, AdapterFailure

PROVENANCE = {
    "archive_sha256": "a" * 64,
    "member": "contract-nli/dev.json",
    "member_sha256": "b" * 64,
}
ADAPTER = "unavailable.task:never_import"


def inputs(data):
    return {d["id"]: adapter_input(d, data["labels"]) for d in data["documents"]}


def capture(tmp_path, monkeypatch, *, output=None, failed=False, name="run"):
    monkeypatch.chdir(tmp_path)
    data = fixture()
    journal = ObservationJournal(
        Path("var") / name, dataset=PROVENANCE, adapter=ADAPTER, scorer_sha256="c" * 64
    )

    def invoke(*_):
        if failed:
            raise AdapterDeadline("PRIVATE-PROVIDER-ERROR")
        return oracle() if output is None else output

    try:
        result = evaluate(data, ADAPTER, invoke_adapter=invoke, observer=journal.record)
        receipt = journal.finish()
    finally:
        journal.close()
    return data, journal.final, receipt, result


def replay_metrics(data, records):
    def replay(_, value):
        record = records[value["document"]["id"]]
        if record["status"] == "failed":
            raise AdapterFailure("Saved invocation failure")
        return record["output"]

    return evaluate(data, ADAPTER, invoke_adapter=replay)


@pytest.mark.parametrize(
    "output,failed",
    [
        (None, False),
        ({"predictions": []}, False),
        ({"PRIVATE": "RAW-CONTENT"}, False),
        (None, True),
    ],
)
def test_private_capture_and_replay_preserve_success_omission_and_failure(
    tmp_path, monkeypatch, output, failed
):
    data, path, receipt, original = capture(tmp_path, monkeypatch, output=output, failed=failed)
    header, records, restored = read_observations(path, dataset=PROVENANCE, inputs=inputs(data))
    assert replay_metrics(data, records) == original
    assert receipt == restored and receipt["records"] == 1
    assert header["adapter"] == ADAPTER
    assert receipt["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert not (path.parent / "observations.partial.jsonl").exists()
    assert "PRIVATE-PROVIDER-ERROR" not in path.read_text()
    assert "text" not in records[1] and "annotations" not in path.read_text()
    assert "RAW-CONTENT" not in json.dumps(original)


def rewrite(path, mutate):
    lines = [json.loads(raw) for raw in path.read_bytes().splitlines()]
    mutate(lines)
    body = b"".join(canonical(value) + b"\n" for value in lines[:-1])
    lines[-1]["body_sha256"] = hashlib.sha256(body).hexdigest()
    path.write_bytes(body + canonical(lines[-1]) + b"\n")


@pytest.mark.parametrize(
    "kind",
    [
        "dataset",
        "input",
        "duplicate",
        "unknown_doc",
        "boolean_doc",
        "extra_field",
        "bad_status",
        "failed_output",
        "version",
        "scorer",
        "count",
    ],
)
def test_replay_rejects_structural_corruption_even_with_a_recomputed_footer(
    tmp_path, monkeypatch, kind
):
    data, path, _, _ = capture(tmp_path, monkeypatch)

    def mutate(lines):
        if kind == "dataset":
            lines[0]["dataset"] = {}
        elif kind == "input":
            lines[1]["input_sha256"] = "0" * 64
        elif kind == "duplicate":
            lines.insert(2, dict(lines[1]))
            lines[-1]["records"] = 2
        elif kind == "unknown_doc":
            lines[1]["document_id"] = 999
        elif kind == "boolean_doc":
            lines[1]["document_id"] = True
        elif kind == "extra_field":
            lines[1]["extra"] = "PRIVATE-MARKER"
        elif kind == "bad_status":
            lines[1]["status"] = "unknown"
        elif kind == "failed_output":
            lines[1]["status"] = "failed"
        elif kind == "version":
            lines[0]["schema_version"] = True
        elif kind == "scorer":
            lines[0]["scorer_sha256"] = "not-a-digest"
        else:
            lines[-1]["records"] = 2

    rewrite(path, mutate)
    with pytest.raises(ValueError, match="^Private contract observations rejected$"):
        read_observations(path, dataset=PROVENANCE, inputs=inputs(data))


@pytest.mark.parametrize(
    "kind", ["truncated", "checksum", "trailing", "public", "symlink", "overflow", "duplicate_json"]
)
def test_replay_rejects_incomplete_nonprivate_and_ambiguous_files(tmp_path, monkeypatch, kind):
    data, path, _, _ = capture(tmp_path, monkeypatch)
    raw = path.read_bytes()
    if kind == "truncated":
        path.write_bytes(raw.rsplit(b"\n", 2)[0] + b"\n")
    elif kind == "checksum":
        path.write_bytes(raw.replace(b'"Entailment"', b'"NotMentioned"', 1))
    elif kind == "trailing":
        path.write_bytes(raw + b"{}\n")
    elif kind == "public":
        path.chmod(0o644)
    elif kind == "symlink":
        link = path.parent / "link.jsonl"
        link.symlink_to(path)
        path = link
    elif kind == "overflow":
        path.write_bytes(raw.replace(b'"output":{', b'"output":{"number":1e999,', 1))
    else:
        path.write_bytes(raw.replace(b'"document_id":1', b'"document_id":1,"document_id":1', 1))
    with pytest.raises(ValueError, match="^Private contract observations rejected$"):
        read_observations(path, dataset=PROVENANCE, inputs=inputs(data))


def test_journal_requires_new_private_directory_and_does_not_overwrite(tmp_path, monkeypatch):
    _, path, _, _ = capture(tmp_path, monkeypatch)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        ObservationJournal(path.parent, dataset=PROVENANCE, adapter=ADAPTER, scorer_sha256="c" * 64)
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match="under private var"):
        ObservationJournal(
            tmp_path / "elsewhere", dataset=PROVENANCE, adapter=ADAPTER, scorer_sha256="c" * 64
        )


def test_interrupted_journal_stays_private_and_cannot_be_replayed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    journal = ObservationJournal(
        "var/interrupted", dataset=PROVENANCE, adapter=ADAPTER, scorer_sha256="c" * 64
    )
    journal.close()
    assert journal.partial.exists() and not journal.final.exists()
    with pytest.raises(ValueError, match="Private contract observations rejected"):
        read_observations(journal.partial, dataset=PROVENANCE, inputs=inputs(fixture()))


def test_observation_write_failure_is_not_scored_as_an_adapter_failure():
    def broken(_):
        raise OSError("controlled recording failure")

    with pytest.raises(OSError, match="controlled recording failure"):
        evaluate(fixture(), ADAPTER, invoke_adapter=lambda *_: oracle(), observer=broken)


def test_cli_replay_never_invokes_or_imports_the_original_adapter(tmp_path, monkeypatch):
    data, path, receipt, expected = capture(tmp_path, monkeypatch)
    monkeypatch.setattr(contractnli, "load_development", lambda _: (data, PROVENANCE))
    monkeypatch.setattr(contractnli, "source_digest", lambda: "d" * 64)
    report = tmp_path / "result.json"
    monkeypatch.setattr(
        "sys.argv",
        ["contractnli", "--archive", "absent.zip", "--replay", str(path), "--output", str(report)],
    )
    contractnli.main()
    saved = json.loads(report.read_text())
    assert saved["results"] == expected and saved["mode"] == "replay"
    assert saved["adapter"] == ADAPTER and saved["observations"] == receipt
    assert saved["scorer_sha256"] == "d" * 64 and receipt["origin_scorer_sha256"] == "c" * 64
    assert "RAW-CONTENT" not in report.read_text()


def test_cli_source_drift_preserves_report_and_leaves_observations_incomplete(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(contractnli, "load_development", lambda _: (fixture(), PROVENANCE))
    values = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(contractnli, "source_digest", lambda: next(values))
    report = tmp_path / "report.json"
    report.write_text("earlier evidence")
    monkeypatch.setattr(
        "sys.argv",
        [
            "contractnli",
            "--archive",
            "absent.zip",
            "--adapter",
            "chaoslab.contractnli:always_not_mentioned",
            "--journal",
            "var/drift",
            "--output",
            str(report),
        ],
    )
    with pytest.raises(SystemExit, match="source changed"):
        contractnli.main()
    assert report.read_text() == "earlier evidence"
    assert Path("var/drift/observations.partial.jsonl").exists()
    assert not Path("var/drift/observations.jsonl").exists()


def test_cli_refuses_to_overwrite_replay_input_before_reading_any_dataset(tmp_path, monkeypatch):
    _, path, _, _ = capture(tmp_path, monkeypatch)
    original = path.read_bytes()
    monkeypatch.setattr(
        contractnli, "load_development", lambda _: pytest.fail("Do not load dataset")
    )
    monkeypatch.setattr(
        "sys.argv",
        ["contractnli", "--archive", "absent.zip", "--replay", str(path), "--output", str(path)],
    )
    with pytest.raises(SystemExit, match="cannot replace its saved observations"):
        contractnli.main()
    assert path.read_bytes() == original
