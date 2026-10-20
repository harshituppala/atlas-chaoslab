import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from test_model_gateway import config as config

from atlas.models import session_budget as sb


@pytest.fixture
def budget(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "var" / "campaign.json"
    sb.initialize(path, authorized_usd="1", prior_reserved_usd="0.20")
    return path


def test_restarts_and_duplicate_runs_do_not_reset_allowance(budget):
    assert sb.reserve(budget, run_id="one", amount_usd="0.50") == Decimal("0.70")
    with pytest.raises(ValueError, match="previously reserved"):
        sb.reserve(budget, run_id="one", amount_usd="0.01")
    with pytest.raises(ValueError, match="exhausted"):
        sb.reserve(budget, run_id="after-crash", amount_usd="0.31")
    with pytest.raises(FileExistsError):
        sb.initialize(budget, authorized_usd="100")
    assert sb.SessionBudget.model_validate_json(budget.read_bytes()).reserved_usd == Decimal("0.70")


def test_concurrent_reservations_cannot_overspend(budget):
    def attempt(i):
        try:
            sb.reserve(budget, run_id=str(i), amount_usd="0.20")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(20)))
    assert sum(results) == 4
    assert sb.SessionBudget.model_validate_json(budget.read_bytes()).reserved_usd == 1


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_nonfinite_and_nonpositive_reservations_rejected(budget, value):
    before = budget.read_bytes()
    with pytest.raises(ValueError):
        sb.reserve(budget, run_id="bad", amount_usd=value)
    assert budget.read_bytes() == before


def test_corruption_and_duplicate_journal_entries_fail_closed(budget):
    data = json.loads(budget.read_text())
    data["reservations"] *= 2
    budget.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate"):
        sb.reserve(budget, run_id="new", amount_usd="0.01")
    budget.write_text("{broken")
    with pytest.raises(ValueError):
        sb.reserve(budget, run_id="new", amount_usd="0.01")


def test_private_path_and_symlink_refusal(budget, tmp_path):
    outside = tmp_path / "outside.json"
    with pytest.raises(ValueError, match="private var"):
        sb.initialize(outside, authorized_usd="1")
    alias = budget.with_name("alias.json")
    alias.symlink_to(budget)
    with pytest.raises(ValueError):
        sb.reserve(alias, run_id="bad", amount_usd="0.01")
    assert budget.stat().st_mode & 0o777 == 0o600


def test_write_failure_cannot_authorize_call_or_erase_previous_budget(budget, monkeypatch):
    before = budget.read_bytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(sb, "write_private_json", fail)
    with pytest.raises(OSError):
        sb.reserve(budget, run_id="not-authorized", amount_usd="0.1")
    assert budget.read_bytes() == before


def test_configuration_reserves_whole_run_before_sdk_setup(budget, config):
    total = sb.reserve_configured_run(budget, config, "var/run.json")
    # Three calls, each 1000 input at $1/M plus 100 output at $2/M.
    assert total == Decimal("0.2036")


def test_separate_processes_share_the_same_lock(budget):
    import os
    import subprocess
    import sys
    from pathlib import Path

    source = Path(sb.__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1"}
    code = "from atlas.models.session_budget import reserve; import sys; reserve(sys.argv[1], run_id=sys.argv[2], amount_usd='0.4')"
    children = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(budget), str(i)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for i in range(6)
    ]
    outcomes = [child.wait(timeout=15) for child in children]
    assert outcomes.count(0) == 2
    assert sb.SessionBudget.model_validate_json(budget.read_bytes()).reserved_usd == 1
