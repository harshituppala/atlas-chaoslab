"""Measure persisted retrieval on authored labels in an owned disposable schema."""

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from .artifacts import publish_report
from .retrieval import score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-config", default="var/postgresql/client.json")
    parser.add_argument("--dataset", default="datasets/retrieval.json")
    parser.add_argument("--output", default="reports/persistent-retrieval.json")
    args = parser.parse_args()
    values = json.loads(Path(args.postgres_config).read_text())
    if values["host"] != "127.0.0.1" or values["dbname"] != "portfolio_integration":
        parser.error(
            "This runner owns disposable schemas only in the dedicated local integration database"
        )
    url = URL.create(
        "postgresql+psycopg",
        username=values["user"],
        password=values["password"],
        host=values["host"],
        port=values["port"],
        database=values["dbname"],
        query={"sslmode": values["sslmode"]},
    )
    admin = create_engine(url)
    namespace = "atlas_benchmark_" + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    engine = create_engine(
        url.update_query_dict({"options": "-csearch_path=" + namespace + ",public"})
    )
    try:
        from atlas.domain import Document
        from atlas.migrations import upgrade
        from atlas.pg_retrieval import PersistentHybridIndex
        from atlas.semantic import MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256, LocalEncoder

        upgrade(engine)
        raw = Path(args.dataset).read_bytes()
        dataset = json.loads(raw)
        encoder = LocalEncoder()
        started = time.perf_counter()
        first = PersistentHybridIndex(
            engine, "benchmark", [Document.model_validate(d) for d in dataset["documents"]], encoder
        )
        build_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        restored = PersistentHybridIndex(
            engine, "benchmark", [Document.model_validate(d) for d in dataset["documents"]], encoder
        )
        restore_ms = (time.perf_counter() - started) * 1000
        if first.cache_reused or not restored.cache_reused:
            raise RuntimeError("The persisted-cache lifecycle did not match the fresh schema")
        results = []
        for query in dataset["queries"]:
            for method in ("lexical", "semantic", "hybrid"):
                start = time.perf_counter()
                hits = restored.search(query["query"], limit=3, method=method)
                elapsed = (time.perf_counter() - start) * 1000
                ranked = [hit.source.document_id for hit in hits]
                results.append(
                    {
                        "query_id": query["id"],
                        "method": method,
                        **score(ranked, query["relevant_document_ids"], 3),
                        "latency_ms": elapsed,
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
        for file in sorted(Path("src").rglob("*.py")):
            source.update(str(file).encode())
            source.update(file.read_bytes())
        report = {
            "schema_version": 1,
            "kind": "persistent_retrieval",
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": dataset["scope"]
            + " Same ten positive queries through persisted exact pgvector search; not additional independent cases, RLS validation or a production SLA.",
            "unique_queries": len(dataset["queries"]),
            "k": 3,
            "backend": "pgvector_exact",
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "encoder_recipe_sha256": encoder.recipe_sha256,
            "corpus_id": first.corpus_id,
            "corpus_build_ms": build_ms,
            "cache_restore_ms": restore_ms,
            "cache_reused": restored.cache_reused,
            "dataset_sha256": hashlib.sha256(raw).hexdigest(),
            "source_sha256": source.hexdigest(),
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "working_tree_dirty": bool(
                subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
            ),
            "python": platform.python_version(),
            "environment": platform.platform(),
            "external_inference_calls": 0,
            "summary": summary,
            "results": results,
        }
        output = Path(args.output)
        publish_report(output, report)
        print(json.dumps({"summary": summary, "cache_reused": True}, indent=2))
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


if __name__ == "__main__":
    main()
