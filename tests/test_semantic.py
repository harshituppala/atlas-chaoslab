import numpy as np
import pytest

from atlas.domain import Document, ResourceBudgetExceeded
from atlas.semantic import HybridIndex, reciprocal_rank_fusion
from chaoslab.retrieval import score


class Encoder:
    maximum = 256

    def token_count(self, text):
        return len(text.split())

    def encode(self, texts):
        return np.array(
            [
                [1.0, 0.0] if "encryption" in text or "protect" in text else [0.0, 1.0]
                for text in texts
            ]
        )


def test_hybrid_returns_original_immutable_citations():
    doc = Document(
        id="p",
        title="Policy",
        kind="knowledge",
        text="AES encryption protects records.\nSupport operates continuously.",
    )
    index = HybridIndex([doc], Encoder())
    hits = index.search("protect information", limit=1, method="semantic")
    assert hits[0].source.quote == "AES encryption protects records."
    assert hits[0].source.matches(doc)
    assert hits[0].score == pytest.approx(1.0)


def test_rank_fusion_ignores_duplicate_votes_and_has_stable_ties():
    assert reciprocal_rank_fusion([["a", "a"], ["b"]]) == [("a", 1 / 61), ("b", 1 / 61)]
    assert reciprocal_rank_fusion([["a", "b"], ["b", "a"]])[0][0] == "a"


def test_invalid_vectors_and_silent_truncation_are_rejected():
    class Zero(Encoder):
        def encode(self, texts):
            return np.zeros((len(texts), 2))

    doc = Document(id="p", title="p", kind="knowledge", text="Example content")
    with pytest.raises(ValueError):
        HybridIndex([doc], Zero())
    doc = doc.model_copy(update={"text": "word " * 300})
    with pytest.raises(ResourceBudgetExceeded):
        HybridIndex([doc], Encoder())


def test_independent_retrieval_scorer_measures_partial_and_duplicate_hits():
    assert score(["a", "a", "b"], ["a", "b"], 2)["recall_at_k"] == 1.0
    assert score(["c", "a"], ["a"], 2)["reciprocal_rank"] == 0.5
    assert score(["c"], ["a"], 1)["recall_at_k"] == 0
