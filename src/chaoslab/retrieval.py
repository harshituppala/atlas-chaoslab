"""Compare retrievers using independent labels; no labels enter the encoder."""

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import publish_report


def score(ranked, relevant, k):
    expected = set(relevant)
    returned = list(dict.fromkeys(ranked))
    hits = len(set(returned[:k]) & expected)
    reciprocal = next(
        (1 / rank for rank, identifier in enumerate(returned, 1) if identifier in expected), 0.0
    )
    return {"recall_at_k": hits / len(expected), "reciprocal_rank": reciprocal}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/retrieval.json")
    parser.add_argument("--output", default="reports/retrieval.json")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.k <= 10:
        parser.error("k must be 1..10")
    from atlas.domain import Document
    from atlas.semantic import MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256, HybridIndex, LocalEncoder

    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    started = time.perf_counter()
    encoder = LocalEncoder()
    load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    index = HybridIndex([Document.model_validate(d) for d in dataset["documents"]], encoder)
    index_ms = (time.perf_counter() - started) * 1000
    results = []
    for query in dataset["queries"]:
        for method in ("lexical", "semantic", "hybrid"):
            start = time.perf_counter()
            hits = index.search(query["query"], limit=args.k, method=method)
            latency = (time.perf_counter() - start) * 1000
            ranked = [hit.source.document_id for hit in hits]
            results.append(
                {
                    "query_id": query["id"],
                    "method": method,
                    **score(ranked, query["relevant_document_ids"], args.k),
                    "latency_ms": latency,
                    "ranked_document_ids": ranked,
                    "scores": [hit.score for hit in hits],
                    "score_kind": hits[0].method if hits else None,
                }
            )
    summary = {}
    for method in ("lexical", "semantic", "hybrid"):
        rows = [r for r in results if r["method"] == method]
        summary[method] = {
            "recall_at_k": statistics.mean(r["recall_at_k"] for r in rows),
            "mrr": statistics.mean(r["reciprocal_rank"] for r in rows),
            "latency_median_ms": statistics.median(r["latency_ms"] for r in rows),
        }
    source = hashlib.sha256()
    for path in sorted(Path("src").rglob("*.py")):
        source.update(str(path).encode())
        source.update(path.read_bytes())
    report = {
        "schema_version": 1,
        "kind": "retrieval",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": dataset["scope"],
        "unique_queries": len(dataset["queries"]),
        "k": args.k,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "embedding_dimensions": index.vectors.shape[1],
        "weights_sha256": WEIGHTS_SHA256,
        "model_load_ms": load_ms,
        "index_build_ms": index_ms,
        "device": "cpu",
        "external_inference_calls": 0,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": source.hexdigest(),
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "environment": platform.platform(),
        "python": platform.python_version(),
        "summary": summary,
        "results": results,
    }
    path = Path(args.output)
    publish_report(path, report)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
