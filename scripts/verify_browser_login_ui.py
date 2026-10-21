"""Build and check the sign-in interface with intercepted Chromium HTTP responses.

This runner creates no cloud resources and performs no real identity-provider login.
Use --pnpm-script and --node for a bundled pnpm installation, or pnpm on PATH.
"""

import argparse
import functools
import hashlib
import json
import os
import subprocess
import threading
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "apps/web/src/AuthBoundary.tsx",
    "apps/web/src/main.tsx",
    "apps/web/src/style.css",
    "apps/web/e2e/browser-login.spec.ts",
    "apps/web/package.json",
    "apps/web/pnpm-lock.yaml",
    "src/atlas/api.py",
    "src/atlas/security/browser.py",
    "src/atlas/http_privacy.py",
    "tests/test_browser_sessions.py",
    "tests/test_http_privacy.py",
    "scripts/verify_browser_login_ui.py",
]
POLICY = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self' https://identity.example.invalid"


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def end_headers(self):
        self.send_header("Content-Security-Policy", POLICY)
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm-script")
    args = parser.parse_args()
    command = [args.node, args.pnpm_script] if args.pnpm_script else ["pnpm"]
    before = hashes()
    work = ROOT / "var/browser-login-ui" / uuid4().hex[:12]
    work.mkdir(parents=True)
    env = {**os.environ, "XDG_CACHE_HOME": str(ROOT / ".cache")}
    build = subprocess.run([*command, "build"], cwd=ROOT / "apps/web", env=env, capture_output=True)
    (work / "build.log").write_bytes(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError("Frontend build failed")
    built = {
        p.relative_to(ROOT / "apps/web/dist").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "apps/web/dist").rglob("*"))
        if p.is_file()
    }
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT / "apps/web/dist"))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        browser = subprocess.run(
            [
                *command,
                "exec",
                "playwright",
                "test",
                "e2e/browser-login.spec.ts",
                "--workers=1",
                "--reporter=json",
            ],
            cwd=ROOT / "apps/web",
            env={**env, "ATLAS_TEST_URL": f"http://127.0.0.1:{server.server_port}"},
            capture_output=True,
        )
        (work / "chromium.json").write_bytes(browser.stdout)
        (work / "chromium.log").write_bytes(browser.stderr)
        if browser.returncode:
            raise RuntimeError(f"Controlled browser checks failed; see {work.relative_to(ROOT)}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    result = json.loads(browser.stdout)
    if before != hashes():
        raise RuntimeError("Source changed during verification; report refused")
    stats = result["stats"]
    if stats["unexpected"] or stats["flaky"] or stats["skipped"] or stats["expected"] < 7:
        raise RuntimeError("Incomplete browser verification")
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Chromium rendering a loopback HTTP build, with intercepted sign-in/API/provider responses and a restricted form-action policy. No real provider, TLS, signed-token exchange or cookie enforcement verified by this run.",
        "files_sha256": before,
        "built_files_sha256": built,
        "chromium_result_sha256": hashlib.sha256(browser.stdout).hexdigest(),
        "checks": stats,
        "real_provider_calls": 0,
        "cloud_resources_created": 0,
        "limits": "The backend's controlled HTTP tests cover signed tokens and cookies separately. These UI checks do not compose them into a real external identity flow; default managed login remains disabled.",
    }
    temporary = work / "report.json"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(temporary, ROOT / "reports/browser-login-ui.json")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
