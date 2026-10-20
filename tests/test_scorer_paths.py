"""Scorer fingerprints must follow loaded files, not the caller's directory."""

import hashlib
from pathlib import Path

from chaoslab.__main__ import source_digest
from chaoslab.comparison import scorer_hashes


def test_scorer_hashes_do_not_trust_a_lookalike_working_directory(tmp_path, monkeypatch):
    expected = scorer_hashes()
    fake = tmp_path / "src/chaoslab"
    fake.mkdir(parents=True)
    for name in expected:
        (fake / Path(name).name).write_text("not the loaded scorer")
    monkeypatch.chdir(tmp_path)
    assert scorer_hashes() == expected


def test_source_digest_is_not_empty_or_controlled_by_the_working_directory(tmp_path, monkeypatch):
    expected = source_digest()
    assert expected != hashlib.sha256(b"").hexdigest()
    monkeypatch.chdir(tmp_path)
    assert source_digest() == expected
    (tmp_path / "src").mkdir()
    (tmp_path / "src/unrelated.py").write_text("different application")
    assert source_digest() == expected
