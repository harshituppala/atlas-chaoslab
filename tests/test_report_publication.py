"""Concurrent report readers and failed replacement retain complete measured artifacts."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from chaoslab.artifacts import publish_report


def test_concurrent_readers_see_complete_old_or_new_report(tmp_path):
    path = tmp_path / "report.json"
    publish_report(path, {"generation": 0, "samples": [0] * 10000})
    done = threading.Event()

    def read():
        reads = 0
        while not done.is_set() or reads == 0:
            report = json.loads(path.read_text())
            assert len(report["samples"]) == 10000
            assert set(report["samples"]) == {report["generation"]}
            reads += 1
        return reads

    with ThreadPoolExecutor(max_workers=3) as pool:
        readers = [pool.submit(read) for _ in range(3)]
        try:
            for generation in range(1, 12):
                publish_report(path, {"generation": generation, "samples": [generation] * 10000})
        finally:
            done.set()
        assert all(reader.result() > 0 for reader in readers)
    assert json.loads(path.read_text())["generation"] == 11


def test_failed_publication_preserves_old_report_and_cleans_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    publish_report(path, {"measured": 1})
    original = path.read_bytes()

    def refuse(*args):
        raise OSError("Injected replacement failure")

    monkeypatch.setattr("chaoslab.artifacts.os.replace", refuse)
    with pytest.raises(OSError):
        publish_report(path, {"measured": 2})
    assert path.read_bytes() == original and list(tmp_path.iterdir()) == [path]


def test_nonfinite_metrics_cannot_replace_measured_report(tmp_path):
    path = tmp_path / "report.json"
    publish_report(path, {"measured": 1})
    original = path.read_bytes()
    with pytest.raises(ValueError):
        publish_report(path, {"latency": float("nan")})
    assert path.read_bytes() == original
