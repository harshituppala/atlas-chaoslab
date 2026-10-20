"""ATLAS adapter; CHAOSLAB does not depend on ATLAS internals."""

from .domain import Citation, Document
from .execution import PIPELINE_VERSION
from .retrieval import BM25
from .workflow import analyze


def run(inputs: dict, fault: str | None = None) -> dict:
    rfp = Document.model_validate(inputs["rfp"])
    knowledge = [Document.model_validate(d) for d in inputs["knowledge"]]
    index = BM25(knowledge)
    calls = 0

    def retrieve(query):
        nonlocal calls
        calls += 1
        if fault == "timeout" or (fault == "transient_timeout" and calls == 1):
            raise TimeoutError("Injected retrieval timeout")
        if fault == "malformed":
            return [{"quote": 42}]
        if fault == "tampered":
            return [
                Citation(
                    document_id=knowledge[0].id,
                    digest=knowledge[0].digest,
                    start=0,
                    end=10,
                    quote="forged citation",
                )
            ]
        return index.search(query)

    state = analyze(rfp, knowledge, retrieve)
    return {
        "assessments": [a.model_dump() for a in state["assessments"]],
        "trace": state["trace"],
        "provider": "extractive-baseline",
        "pipeline_version": PIPELINE_VERSION,
        "external_model_cost_usd": 0.0,
    }
