"""Auditable lexical baseline. It is NOT a semantic embedding model."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from .domain import Citation, Document, ResourceBudgetExceeded

STOP = set(
    "the a an and or of to in is are must shall required be all vendor system provide support with for on will should".split()
)
INSTRUCTION = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)|system\s*prompt|exfiltrat|send.{0,30}(?:secret|credential)|override.{0,30}instruction",
    re.I,
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


@dataclass(frozen=True)
class Chunk:
    source: Citation
    terms: Counter
    suspicious: bool


class BM25:
    def __init__(self, documents: list[Document], chunks: list[Citation] | None = None):
        self.chunks = []
        originals = {document.id: document for document in documents}
        if len(originals) != len(documents):
            raise ValueError("Duplicate document IDs")
        if chunks is None:
            chunks = []
            for document in documents:
                for match in re.finditer(r"[^\n]+", document.text):
                    if match.group().strip():
                        chunks.append(
                            Citation(
                                document_id=document.id,
                                digest=document.digest,
                                start=match.start(),
                                end=match.end(),
                                quote=match.group(),
                            )
                        )
        for source in chunks:
            document = originals.get(source.document_id)
            if document is None or not source.matches(document):
                raise ValueError("Lexical chunk provenance is invalid")
            if len(source.quote) > 4096 or len(self.chunks) >= 5000:
                raise ResourceBudgetExceeded("Evidence chunk budget exceeded")
            self.chunks.append(
                Chunk(source, Counter(tokens(source.quote)), bool(INSTRUCTION.search(source.quote)))
            )
        self.average = sum(sum(c.terms.values()) for c in self.chunks) / max(1, len(self.chunks))
        self.df = Counter(t for c in self.chunks for t in c.terms)

    def search(self, query: str, limit: int = 3) -> list[Citation]:
        n = len(self.chunks)
        ranked = []
        query_terms = set(tokens(query)[:64])
        for chunk in self.chunks:
            if chunk.suspicious:
                continue
            score = 0.0
            length = sum(chunk.terms.values())
            for term in query_terms:
                tf = chunk.terms[term]
                if tf:
                    idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += (
                        idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / max(self.average, 1)))
                    )
            if score > 0:
                ranked.append((score, chunk.source))
        ranked.sort(key=lambda item: (-item[0], item[1].document_id, item[1].start))
        return [citation for _, citation in ranked[:limit]]
