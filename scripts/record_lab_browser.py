"""Project a passing real-browser lab run without cookies, traces or private logs."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report

EXPECTED = {
    "an external portfolio link opens the public lab in a new tab",
    "real analysis, exact sources, review conflicts across tabs, reload and logout",
    "mobile conflict review and a controlled capacity message recover without automatic retries",
    "client expiry clears a restored workspace using controlled lifetime metadata",
    "recorded evaluation at 1440px explains comparisons and failures without API calls",
    "recorded evaluation at 390px explains comparisons and failures without API calls",
}


def specifications(suites):
    for suite in suites:
        yield from suite.get("specs", [])
        yield from specifications(suite.get("suites", []))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = Path("var/lab-browser.json")
    raw = evidence.read_bytes()
    data = json.loads(raw)
    specs = list(specifications(data["suites"]))
    if len(specs) != len(EXPECTED) or {s["title"] for s in specs} != EXPECTED:
        raise ValueError("Expected all authored lab browser workflows")
    for spec in specs:
        if len(spec["tests"]) != 1:
            raise ValueError("Expected one actual Chromium execution per workflow")
        case = spec["tests"][0]
        if (
            case["expectedStatus"] != "passed"
            or len(case["results"]) != 1
            or case["results"][0]["status"] != "passed"
        ):
            raise ValueError("Browser gate did not pass without retries")
    if (
        data["stats"].get("expected") != len(EXPECTED)
        or any(data["stats"].get(k) != 0 for k in ("unexpected", "flaky", "skipped"))
        or data.get("errors")
    ):
        raise ValueError("Unexpected browser failures or omissions")
    sources = [
        "apps/web/src/lab.tsx",
        "apps/web/src/lab.css",
        "apps/web/src/Dialog.tsx",
        "apps/web/src/PublicHeader.tsx",
        "apps/web/src/PublicEvaluation.tsx",
        "apps/web/src/ContractTestPanel.tsx",
        "apps/web/src/ScenarioPanel.tsx",
        "reports/scenarios-baseline.json",
        "reports/scenarios-live-v4.json",
        "reports/reasoning-transfer-baseline.json",
        "reports/reasoning-transfer-live-v4.json",
        "reports/contract-model-test.json",
        "reports/contract-model-test-standalone-replay.json",
        "datasets/reasoning-transfer.json",
        "apps/web/lab/index.html",
        "apps/web/vite.lab.config.ts",
        "apps/web/playwright.lab.config.ts",
        "apps/web/lab-e2e/lab.spec.ts",
        "apps/web/package.json",
        "scripts/record_lab_browser.py",
    ]
    build = Path("apps/web/dist-lab")
    assets = sorted(p for p in build.rglob("*") if p.is_file())
    if not assets or not (build / "index.html").exists():
        raise ValueError("Expected the built lab artifact")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Six Chromium workflows against the built React lab. Three exercise the actual loopback API; two inspect saved evaluation results with no API requests or cookies; one follows a controlled external portfolio link in a new tab. Baseline computation is real. Capacity feedback uses a controlled 503; client expiry uses a shortened metadata lifetime while server state remains valid. No hosted TLS/provider or ten-minute wall-clock expiry claim.",
        "browser_cases_passed": len(specs),
        "workflows": [s["title"] for s in specs],
        "privacy_scope": "Projects only authored test names, counts and hashes. No cookies, headers, session identifiers, source payloads, stderr, attachments or trace content are exported.",
        "browser_evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "frontend_sha256": {p: digest(Path(p)) for p in sources},
        "backend_source_sha256": source_manifest()["source_sha256"],
        "build_sha256": {p.relative_to(build).as_posix(): digest(p) for p in assets},
        "screenshots_sha256": {
            p: digest(Path(p))
            for p in [
                "var/ui-review/screenshots/synthetic-workbench.png",
                "var/ui-review/screenshots/synthetic-workbench-mobile.png",
                "var/ui-review/screenshots/public-evaluation-1440.png",
                "var/ui-review/screenshots/public-evaluation-390.png",
                "var/ui-review/screenshots/contract-test-1440.png",
                "var/ui-review/screenshots/contract-test-390.png",
            ]
        },
        "identity_scope": "Source/build/screenshot hashes captured after the actual browser run; no frozen-run, signed execution or full loaded-dependency attestation. Separate ASGI evidence checks its own source before/after.",
        "new_model_provider_calls": 0,
    }
    publish_report(Path("reports/synthetic-lab-browser.json"), report)
    print(json.dumps({"browser_cases_passed": len(specs), "build_files": len(assets)}))


if __name__ == "__main__":
    main()
