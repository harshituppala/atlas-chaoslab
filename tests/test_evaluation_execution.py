"""Bounded trusted-adapter invocation; source data and stderr never enter reports."""

import os
from pathlib import Path

import pytest

from chaoslab.execution import AdapterDeadline, AdapterFailure, AdapterOutputBudget, invoke


@pytest.fixture
def adapters(tmp_path, monkeypatch):
    module = tmp_path / "evaluation_fixture.py"
    module.write_text("""
import sys, time
from pathlib import Path

def mutate(body, fault):
    body["secret"] = "changed"
    return {"seen": body}

def hang(body, fault):
    Path(body["marker"]).write_text("entered")
    while True:
        time.sleep(0.1)

def oversized(body, fault):
    sys.stdout.write("x" * 3000000)
    sys.stdout.flush()
    return {}

def fail(body, fault):
    raise RuntimeError("PRIVATE-SOURCE-CANARY")

def malformed(body, fault):
    print("unexpected output")
    return {}
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + str(Path("src").resolve()))
    return "evaluation_fixture:"


def test_adapter_mutation_cannot_change_judge_input(adapters):
    body = {"secret": "original"}
    output = invoke(adapters + "mutate", body)
    assert body == {"secret": "original"} and output["seen"]["secret"] == "changed"


def test_hung_adapter_is_terminated_by_parent_deadline(adapters, tmp_path):
    marker = tmp_path / "entered"
    with pytest.raises(AdapterDeadline):
        invoke(adapters + "hang", {"marker": str(marker)}, deadline_seconds=0.5)
    assert marker.read_text() == "entered"


def test_excess_output_is_refused(adapters):
    with pytest.raises(AdapterOutputBudget):
        invoke(adapters + "oversized", {})


@pytest.mark.parametrize("name", ["fail", "malformed"])
def test_adapter_failure_does_not_disclose_private_stderr(adapters, name):
    with pytest.raises(AdapterFailure) as caught:
        invoke(adapters + name, {"private": "PRIVATE-SOURCE-CANARY"})
    assert "PRIVATE-SOURCE-CANARY" not in str(caught.value)


def test_input_budget_and_explicit_adapter_selection(adapters):
    with pytest.raises(AdapterOutputBudget):
        invoke(adapters + "mutate", {"text": "x" * 1500000})
    with pytest.raises(ValueError):
        invoke("bad;module:run", {})
