"""Reproduce the pinned local integration runtime without a global installation.

Free source downloads occur only when explicitly running this preparation script.
No database is initialized or started here. Requires an existing C toolchain.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

POSTGRES = {
    "version": "18.6",
    "source": "https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2",
    "sha256": "555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f",
}
VECTOR = {
    "version": "v0.8.7",
    "commit": "f37c13f68b57d2c3472b2214fbcff699d6d34876",
    "source": "https://codeload.github.com/pgvector/pgvector/tar.gz/f37c13f68b57d2c3472b2214fbcff699d6d34876",
    "sha256": "83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56",
}


def prepare_source(cache, name, source, maximum):
    archive = cache / name
    if not archive.exists():
        with urllib.request.urlopen(source["source"], timeout=60) as response:
            raw = response.read(maximum + 1)
        if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise RuntimeError("Runtime source download failed its pinned checksum")
        archive.write_bytes(raw)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("Cached runtime source differs from its pinned checksum")
    with tarfile.open(archive) as package:
        package.extractall(cache, filter="data")


def run_step(command, directory, log):
    with log.open("w") as output:
        result = subprocess.run(command, cwd=directory, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError("Runtime build step failed; inspect the local build log: " + log.name)


def verify(root):
    runtime = root / ".runtime/postgresql"
    version = subprocess.check_output(
        [str(runtime / "bin/postgres"), "--version"], text=True
    ).strip()
    shared = Path(
        subprocess.check_output([str(runtime / "bin/pg_config"), "--sharedir"], text=True).strip()
    )
    if not shared.is_relative_to(runtime):
        raise RuntimeError("Installed runtime data directory is outside the repository runtime")
    control = (shared / "extension/vector.control").read_text()
    if not version.endswith(POSTGRES["version"]) or "default_version = '0.8.7'" not in control:
        raise RuntimeError("Installed runtime identity differs from pinned versions")
    print(
        json.dumps(
            {
                "runtime_verified": True,
                "postgres": POSTGRES["version"],
                "pgvector": VECTOR["version"],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the existing runtime without downloads or builds",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.check:
        verify(root)
        return
    binary = root / ".runtime/postgresql/bin/pg_ctl"
    data = root / "var/postgresql/data"
    if binary.exists() and (data / "PG_VERSION").exists():
        running = (
            subprocess.run([str(binary), "-D", str(data), "status"], capture_output=True).returncode
            == 0
        )
        if running:
            parser.error("Stop the private integration cluster before rebuilding its runtime")
    make = shutil.which("make")
    if not make or not (shutil.which("cc") or shutil.which("clang")):
        parser.error("An existing C compiler and GNU make are required")
    cache = root / ".cache/postgresql"
    cache.mkdir(parents=True, exist_ok=True)
    prepare_source(cache, "postgresql-18.6.tar.bz2", POSTGRES, 30_000_000)
    prepare_source(cache, "pgvector.tar.gz", VECTOR, 2_000_000)
    postgres = cache / "postgresql-18.6"
    vector = cache / ("pgvector-" + VECTOR["commit"])
    runtime = root / ".runtime/postgresql"
    run_step(
        [
            str(postgres / "configure"),
            "--prefix=" + str(runtime),
            "--without-icu",
            "--without-readline",
        ],
        postgres,
        cache / "configure.log",
    )
    run_step([make, "-j" + str(min(4, os.cpu_count() or 1))], postgres, cache / "build.log")
    run_step([make, "install"], postgres, cache / "install.log")
    pg_config = "PG_CONFIG=" + str(runtime / "bin/pg_config")
    run_step([make, pg_config], vector, cache / "pgvector-build.log")
    run_step([make, pg_config, "install"], vector, cache / "pgvector-install.log")
    (cache / "source-provenance.json").write_text(json.dumps(POSTGRES, indent=2) + "\n")
    (cache / "pgvector-provenance.json").write_text(json.dumps(VECTOR, indent=2) + "\n")
    verify(root)


if __name__ == "__main__":
    main()
