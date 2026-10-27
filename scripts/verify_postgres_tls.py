"""Local database TLS acceptance using a cached PostgreSQL image and fictional inputs.

Owns only its uniquely named container/network. No downloads, cloud services,
model calls or system trust changes. Docker administrators are trusted.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from atlas.api import create_app
from atlas.domain import Citation, Document
from atlas.migrations import upgrade
from atlas.store import Store
from chaoslab.artifacts import publish_report

ROOT = Path(__file__).resolve().parents[1]


def certificates(work):
    now = datetime.now(UTC)
    authority_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    authority_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ATLAS fixture CA")])
    authority = (
        x509.CertificateBuilder()
        .subject_name(authority_name)
        .issuer_name(authority_name)
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(authority_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for name, start, end in (
        ("server", now - timedelta(minutes=5), now + timedelta(hours=1)),
        ("expired", now - timedelta(days=2), now - timedelta(days=1)),
    ):
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ATLAS database")]))
            .issuer_name(authority_name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(start)
            .not_valid_after(end)
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(authority_key, hashes.SHA256())
        )
        (work / (name + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (work / "root.crt").write_bytes(authority.public_bytes(serialization.Encoding.PEM))
    # Only the server key is persisted. Readable within a private 0700 fixture
    # directory so the non-root container can copy it to its own 0600 data file.
    (work / "server.key").write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    # A different self-signed trust anchor is enough to exercise chain refusal.
    wrong_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unrelated fixture CA")])
    wrong = (
        x509.CertificateBuilder()
        .subject_name(wrong_name)
        .issuer_name(wrong_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(server_key, hashes.SHA256())
    )
    (work / "wrong-root.crt").write_bytes(wrong.public_bytes(serialization.Encoding.PEM))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--image", default="pgvector/pgvector:pg17")
    args = parser.parse_args()
    name = "atlastls" + uuid4().hex[:12]
    work = ROOT / "var/postgres-tls" / name
    work.mkdir(parents=True, mode=0o700)
    certificates(work)
    passwords = {role: secrets.token_urlsafe(36) for role in ("owner", "api", "worker")}
    (work / "password").write_text(passwords["owner"])
    (work / "pg_hba.conf").write_text(
        "local all all trust\nhostnossl all all all reject\nhostssl all all all scram-sha-256\n"
    )
    for path in work.iterdir():
        path.chmod(0o644)
    log = (work / "execution.log").open("w")
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}

    def docker(*command, check=True):
        return subprocess.run(
            [args.docker, *command],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            timeout=90,
            check=check,
        ).stdout.strip()

    stores = []
    engine = None
    try:
        image = docker("image", "inspect", args.image, "--format", "{{.Id}}")
        uid = docker(
            "run", "--rm", "--network", "none", "--pull=never", image, "id", "-u", "postgres"
        )
        assert uid.isdigit()
        docker("network", "create", name)
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--pull=never",
            "--network",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--user",
            uid + ":" + uid,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "512m",
            "--pids-limit",
            "128",
            "--tmpfs",
            f"/var/lib/postgresql/data:rw,uid={uid},gid={uid},mode=0700",
            "--tmpfs",
            f"/var/run/postgresql:rw,uid={uid},gid={uid},mode=0700",
            "--tmpfs",
            "/tmp:rw,mode=1777",
            "--mount",
            f"type=bind,src={work},dst=/fixture,readonly",
            "--env",
            "POSTGRES_USER=atlas_owner",
            "--env",
            "POSTGRES_DB=postgres",
            "--env",
            "POSTGRES_PASSWORD_FILE=/fixture/password",
            "--env",
            "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
            "--entrypoint",
            "sh",
            image,
            "-c",
            'cp /fixture/server.key /tmp/server.key; chmod 600 /tmp/server.key; exec docker-entrypoint.sh "$@"',
            "sh",
            "postgres",
            "-c",
            "ssl=on",
            "-c",
            "ssl_cert_file=/fixture/server.crt",
            "-c",
            "ssl_key_file=/tmp/server.key",
            "-c",
            "ssl_min_protocol_version=TLSv1.2",
            "-c",
            "hba_file=/fixture/pg_hba.conf",
        )
        for _ in range(5):
            binding = docker("port", name, "5432/tcp", check=False)
            if binding:
                break
            time.sleep(0.1)
        assert binding.startswith("127.0.0.1:") and "\n" not in binding
        base = dict(
            host="127.0.0.1",
            port=int(binding.split(":")[-1]),
            dbname="postgres",
            user="atlas_owner",
            password=passwords["owner"],
            sslmode="verify-full",
            sslrootcert=str(work / "root.crt"),
            connect_timeout=2,
        )
        for _ in range(100):
            try:
                with psycopg.connect(**base):
                    break
            except psycopg.OperationalError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Disposable TLS database did not become ready")
        urls = {
            role: URL.create(
                "postgresql+psycopg",
                username="atlas_" + role,
                password=password,
                host=base["host"],
                port=base["port"],
                database="postgres",
                query={
                    "sslmode": "verify-full",
                    "sslrootcert": base["sslrootcert"],
                    "options": "-csearch_path=atlas,public",
                },
            ).render_as_string(hide_password=False)
            for role, password in passwords.items()
        }
        engine = create_engine(urls["owner"])
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA atlas AUTHORIZATION atlas_owner")
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.exec_driver_sql("REVOKE ALL ON DATABASE postgres FROM PUBLIC")
        upgrade(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql((ROOT / "deployment/postgres-runtime-roles.sql").read_text())
            for role in ("api", "worker"):
                driver = connection.connection.driver_connection
                driver.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier("atlas_" + role), sql.Literal(passwords[role])
                    )
                )
                driver.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE postgres TO {}").format(
                        sql.Identifier("atlas_" + role)
                    )
                )
        observed = {}
        for role in ("api", "worker"):
            store = Store(urls[role], purpose=role)
            stores.append(store)
            with store.engine.connect() as connection:
                row = dict(
                    connection.execute(
                        text(
                            "SELECT current_user AS role, rolsuper AS superuser, rolbypassrls AS bypass, "
                            "ssl, version AS protocol, cipher, bits FROM pg_roles, pg_stat_ssl "
                            "WHERE rolname=current_user AND pid=pg_backend_pid()"
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["ssl"] and row["protocol"] in {"TLSv1.2", "TLSv1.3"}
                assert row["bits"] >= 128 and row["superuser"] is False
                assert row["bypass"] is (role == "worker")
                observed[role] = row
            denied = (
                ["UPDATE atlas.memberships SET active=false WHERE false"]
                if role == "api"
                else [
                    "SELECT * FROM atlas.memberships",
                    "UPDATE atlas.reviews SET version=version WHERE false",
                ]
            )
            for statement in denied:
                try:
                    with store.engine.begin() as connection:
                        connection.exec_driver_sql(statement)
                except DBAPIError as error:
                    assert error.orig.sqlstate == "42501"
                else:
                    raise AssertionError("Runtime privilege unexpectedly admitted")
        refusals = {}
        for label, changes, fragment in (
            (
                "wrong_authority",
                {"sslrootcert": str(work / "wrong-root.crt")},
                "certificate verify failed",
            ),
            (
                "wrong_hostname",
                {"host": "mismatch.invalid", "hostaddr": "127.0.0.1"},
                "does not match",
            ),
            ("missing_authority", {"sslrootcert": str(work / "absent.crt")}, "does not exist"),
            ("plaintext", {"sslmode": "disable"}, "no encryption"),
        ):
            try:
                psycopg.connect(**{**base, **changes}).close()
            except psycopg.OperationalError as error:
                assert fragment in str(error), label
                refusals[label] = True
            else:
                raise AssertionError("Invalid TLS connection unexpectedly admitted: " + label)
        principals = {
            "fixture-reviewer": {"tenant": "a", "actor": "reviewer", "role": "reviewer"},
            "fixture-other": {"tenant": "b", "actor": "other", "role": "reviewer"},
        }
        app = create_app(urls["api"], principals)
        stores.append(app.state.store)
        headers = {"Authorization": "Bearer fixture-reviewer", "Idempotency-Key": "tls-job-001"}
        body = json.loads((ROOT / "datasets/demo.json").read_text())
        with TestClient(app) as client:
            submitted = client.post("/api/jobs", json=body, headers=headers)
            assert submitted.status_code == 202 and submitted.json()["status"] == "queued"
            job_id = submitted.json()["id"]
            worker_environment = {
                key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ
            }
            worker_environment.update(
                PYTHONPATH=str(ROOT / "src"),
                ATLAS_DATABASE_URL=urls["worker"],
                ATLAS_BEDROCK_ENABLED="false",
            )
            subprocess.run(
                [sys.executable, "-m", "atlas.worker", "--once"],
                env=worker_environment,
                cwd=ROOT,
                check=True,
                stdout=log,
                stderr=log,
                timeout=45,
            )
            job = client.get("/api/jobs/" + job_id, headers=headers).json()
            assert job["status"] == "succeeded"
            run = client.get("/api/runs/" + job["result_id"], headers=headers).json()
            documents = {
                d["id"]: Document.model_validate(d) for d in [body["rfp"], *body["knowledge"]]
            }
            citations = 0
            for item in run["assessments"]:
                for value in [item["requirement"]["source"], *item["evidence"]]:
                    citation = Citation.model_validate(value)
                    assert citation.matches(documents[citation.document_id])
                    citations += 1
            review_url = (
                f"/api/runs/{run['id']}/reviews/{run['assessments'][0]['requirement']['id']}"
            )
            review = {"version": 1, "decision": "approved", "note": "Fictional TLS fixture review."}
            assert client.post(review_url, json=review, headers=headers).status_code == 200
            assert client.post(review_url, json=review, headers=headers).status_code == 409
            assert client.get(f"/api/runs/{run['id']}/audit", headers=headers).json()
            assert (
                client.get(
                    "/api/runs/" + run["id"], headers={"Authorization": "Bearer fixture-other"}
                ).status_code
                == 404
            )
        # Swap only the disposable server leaf; a newly created client must reject expiry.
        (work / "server.crt").write_bytes((work / "expired.crt").read_bytes())
        with psycopg.connect(**base, autocommit=True) as connection:
            connection.execute("SELECT pg_reload_conf()")
        time.sleep(0.5)
        try:
            psycopg.connect(**base).close()
        except psycopg.OperationalError as error:
            assert "certificate verify failed" in str(error)
            refusals["expired_certificate"] = True
        else:
            raise AssertionError("Expired leaf certificate unexpectedly admitted")
        sources = [
            Path(__file__),
            ROOT / "deployment/postgres-runtime-roles.sql",
            *sorted((ROOT / "src/atlas").rglob("*.py")),
        ]
        report = dict(
            recorded_at=datetime.now(UTC).isoformat(),
            scope="Local PostgreSQL TLS transport and restricted ATLAS API/queue/separate baseline worker. In-process HTTP client with synthetic bearer identities; no browser, Cognito, hosted service or recovery acceptance.",
            image_id=image,
            database_version=docker("exec", name, "postgres", "--version"),
            client_libpq_version=psycopg.pq.version(),
            roles=observed,
            refused_connections=refusals,
            workflow={
                "queued_then_separate_worker_completed": True,
                "requirements": len(run["assessments"]),
                "validated_source_spans": citations,
                "review_and_audit": True,
                "stale_review_refused": True,
                "foreign_workspace_refused": True,
                "privilege_refusals": 3,
            },
            isolation="Cached image, dedicated Docker bridge (egress not blocked), loopback port, non-root, read-only root, dropped capabilities, temporary data, no cloud/model credentials.",
            limitations=[
                "Separate fixture from earlier native PostgreSQL 18 restart/restore controls.",
                "No certificate rotation overlap, revocation, cloud certificate distribution or hosted acceptance.",
                "No mutual TLS: service passwords authenticate clients; verify-full authenticates the server.",
                "No paid models or completed benchmark reruns.",
            ],
            files_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources
            },
        )
        publish_report(ROOT / "reports/postgres-tls.json", report)
        print(
            json.dumps(
                {
                    "tls_roles": len(observed),
                    "connection_refusals": len(refusals),
                    "workflow": report["workflow"],
                }
            )
        )
    finally:
        for store in stores:
            store.engine.dispose()
        if engine is not None:
            engine.dispose()
        log.write(docker("logs", name, check=False))
        docker("rm", "--force", name, check=False)
        docker("network", "rm", name, check=False)
        log.close()
        for filename in ("password", "server.key"):
            (work / filename).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
