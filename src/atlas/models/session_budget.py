"""Conservative local spending reservations shared by cooperating CLI processes.

No automatic refunds: failed credential setup, process death and unknown provider
billing keep their full reservation until a human reconciles the authorization.
This is not an AWS account spending limit or a hostile-local-user boundary.
"""

import fcntl
import os
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from pydantic import Field

from atlas.artifacts import write_private_json
from atlas.domain import StrictModel


class Reservation(StrictModel):
    run_id: str = Field(min_length=1, max_length=512)
    reserved_usd: Decimal = Field(gt=0, le=100, allow_inf_nan=False)


class SessionBudget(StrictModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    authorized_usd: Decimal = Field(gt=0, le=100, allow_inf_nan=False)
    reservations: list[Reservation] = Field(default_factory=list, max_length=10000)

    @property
    def reserved_usd(self):
        return sum((r.reserved_usd for r in self.reservations), Decimal(0))


@contextmanager
def locked_budget(path):
    path = Path(path).absolute()
    root = (Path.cwd() / "var").resolve()
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError("Session budget must be a nonsymlink file under private var/")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if path.is_symlink():
            raise ValueError("Session budget must not be a symlink")
        yield path
    finally:
        os.close(fd)


def save(path, budget):
    write_private_json(path, budget.model_dump(mode="json"))
    # Persist the rename before permitting a billable invocation.
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def initialize(path, *, authorized_usd, prior_reserved_usd=Decimal(0)):
    """Operator-only setup after explicit user authorization; never reset a file."""
    budget = SessionBudget(authorized_usd=authorized_usd)
    prior = Decimal(prior_reserved_usd)
    if not prior.is_finite() or prior < 0:
        raise ValueError("Invalid prior reservation")
    if prior:
        budget.reservations.append(Reservation(run_id="prior-reviewed-usage", reserved_usd=prior))
    if budget.reserved_usd > budget.authorized_usd:
        raise ValueError("Prior reservations exceed authorization")
    with locked_budget(path) as target:
        if target.exists():
            raise FileExistsError("Existing session authorization must not be reset")
        save(target, budget)


def reserve(path, *, run_id, amount_usd):
    entry = Reservation(run_id=run_id, reserved_usd=amount_usd)
    with locked_budget(path) as target:
        if target.stat().st_size > 2_000_000:
            raise ValueError("Oversized session budget")
        budget = SessionBudget.model_validate_json(target.read_bytes())
        ids = [r.run_id for r in budget.reservations]
        if len(ids) != len(set(ids)) or run_id in ids:
            raise ValueError("Duplicate or previously reserved run")
        if len(ids) >= 10000 or budget.reserved_usd + entry.reserved_usd > budget.authorized_usd:
            raise ValueError("Cumulative session spending authorization exhausted")
        budget.reservations.append(entry)
        save(target, budget)
        return budget.reserved_usd


def reserve_configured_run(path, config, output):
    """Reserve all configured calls, even if a later case or SDK setup fails."""
    limits, card = config.limits, config.price_card
    per_call = (
        Decimal(limits.max_input_tokens) * card.input_usd_per_million
        + Decimal(limits.max_output_tokens) * card.output_usd_per_million
    ) / 1000000
    calls = min(
        limits.max_calls,
        limits.max_reserved_tokens // (limits.max_input_tokens + limits.max_output_tokens),
        int(limits.max_estimated_cost_usd // per_call),
    )
    if calls < 1:
        raise ValueError("Configuration cannot reserve one call")
    return reserve(path, run_id=str(Path(output).resolve()), amount_usd=per_call * calls)
