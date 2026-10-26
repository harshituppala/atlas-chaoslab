# ATLAS and CHAOSLAB

A request for proposal (RFP) asks for recovery within four hours. The supplier's capability register promises eight. Finding the related paragraph is easy; deciding whether it meets the requirement is a different problem.

**[ATLAS](src/atlas/README.md)** brings the requirement, evidence and review decision into one workspace. It accepts PDF, DOCX or pasted text, runs an analysis and lets a reviewer inspect the original passage before accepting or rejecting the finding.

**[CHAOSLAB](src/chaoslab/README.md)** checks systems that produce those findings. It scores answers against fixed expectations, compares saved runs and tests what happens when responses are missing, malformed or wrong. Its evaluator can be installed without ATLAS.

[Try ATLAS](https://atlas-review-lab.onrender.com) · [Inspect recorded failures](https://atlas-review-lab.onrender.com/?view=evaluation) · [Read the case study](docs/case-study.md) · [Review the code and evidence](docs/reviewer-guide.md)

## What you can try

The public ATLAS lab uses fictional documents and an offline extractive baseline. You can run the sample, open its citations and record a review. It accepts no uploads or model credentials. Its history is temporary and resets after expiry or restart.

The private workbench adds document uploads, saved reviews, job history, audit events and an optional Bedrock model workflow. Real Cognito sign-in has been checked locally. Durable authenticated hosting is still unfinished; the public lab is a separate, restricted application profile.

The [external contract evaluation](docs/contractnli-evaluation.md) covers 61 development contracts and 1,037 claims. Claude Haiku 4.5 reached 77.4% label accuracy, but only 48.7% of claims had both the correct label and complete evidence. Contradictions were a particular weakness. The report preserves those mistakes, separates saved responses from new calls and can be replayed without a model. The separate [frozen test evaluation](docs/contractnli-evaluation.md#frozen-test-result--october-26) covers 123 contracts: 77.5% label accuracy and 49.4% correctness when complete evidence is required. These NDA results do not measure end-to-end RFP accuracy.

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

Open http://127.0.0.1:8000 and use the generated reviewer token in `var/local-credentials.json`. This launcher binds to loopback for private use. The [operator guide](docs/deployment.md) covers PostgreSQL and its separate API, worker and migration roles.

## Run CHAOSLAB

With the project environment installed:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab --output var/evaluation.json
PYTHONPATH=src .runtime/bin/python -m chaoslab.recovery --output var/recovery.json
PYTHONPATH=src .runtime/bin/python -m pytest -q --basetemp=var/pytest-local
```

For a smaller starting point, the [four-answer example](examples/review-regression/README.md) compares deliberately written answers: one correct, one with a wrong decision, one with a broken citation and one missing an attempt. These are test fixtures, not model results.

## Why one repository?

ATLAS and CHAOSLAB are separate Python packages with different responsibilities. They share fixtures and CI so an application change can be checked against the evaluator in the same revision. CHAOSLAB also ships a dependency-free wheel for saved-run comparisons, contract scoring and trusted adapters. Retrieval probes that call ATLAS still require the full environment.

[Architecture](docs/architecture.md) · [Security assumptions](docs/threat-model.md) · [Current work and verification history](docs/STATUS.md)
