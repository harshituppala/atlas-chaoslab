# Check document text and source locations

The layout cases exercise repeated PDF text, blank physical pages and a few DOCX reading rules. Run them from the repository root with the locked environment installed:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.ingestion \
  --dataset datasets/ingestion-layout.json \
  --output var/ingestion-layout.json
```

The report contains each check, the dataset and fixture hashes, and the source fingerprint. A failed case still produces a report and exits unsuccessfully. If source or fixture bytes change during execution, publication is refused and any earlier report is left alone.

The fixture generator is `scripts/seed_layout_documents.py`. Expected text and locations live separately in `datasets/ingestion-layout.json`; do not replace them with whatever the parser currently returns. The PDF has text on pages one and three and repeats a footer on both. DOCX cases cover split runs, deleted text, whitespace and cells under a merged heading.

The original four ingestion cases remain in `datasets/ingestion.json`. Neither dataset measures OCR or visual layout accuracy. A table's XML order does not establish which capability satisfies a requirement. Keep that interpretation visible for human review.

[Repeated-text bug and correction](adr/038-repeated-source-locations.md) · [Latest layout report](../reports/ingestion-layout.json)
