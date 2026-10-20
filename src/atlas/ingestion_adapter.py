"""Extraction observations only; independently authored labels stay in CHAOSLAB."""

import base64

from .domain import ResourceBudgetExceeded
from .ingestion import ExtractionFailed, UnsupportedDocument, extract_isolated


def run(inputs):
    try:
        document = extract_isolated(
            base64.b64decode(inputs["raw_base64"], validate=True),
            inputs["format"],
            inputs["title"],
            inputs["kind"],
        )
        return {"status": "extracted", "document": document.model_dump()}
    except UnsupportedDocument:
        return {"status": "rejected", "reason": "unsupported_document"}
    except ResourceBudgetExceeded:
        return {"status": "rejected", "reason": "resource_budget_exceeded"}
    except ExtractionFailed:
        return {"status": "rejected", "reason": "extraction_failed"}
