"""Local container bootstrap must refuse implicit use and redact secret-bearing faults."""

import pytest

from atlas import local_stack


def test_stack_initializer_requires_explicit_local_opt_in(monkeypatch):
    monkeypatch.setattr("sys.argv", ["local-stack", "initialize"])
    monkeypatch.delenv("ATLAS_LOCAL_STACK", raising=False)
    monkeypatch.setattr(
        local_stack, "load_secret", lambda _: pytest.fail("Secret read before opt-in")
    )
    with pytest.raises(SystemExit, match="Local stack initialization/launch failed") as failure:
        local_stack.main()
    assert failure.value.__suppress_context__


def test_stack_initializer_never_prints_database_fault_content(monkeypatch, capsys):
    marker = "PRIVATE-DATABASE-PASSWORD-CANARY"
    monkeypatch.setattr("sys.argv", ["local-stack", "initialize"])
    monkeypatch.setenv("ATLAS_LOCAL_STACK", "1")
    monkeypatch.setattr(local_stack, "load_secret", lambda _: {"owner_password": marker})

    def fail(_settings):
        raise RuntimeError("Connection parameters and SQL: " + marker)

    monkeypatch.setattr(local_stack, "initialize", fail)
    with pytest.raises(SystemExit) as failure:
        local_stack.main()
    captured = capsys.readouterr()
    assert marker not in str(failure.value) + captured.out + captured.err
    assert failure.value.__suppress_context__


@pytest.mark.parametrize(
    "role,password",
    [
        ("postgres", "a" * 36),
        ("atlas_api; DROP ROLE atlas_worker", "a" * 36),
        ("atlas_api", "short"),
        ("atlas_worker", None),
        ("atlas_api", "a" * 129),
    ],
)
def test_stack_rejects_unexpected_connection_identity(role, password):
    with pytest.raises(ValueError):
        local_stack.database_url(role, password)


def test_stack_connection_preserves_delimiters_without_changing_endpoint():
    password = "unusual@:/?#'password" * 2
    from sqlalchemy.engine import make_url

    url = make_url(
        local_stack.database_url("atlas_api", password).render_as_string(hide_password=False)
    )
    assert url.password == password
    assert url.host == "postgres" and url.port == 5432 and url.database == "atlas"
    assert url.username == "atlas_api"
