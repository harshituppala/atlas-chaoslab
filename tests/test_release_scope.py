"""Publication admits the named fictional example without widening private paths."""

import runpy
from pathlib import Path

import pytest

allowed = runpy.run_path(str(Path(__file__).parents[1] / "scripts/prepare_release.py"))["allowed"]


@pytest.mark.parametrize(
    "name",
    [
        "examples/review-regression/dataset.json",
        "examples/review-regression/reference.json",
        "examples/review-regression/README.md",
    ],
)
def test_named_public_example_is_included(name):
    assert allowed(name)


@pytest.mark.parametrize(
    "name",
    [
        "examples/unreviewed/observations.json",
        "examples/review-regression/.env",
        "examples/review-regression/var/observations.jsonl",
        "examples/review-regression/private.key",
        "examples/review-regression/../../var/data.json",
        "/examples/review-regression/dataset.json",
        "docs/interview-practice.md",
        "docs/portfolio-delivery.md",
        "var/bedrock/usage.json",
    ],
)
def test_private_or_unreviewed_paths_remain_excluded(name):
    assert not allowed(name)
