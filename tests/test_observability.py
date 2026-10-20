import json

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from atlas.observability import PrivateJSONLExporter


def test_trace_export_preserves_correlation_and_excludes_private_content(tmp_path):
    path = tmp_path / "trace.jsonl"
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(PrivateJSONLExporter(path)))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("atlas.operation") as root:
        root.set_attribute("job.id", "synthetic-job")
        root.set_attribute("document.text", "private document text")
        root.set_attribute("authorization", "private credential")
        root.add_event("sensitive event", {"private": "event data"})
        with tracer.start_as_current_span("atlas.child"):
            pass
    provider.shutdown()
    raw = path.read_text()
    assert "private" not in raw and "sensitive" not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    child, parent = rows
    assert child["trace_id"] == parent["trace_id"]
    assert child["parent_span_id"] == parent["span_id"]
    assert parent["attributes"]["job.id"] == "synthetic-job"
    assert path.stat().st_mode & 0o777 == 0o600


def test_trace_export_failure_is_reported_without_raising(tmp_path):
    from opentelemetry.sdk.trace.export import SpanExportResult

    exporter = PrivateJSONLExporter(tmp_path / "blocked" / "trace.jsonl")
    (tmp_path / "blocked").write_text("not a directory")
    assert exporter.export([]) == SpanExportResult.FAILURE


def test_unknown_span_names_cannot_export_raw_prompt_text(tmp_path):
    path = tmp_path / "trace.jsonl"
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(PrivateJSONLExporter(path)))
    with provider.get_tracer("test").start_as_current_span("private raw prompt"):
        pass
    provider.shutdown()
    assert "private raw prompt" not in path.read_text()
    assert "unrecognized.operation" in path.read_text()
