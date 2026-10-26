"""Reject misleading database acceptance without exporting raw failure messages."""

import runpy
from pathlib import Path

import pytest
from defusedxml.common import DTDForbidden

admit = runpy.run_path(str(Path(__file__).parents[1] / "scripts/verify_postgres_ci.py"))[
    "admit_results"
]


def test_complete_execution_is_admitted():
    assert admit(
        b'<testsuite><testcase name="roles" time="1"/><testcase name="queue"/></testsuite>',
        {"roles", "queue"},
    ) == [{"id": "roles", "passed": True}, {"id": "queue", "passed": True}]


@pytest.mark.parametrize(
    "body",
    [
        '<testcase name="roles"/>',
        '<testcase name="roles"/><testcase name="roles"/>',
        '<testcase name="roles"/><testcase name="unknown"/>',
        '<testcase name="roles"><skipped/></testcase><testcase name="queue"/>',
        '<testcase name="roles"><failure>private connection detail</failure></testcase><testcase name="queue"/>',
        '<testcase name="roles"><error>private connection detail</error></testcase><testcase name="queue"/>',
        '<testcase name="roles" time="nan"/><testcase name="queue"/>',
        '<testcase name="roles" time="-1"/><testcase name="queue"/>',
    ],
)
def test_incomplete_or_unsuccessful_execution_is_not_acceptance(body):
    with pytest.raises(ValueError) as error:
        admit(("<testsuite>" + body + "</testsuite>").encode(), {"roles", "queue"})
    assert "private connection detail" not in str(error.value)


def test_dtd_and_oversized_evidence_are_refused():
    with pytest.raises(DTDForbidden):
        admit(b'<!DOCTYPE x [<!ENTITY secret "private">]><testsuite/>', {"roles"})
    with pytest.raises(ValueError):
        admit(b"x" * 4_000_001, {"roles"})
