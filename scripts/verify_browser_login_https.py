"""Compose real loopback TLS, Chromium and ATLAS with a synthetic identity provider.

No AWS resources or real user identity are used. Chromium trusts only the fixture
certificate's SPKI for this subprocess; the OS trust store is never modified.
"""

import argparse
import atexit
import base64
import hashlib
import ipaddress
import json
import os
import select
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from login_browser_fixture import create_fixture

ROOT = Path(__file__).resolve().parents[1]


def fingerprints():
    paths = (
        sorted((ROOT / "src/atlas").rglob("*.py"))
        + [
            ROOT / "scripts/login_browser_fixture.py",
            ROOT / "scripts/browser_login_https.mjs",
            Path(__file__).resolve(),
        ]
        + sorted((ROOT / "apps/web/src").glob("*.tsx"))
    )
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }


def certificate(work):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ATLAS local fixture")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    private = work / "tls-key.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    public = work / "tls-cert.pem"
    public.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    spki = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return public, private, base64.b64encode(hashlib.sha256(spki).digest()).decode()


def proxy_for(port):
    class Tunnel(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_CONNECT(self):
            if self.path not in {"localhost:443", "127.0.0.1:443"}:
                self.send_error(403)
                return
            with socket.create_connection(("127.0.0.1", port), timeout=5) as upstream:
                self.send_response(200)
                self.end_headers()
                sockets = [self.connection, upstream]
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    ready, _, _ = select.select(sockets, [], [], 1)
                    for source in ready:
                        try:
                            block = source.recv(65536)
                            if not block:
                                return
                            (upstream if source is self.connection else self.connection).sendall(
                                block
                            )
                        except OSError:
                            return

    return ThreadingHTTPServer(("127.0.0.1", 0), Tunnel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm-script")
    args = parser.parse_args()
    frozen = fingerprints()
    work = ROOT / "var/browser-login-https" / uuid4().hex[:12]
    work.mkdir(parents=True, mode=0o700)
    cert, private, spki = certificate(work)
    atexit.register(private.unlink, missing_ok=True)
    temporary_directory = work / "tmp"
    temporary_directory.mkdir(mode=0o700)
    environment = {
        **os.environ,
        "TMPDIR": str(temporary_directory),
        "TMP": str(temporary_directory),
        "TEMP": str(temporary_directory),
        "XDG_CACHE_HOME": str(ROOT / ".cache"),
        "XDG_CONFIG_HOME": str(work / "config"),
    }
    command = [args.node, args.pnpm_script] if args.pnpm_script else ["pnpm"]
    build = subprocess.run(
        [*command, "build"], cwd=ROOT / "apps/web", env=environment, capture_output=True
    )
    (work / "build.log").write_bytes(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError("Frontend build failed")
    assets = {
        p.relative_to(ROOT / "apps/web/dist").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "apps/web/dist").rglob("*"))
        if p.is_file()
    }
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    proxy = proxy_for(listener.getsockname()[1])
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    proxy_url = f"http://127.0.0.1:{proxy.server_port}"
    # Paid inference profiles cannot be enabled by an inherited local environment.
    for name in ("ATLAS_MODEL_JOB_SPEC", "ATLAS_ENABLE_BEDROCK_JOBS", "ATLAS_TOKEN_TRUST"):
        os.environ.pop(name, None)
    app, metrics, close = create_fixture(
        work, proxy_url, cert, rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=listener.getsockname()[1],
            ssl_keyfile=str(private),
            ssl_certfile=str(cert),
            access_log=False,
            log_level="critical",
            lifespan="off",
        )
    )
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("Loopback TLS server did not start")
        result = subprocess.run(
            [args.node, str(ROOT / "scripts/browser_login_https.mjs")],
            cwd=ROOT,
            env={
                **environment,
                "ATLAS_FIXTURE_PROXY": proxy_url,
                "ATLAS_FIXTURE_SPKI": spki,
                "ATLAS_FIXTURE_SCREENSHOT": str(work / "workbench.png"),
            },
            capture_output=True,
            timeout=120,
        )
        (work / "browser.json").write_bytes(result.stdout)
        (work / "browser.log").write_bytes(result.stderr)
        (work / "fixture-metrics.json").write_text(json.dumps(metrics))
        if result.returncode:
            raise RuntimeError(
                f"Composed browser acceptance failed; inspect {work.relative_to(ROOT)}"
            )
        observed = json.loads(result.stdout)
        if len(observed["checks"]) != 12 or not all(observed["checks"].values()):
            raise RuntimeError("Incomplete browser acceptance")
        if not (
            metrics["token_exchanges"] == metrics["authorized"] == 2
            and metrics["jwks_requests"] >= 1
            and metrics["pkce_rejections"] == 0
            and metrics.get("same_origin_form_post") is True
            and metrics.get("external_referrer_absent") is True
        ):
            raise RuntimeError("Unexpected synthetic provider observations")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        close()
        listener.close()
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        private.unlink(missing_ok=True)
    if frozen != fingerprints():
        raise RuntimeError("Source changed during acceptance; publication refused")
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Chromium through a loopback-only CONNECT proxy to a real TLS server, ATLAS UI/API and a synthetic passwordless provider with real S256, token exchange, JWKS and RSA signature verification. Not AWS/Cognito or a real user login.",
        "browser": observed["browser"],
        "checks": observed["checks"],
        "fixture_counts": metrics,
        "files_sha256": frozen,
        "built_assets_sha256": assets,
        "browser_result_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "tls": {
            "server": "short-lived self-signed fixture certificate",
            "browser_trust": "subprocess-only pinned certificate SPKI exception",
            "backend_trust": "fixture certificate CA and hostname verification",
            "system_trust_modified": False,
        },
        "browser_temporary_profile": "Verified inside this run's private var/browser-login-https directory via Chromium command-line inspection.",
        "external_provider_calls": 0,
        "cloud_resources_created": 0,
        "limits": "Synthetic identity and local SQLite only. Provider includes local control routes that must never be deployed. Server expiry uses a controlled monotonic-clock offset. No real provider configuration, public CA trust, deployed proxy, durable hosting, refresh or distributed-session acceptance.",
    }
    temporary = work / "report.json"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(temporary, ROOT / "reports/browser-login-https.json")
    print(json.dumps({"checks_passed": len(observed["checks"]), "fixture_counts": metrics}))


if __name__ == "__main__":
    main()
