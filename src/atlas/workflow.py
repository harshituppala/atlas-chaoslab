"""Bounded LangGraph workflow with a deterministic extractive baseline."""

import re
import time
from collections.abc import Callable
from hashlib import sha256
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from pydantic import TypeAdapter, ValidationError

from .domain import (
    Assessment,
    Citation,
    Document,
    Requirement,
    ResourceBudgetExceeded,
    extractive_draft,
)
from .retrieval import BM25, tokens

tracer = trace.get_tracer("atlas.workflow")
MANDATORY = re.compile(r"\b(must|shall|required)\b", re.I)
NEGATIVE = re.compile(r"\b(not|no|unsupported|unavailable|cannot|only)\b", re.I)


class State(TypedDict, total=False):
    rfp: Document
    knowledge: list[Document]
    requirements: list[Requirement]
    assessments: list[Assessment]
    trace: list[dict]
    retrieval: Callable


def extract(document: Document) -> list[Requirement]:
    result = []
    for match in re.finditer(r"[^\n]+", document.text):
        text = match.group()
        if not MANDATORY.search(text):
            continue
        if len(text) > 4096 or len(result) >= 500:
            raise ResourceBudgetExceeded("Requirement extraction budget exceeded")
        citation = Citation(
            document_id=document.id,
            digest=document.digest,
            start=match.start(),
            end=match.end(),
            quote=text,
        )
        category = (
            "security" if re.search(r"data|sso|encrypt|security", text, re.I) else "operations"
        )
        identifier = sha256(
            f"{document.digest}:{match.start()}:{match.end()}".encode()
        ).hexdigest()[:20]
        result.append(Requirement(id=identifier, text=text, category=category, source=citation))
    return result


def compile_workflow():
    def extraction(state):
        start = time.perf_counter()
        with tracer.start_as_current_span("extract"):
            requirements = extract(state["rfp"])
        return {
            "requirements": requirements,
            "trace": [
                {
                    "stage": "extract",
                    "duration_ms": (time.perf_counter() - start) * 1000,
                    "count": len(requirements),
                }
            ],
        }

    def assessment(state):
        start = time.perf_counter()
        index = BM25(state["knowledge"])
        retrieve = state.get("retrieval", index.search)
        documents = {d.id: d for d in state["knowledge"]}
        items, attempts, failures = [], 0, 0
        with tracer.start_as_current_span("retrieve_and_assess"):
            for requirement in state["requirements"]:
                evidence = []
                for _attempt in range(2):
                    attempts += 1
                    try:
                        candidates = TypeAdapter(list[Citation]).validate_python(
                            retrieve(requirement.text)
                        )
                        # The baseline requires two shared content tokens; this is a
                        # retrieval heuristic, not a factual entailment judgement.
                        evidence = [
                            c
                            for c in candidates
                            if c.document_id in documents
                            and c.matches(documents[c.document_id])
                            and len(set(tokens(requirement.text)) & set(tokens(c.quote))) >= 2
                        ]
                        break
                    except (TimeoutError, ConnectionError, ValidationError):
                        failures += 1
                negative = any(NEGATIVE.search(c.quote) for c in evidence)
                status = (
                    "conflicting_evidence"
                    if negative
                    else "evidence_found"
                    if evidence
                    else "missing_evidence"
                )
                draft = extractive_draft(evidence)
                items.append(
                    Assessment(
                        requirement=requirement, status=status, evidence=evidence, draft=draft
                    )
                )
        return {
            "assessments": items,
            "trace": state["trace"]
            + [
                {
                    "stage": "retrieve_and_assess",
                    "duration_ms": (time.perf_counter() - start) * 1000,
                    "attempts": attempts,
                    "failures": failures,
                }
            ],
        }

    def validation(state):
        with tracer.start_as_current_span("validate"):
            sources = {d.id: d for d in [state["rfp"], *state["knowledge"]]}
            for item in state["assessments"]:
                for citation in [item.requirement.source, *item.evidence]:
                    if citation.document_id not in sources or not citation.matches(
                        sources[citation.document_id]
                    ):
                        raise ValueError("Citation integrity check failed")
        return {"trace": state["trace"] + [{"stage": "validate", "citations_valid": True}]}

    graph = StateGraph(State)
    graph.add_node("extract", extraction)
    graph.add_node("assess", assessment)
    graph.add_node("validate", validation)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "assess")
    graph.add_edge("assess", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


WORKFLOW = compile_workflow()


def analyze(rfp: Document, knowledge: list[Document], retrieval=None) -> dict:
    state = {"rfp": rfp, "knowledge": knowledge}
    if retrieval is not None:
        state["retrieval"] = retrieval
    return WORKFLOW.invoke(state, config={"recursion_limit": 8})
