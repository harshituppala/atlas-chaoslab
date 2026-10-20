# ADR 006: bounded ingestion with immutable source maps

Status: implemented and verified locally on SQLite/macOS; production storage and Linux limits remain deployment gates.

The workbench accepts text-bearing PDF and standard DOCX files up to 1,000,000 bytes. A parser subprocess has a 15-second wall deadline and a POSIX CPU ceiling. Linux also sets a 384 MiB address-space limit; this has not been executed on this machine. macOS does not have a verified hard memory ceiling. PDF decoder/page/form limits and DOCX archive/XML limits apply before extraction where possible. Two parser slots per API process bound concurrent parsing; this is not a distributed rate limit. Request bodies have byte, chunk-count and total receive-time limits.

PDF text is mapped to physical page numbers. DOCX body paragraphs and table cells are mapped to paragraph numbers in XML order. DOCX pages are not inferred. Canonical text retains extracted Unicode and whitespace, normalizes carriage returns, and separates source units with a newline. Offsets count Unicode characters. The browser uses Unicode-aware slicing, including characters outside the basic multilingual plane.

Each immutable upload retains original bytes, their SHA-256, parser identity, canonical text and its source map. Content identity includes parser version and document kind. Deduplication is tenant-scoped; filenames do not change content identity. The first stored title wins. Analysis admission compares uploaded documents with the tenant's persisted snapshot, including provenance, so a client cannot alter text, remove mapping or borrow another tenant's source. Worker publication validates the admitted snapshot again.

Quota reservation, document insert and ingestion audit share a transaction. Duplicate insert races roll back quota increments. Conditional admission caps stored original bytes at 20 MB and uploads at 200 per tenant. These caps do not bound all analysis snapshots, indexes or logs; retention and overall storage quotas remain necessary. Originals currently live in the local database. Private object storage, malware scanning, encrypted production storage, deletion and migration validation remain future work.

Original files are downloaded as authenticated attachments with a content-derived filename, no sniffing and no caching. They are never rendered by the application. The local launcher disables raw access logs because upload filenames appear in query parameters; OpenTelemetry exports only allowlisted route metadata. Reverse-proxy logging needs the same policy before deployment.

Empty/encrypted PDFs, unsupported OOXML/macro formats, DTDs/entities, excessive archive expansion and malformed sources fail without partial publication. Mixed PDFs with textless pages expose a warning. There is no OCR, layout/table reconstruction guarantee, DOCX header/footnote extraction or field evaluation. PDF reading order and table associations require review. Process deadlines do not constitute a hostile-code sandbox.

Independent CHAOSLAB expectations specify page/paragraph locations and raw hashes without calling ATLAS's validation helpers. The four authored synthetic report cases establish those narrow checks, not broad document accuracy. Additional parser, quota, tenant, concurrency and browser tests cover the trust boundaries.

Sources: [pypdf extraction](https://pypdf.readthedocs.io/en/latest/user/extract-text.html), [pypdf public configuration implementation](https://github.com/py-pdf/pypdf/blob/main/pypdf/_configuration.py), [defusedxml](https://pypi.org/project/defusedxml/).
