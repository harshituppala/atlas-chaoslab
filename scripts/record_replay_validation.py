"""Record a completed local replay check without exporting private browser/test reports."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    browser_path = Path("var/replay-browser.json")
    junit_path = Path("var/replay-backend.xml")
    browser = json.loads(browser_path.read_text())
    if (
        browser["errors"]
        or browser["stats"]["expected"] != 3
        or any(browser["stats"][k] for k in ("unexpected", "flaky", "skipped"))
    ):
        raise ValueError("Replay browser checks did not all pass")
    cases = list(ET.fromstring(junit_path.read_bytes()).iter("testcase"))
    if not cases or any(c.find(tag) is not None for c in cases for tag in ("error", "failure")):
        raise ValueError("Backend verification failed or was empty")
    passed = sum(c.find("skipped") is None for c in cases)
    skipped = len(cases) - passed
    inputs = [
        "src/atlas/replay.py",
        "tests/test_replay.py",
        "apps/web/src/replay.tsx",
        "apps/web/src/replay.css",
        "apps/web/src/replay-data.json",
        "apps/web/src/Dialog.tsx",
        "apps/web/replay/index.html",
        "apps/web/vite.replay.config.ts",
        "apps/web/playwright.replay.config.ts",
        "apps/web/replay-e2e/replay.spec.ts",
        "apps/web/package.json",
        "apps/web/pnpm-lock.yaml",
        "scripts/record_replay_validation.py",
    ]
    artifacts = sorted(p for p in Path("apps/web/dist-replay").rglob("*") if p.is_file())
    if not artifacts or not Path("apps/web/dist-replay/index.html").is_file():
        raise ValueError("Static build is missing")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Executed local Chromium static-artifact checks and native backend regression suite. No deployment or new inference. Not a complete accessibility/security audit.",
        "browser": {"passed": 3, "skipped": 0, "duration_ms": browser["stats"]["duration"]},
        "backend": {"passed": passed, "skipped": skipped},
        "checks": [
            "baseline_and_historical_recording",
            "exact_citation_highlight",
            "keyboard_dialog_and_focus_return",
            "search_empty_state",
            "known_failures_visible",
            "no_api_or_external_requests",
            "empty_browser_storage",
            "csp_blocks_fetch",
            "390px_mobile_no_horizontal_overflow",
            "source_projection_privacy_and_tamper_rejection",
        ],
        "input_sha256": {p: digest(p) for p in inputs},
        "build_sha256": {str(p): digest(p) for p in artifacts},
        "execution_report_sha256": {"browser": digest(browser_path), "backend": digest(junit_path)},
        "hash_scope": "On-disk hashes captured after executed checks; no frozen pre-run attestation, loaded-code proof, remote CI or host-header validation is implied.",
    }
    Path("reports/replay-validation.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
