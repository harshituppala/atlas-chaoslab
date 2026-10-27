PYTHON ?= .runtime/bin/python
.PHONY: test benchmark serve worker web local

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q
benchmark:
	PYTHONPATH=src $(PYTHON) -m chaoslab --repeat 3
	PYTHONPATH=src $(PYTHON) -m chaoslab.recovery
	PYTHONPATH=src $(PYTHON) -m chaoslab.ingestion
serve:
	ATLAS_DEMO=1 PYTHONPATH=src $(PYTHON) -m atlas
web:
	cd apps/web && pnpm build

worker:
	PYTHONPATH=src $(PYTHON) -m atlas.worker

local:
	PYTHONPATH=src $(PYTHON) scripts/run_local_workbench.py
