"""Record offline Cognito-profile evidence from an actual JUnit run and Linux verifier."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report


def main():
    path = Path("var/cognito-profile-tests.xml")
    raw = path.read_bytes()
    cases = [
        c
        for c in ET.fromstring(raw).iter("testcase")
        if c.attrib.get("classname", "").endswith("test_cognito_tokens")
    ]
    if not cases or any(
        c.find(tag) is not None for c in cases for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("Expected a successful actually executed Cognito-profile test group")
    image = json.loads(Path("reports/container.json").read_text())
    if image["image_source_sha256"] != source_manifest()["source_sha256"]:
        raise ValueError("Current source differs from the verified image")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "profile": "cognito-resource",
        "host_profile_cases_passed": len(cases),
        "host_junit_sha256": hashlib.sha256(raw).hexdigest(),
        "test_file_sha256": hashlib.sha256(
            Path("tests/test_cognito_tokens.py").read_bytes()
        ).hexdigest(),
        "token_module_sha256": hashlib.sha256(
            Path("src/atlas/security/tokens.py").read_bytes()
        ).hexdigest(),
        "linux_image_id": image["image_id"],
        "linux_suite_counts": image["counts"],
        "image_source_sha256": image["image_source_sha256"],
        "linux_verification_input_sha256": image["verification_input_sha256"],
        "scope": "Offline real RSA signatures, controlled JWKS and actual SQLite API membership/"
        "revocation tests. Host file identities recorded after execution. The separate Linux "
        "verifier froze inputs before execution and matched image source to the host. "
        "Local hashes are not signed attestations. No real Cognito pool/login, browser PKCE, "
        "managed token issuance, deployed identity, cloud resources or billing were exercised.",
    }
    publish_report(Path("reports/cognito-profile.json"), report)
    print(
        json.dumps(
            {
                "offline_profile_cases_passed": len(cases),
                "linux_suite_passed": image["counts"]["passed"],
            }
        )
    )


if __name__ == "__main__":
    main()
