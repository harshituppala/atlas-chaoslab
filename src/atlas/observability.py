"""Local OpenTelemetry traces with an explicit metadata allowlist.

No prompt text, document excerpts, credentials, query strings or exception
messages are exported. Local files are private and separated by process.
"""

import atexit
import json
import os
import threading
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

ALLOWED_NAMES = {
    "atlas.http.request",
    "atlas.operation",
    "atlas.child",
    "atlas.analysis",
    "atlas.worker",
    "atlas.model.structured",
    "extract",
    "retrieve_and_assess",
    "validate",
    "model_extract",
    "model_assess",
}

ALLOWED_ATTRIBUTES = {
    "job.id",
    "pipeline.version",
    "tenant.hash",
    "http.method",
    "http.route",
    "http.status_code",
    "model.task",
    "model.id",
    "model.region",
    "model.input_tokens",
    "model.output_tokens",
    "model.status",
    "model.prompt_sha256",
    "model.schema_sha256",
    "retrieval.method",
    "retrieval.count",
}


class PrivateJSONLExporter(SpanExporter):
    def __init__(self, path: Path, maximum_bytes=5_000_000):
        self.path, self.maximum = path, maximum_bytes
        self.lock = threading.Lock()

    def export(self, spans):
        try:
            with self.lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size >= self.maximum:
                    return SpanExportResult.FAILURE
                lines = []
                for span in spans:
                    # Span events can contain automatic exception strings; exclude them.
                    attrs = {
                        key: value
                        for key, value in (span.attributes or {}).items()
                        if key in ALLOWED_ATTRIBUTES
                    }
                    lines.append(
                        json.dumps(
                            {
                                "name": span.name
                                if span.name in ALLOWED_NAMES
                                else "unrecognized.operation",
                                "trace_id": f"{span.context.trace_id:032x}",
                                "span_id": f"{span.context.span_id:016x}",
                                "parent_span_id": f"{span.parent.span_id:016x}"
                                if span.parent
                                else None,
                                "start_ns": span.start_time,
                                "end_ns": span.end_time,
                                "status": span.status.status_code.name,
                                "attributes": attrs,
                            }
                        )
                        + "\n"
                    )
                descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.fchmod(descriptor, 0o600)
                    data = "".join(lines).encode()
                    if (
                        len(data) + (self.path.stat().st_size if self.path.exists() else 0)
                        > self.maximum
                    ):
                        return SpanExportResult.FAILURE
                    while data:
                        count = os.write(descriptor, data)
                        data = data[count:]
                finally:
                    os.close(descriptor)
            return SpanExportResult.SUCCESS
        except OSError:
            # Trace availability must never make the application process confidential data differently.
            return SpanExportResult.FAILURE

    def shutdown(self):
        return None


_PROVIDER = None


def configure(service):
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    if os.getenv("ATLAS_TRACING") != "1":
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        SimpleSpanProcessor(
            PrivateJSONLExporter(Path("var/traces") / f"{service}-{os.getpid()}.jsonl")
        )
    )
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    atexit.register(provider.shutdown)
    return provider


class RequestTracing:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        tracer = trace.get_tracer("atlas.http")
        with tracer.start_as_current_span(
            "atlas.http.request", record_exception=False, set_status_on_exception=False
        ) as span:
            method = scope["method"]
            span.set_attribute(
                "http.method",
                method
                if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                else "OTHER",
            )

            async def observed_send(message):
                if message["type"] == "http.response.start":
                    span.set_attribute("http.status_code", message["status"])
                await send(message)

            try:
                await self.app(scope, receive, observed_send)
            finally:
                route = scope.get("route")
                if route is not None:
                    span.set_attribute("http.route", getattr(route, "path", "unknown"))
