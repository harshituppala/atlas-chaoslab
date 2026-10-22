"""Check private login settings offline, or probe public provider endpoints explicitly."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from atlas.managed import read_settings
from atlas.security.provider import ProviderCheckFailed, check_provider

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "src/atlas/managed.py",
    "src/atlas/security/provider.py",
    "src/atlas/security/login.py",
    "src/atlas/security/tokens.py",
    "scripts/check_managed_provider.py",
)


def fingerprints():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument(
        "--provider", action="store_true", help="Contact pinned public HTTPS endpoints"
    )
    args = parser.parse_args()
    before = fingerprints()
    try:
        config = read_settings(args.settings)
        checks = check_provider(config) if args.provider else {"user_login_verified": False}
    except (ValueError, ProviderCheckFailed) as error:
        raise SystemExit(str(error)) from None
    if before != fingerprints():
        raise SystemExit("Source changed during provider check; report refused")
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Public discovery and signing-key checks"
        if args.provider
        else "Offline settings admission",
        "configuration_sha256": hashlib.sha256(
            json.dumps(asdict(config), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "files_sha256": before,
        "checks": {"settings_valid": True, **checks},
        "limitations": "No user credential, token, callback, registered scope/client, workspace membership or hosted service is validated. No inference or paid operation is requested.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
