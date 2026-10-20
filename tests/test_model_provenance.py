from pathlib import Path

import pytest

from atlas.models.provenance import source_manifest


def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("value = 1\n")
    (tmp_path / "requirements.lock").write_text("example==1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    return tmp_path


def test_manifest_binds_source_and_locks_but_excludes_private_data(tmp_path):
    root = project(tmp_path)
    before = source_manifest(root)
    (root / "private-secret.json").write_text("private-secret")
    assert source_manifest(root) == before
    assert all(not Path(name).is_absolute() for name in before["files"])
    for name in ("src/module.py", "requirements.lock"):
        path = root / name
        original = path.read_text()
        path.write_text(original + "changed\n")
        assert source_manifest(root)["source_sha256"] != before["source_sha256"]
        path.write_text(original)
    assert source_manifest(root) == before


def test_manifest_rejects_symlinks_and_missing_lock(tmp_path):
    root = project(tmp_path)
    (root / "src" / "link.py").symlink_to(root / "requirements.lock")
    with pytest.raises(ValueError):
        source_manifest(root)
    (root / "src" / "link.py").unlink()
    (root / "requirements.lock").unlink()
    with pytest.raises(FileNotFoundError):
        source_manifest(root)
