"""Opt-in real CPU embedding validation; requires already prepared local weights."""

import json
import re

import numpy as np

from atlas.domain import Document, ResourceBudgetExceeded
from atlas.semantic import HybridIndex, LocalEncoder


def main():
    encoder = LocalEncoder()
    text = " ".join(["Canadian résumés require café-grade encryption and auditable backups."] * 100)
    document = Document(id="unicode-long", title="Unicode fixture", text=text, kind="knowledge")
    index = HybridIndex([document], encoder)
    assert len(index.sources) > 1, "Long input must be split"
    for citation in index.sources:
        assert citation.matches(document)
        assert encoder.token_count(citation.quote) <= encoder.maximum
    # Each non-whitespace word must remain fully covered by a source span.
    for word in re.finditer(r"\S+", text):
        assert any(c.start <= word.start() and c.end >= word.end() for c in index.sources)
    assert np.isfinite(index.vectors).all()
    assert np.allclose(np.linalg.norm(index.vectors, axis=1), 1, atol=1e-5)
    assert index.vectors.shape[1] == 384
    try:
        encoder.encode([text])
    except ResourceBudgetExceeded:
        pass
    else:
        raise AssertionError("Oversized direct encoding must fail before silent truncation")
    for method in ("lexical", "semantic", "hybrid"):
        hits = index.search("auditable encrypted backups", method=method)
        assert hits and all(hit.source.matches(document) for hit in hits)
    print(
        json.dumps(
            {
                "passed": True,
                "chunks": len(index.sources),
                "dimensions": 384,
                "external_inference_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
