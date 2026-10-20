# ATLAS and CHAOSLAB

Two tools for reviewing requirements and testing the systems that assess them.

**[ATLAS](src/atlas/README.md)** is the review application. It compares RFP requirements with capability records, links each finding to its source and lets a reviewer record a decision. In the sample, the RFP requires recovery within four hours; the capability register promises eight.

**[CHAOSLAB](src/chaoslab/README.md)** is the evaluator. It runs adapters against fixed cases and checks extraction, evidence selection, citations, review state and failure handling. Its reports keep incorrect answers and failed runs visible.

[Try the fictional review lab](https://atlas-review-lab.onrender.com) · [Read the case study](docs/case-study.md) · [Current work](docs/STATUS.md)

The hosted lab runs the extractive baseline on fictional documents. It accepts no uploads or model credentials, and its history disappears after expiry or restart. The full local workbench supports document uploads and an optional Bedrock workflow; managed sign-in and durable hosted storage are still unfinished.

## Run ATLAS locally

Requires Python 3.12+, Node 24 and pnpm 11.25.0.

```sh
python3.12 -m venv .runtime
.runtime/bin/python -m pip install -r requirements.lock
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
make serve
# In a second terminal, from the repository root:
make worker
```

Open http://127.0.0.1:8000 and use the generated reviewer token in `var/local-credentials.json`. This launcher binds to loopback and is for private use. PostgreSQL setup and the separate runtime roles are covered in the [operator guide](docs/deployment.md).

## Run an evaluation

With the same environment installed:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab --output var/evaluation.json
PYTHONPATH=src .runtime/bin/python -m chaoslab.recovery --output var/recovery.json
PYTHONPATH=src .runtime/bin/python -m pytest -q --basetemp=var/pytest-local
```

The example adapter targets ATLAS. [CHAOSLAB's guide](src/chaoslab/README.md) explains the adapter boundary, paired comparisons and the limits of the current datasets.

## What the results mean

A citation can point to real text while the assessment is wrong. The live-model experiments retain a misread numeric threshold, a legitimate excerpt removed by a keyword filter and a hostile appendix selected as evidence. The datasets are small synthetic development sets, not representative contract accuracy measurements. See the [results and failure analysis](docs/adr/030-live-paired-injection-diagnostic.md).

The [CI run for the hosted release](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39461145031) passed backend and browser checks. Database, model and hosted acceptance reports describe separate runs; their details are in [the status notes](docs/STATUS.md).

## Why one repository?

ATLAS and CHAOSLAB have separate source packages and responsibilities. They currently share fixtures, dependency setup and CI so changes to the application can be checked against its evaluator together. Some retrieval probes still call ATLAS directly; fully separate packaging remains work to finish. The individual project guides describe those boundaries without presenting the two tools as unrelated codebases.
