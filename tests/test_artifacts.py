import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from atlas.artifacts import reserve_invocation_artifacts, write_private_json


def test_concurrent_invocation_artifacts_have_one_owner(tmp_path):
    output = tmp_path / "run.json"

    def reserve():
        try:
            reserve_invocation_artifacts(output)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: reserve(), range(8))) == 1
    reservation = output.with_suffix(".reservation.json")
    assert json.loads(reservation.read_text())["invocation_id"]
    assert reservation.stat().st_mode & 0o777 == 0o600
    # Even without a completed report, interrupted ownership cannot be reused.
    with pytest.raises(FileExistsError):
        reserve_invocation_artifacts(output)


@pytest.mark.parametrize("suffix", [".json", ".ledger.json"])
def test_existing_billing_or_source_artifact_is_preserved(tmp_path, suffix):
    output = tmp_path / "run.json"
    existing = output.with_suffix(suffix)
    write_private_json(existing, {"cost": "unknown", "sentinel": True})
    with pytest.raises(FileExistsError):
        reserve_invocation_artifacts(output)
    assert json.loads(existing.read_text()) == {"cost": "unknown", "sentinel": True}
    assert not output.with_suffix(".reservation.json").exists()


def test_directory_flush_failure_never_grants_invocation_ownership(tmp_path, monkeypatch):
    import atlas.artifacts as artifacts

    output = tmp_path / "run.json"
    monkeypatch.setattr(
        artifacts, "sync_directory", lambda _: (_ for _ in ()).throw(OSError("flush failed"))
    )
    with pytest.raises(OSError):
        reserve_invocation_artifacts(output)
    assert output.with_suffix(".reservation.json").exists()
    with pytest.raises(FileExistsError):
        reserve_invocation_artifacts(output)


def test_new_artifact_directories_and_file_entries_are_flushed(tmp_path, monkeypatch):
    import atlas.artifacts as artifacts

    flushed = []
    real = artifacts.sync_directory

    def capture(path):
        flushed.append(path)
        real(path)

    monkeypatch.setattr(artifacts, "sync_directory", capture)
    output = tmp_path / "first" / "second" / "run.json"
    reserve_invocation_artifacts(output)
    assert flushed == [tmp_path, tmp_path / "first", output.parent]


def test_nonfinite_private_artifact_preserves_previous_receipt(tmp_path):
    output = tmp_path / "receipt.json"
    write_private_json(output, {"status": "invocation_unknown"})
    with pytest.raises(ValueError):
        write_private_json(output, {"cost": float("nan")})
    assert json.loads(output.read_text()) == {"status": "invocation_unknown"}
    assert list(tmp_path.iterdir()) == [output]
