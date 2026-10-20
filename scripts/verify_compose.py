"""Disposable local Compose proof. Creates synthetic data; always removes its own stack.

No AWS credentials, model calls, public binding, or cloud provisioning. Secret files
are readable inside containers but protected on the host by a private 0700 directory.
Docker administrators remain trusted. Do not point this harness at real client data.
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from atlas.domain import Citation, Document


def snapshot():
    paths = list(Path("src").rglob("*.py")) + [
        Path(p)
        for p in (
            "Dockerfile",
            "compose.yaml",
            "requirements.lock",
            "pyproject.toml",
            "deployment/postgres-runtime-roles.sql",
            "scripts/verify_compose.py",
            "datasets/demo.json",
            "datasets/documents/municipal-rfp.pdf",
            "scripts/restore_exercise.py",
            "scripts/backup_fixture.py",
        )
    ]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    parser.add_argument(
        "--backup-restore",
        action="store_true",
        help="Delete this disposable stack volume and recover from a logical archive",
    )
    args = parser.parse_args()
    root = Path.cwd().resolve()
    project = "atlascheck" + uuid4().hex[:12]
    private = root / "var/compose-validation" / project
    private.mkdir(parents=True, mode=0o700)
    passwords = {name: secrets.token_urlsafe(36) for name in ("owner", "api", "worker")}
    tokens = {name: secrets.token_urlsafe(36) for name in ("analyst", "one", "two", "foreign")}
    principals = {
        tokens[name]: {
            "tenant": "b" if name == "foreign" else "a",
            "actor": name,
            "role": "analyst" if name == "analyst" else "reviewer",
        }
        for name in tokens
    }
    artifacts = {
        "owner_password": passwords["owner"],
        "operator.json": json.dumps(
            {name + "_password": value for name, value in passwords.items()}
        ),
        "api.json": json.dumps({"password": passwords["api"], "principals": principals}),
        "worker.json": json.dumps({"password": passwords["worker"]}),
    }
    for name, value in artifacts.items():
        path = private / name
        path.write_text(value)
        path.chmod(
            0o644
        )  # Ancestor is 0700; nonroot container UID must read the bind-mounted file.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        local_port = probe.getsockname()[1]
    env = {
        **os.environ,
        "ATLAS_LOCAL_SECRETS": str(private),
        "ATLAS_LOCAL_PORT": str(local_port),
        "ATLAS_LOCAL_IMAGE": "atlas-local:" + project,
    }
    started, frozen = datetime.now(UTC).isoformat(), snapshot()
    log = (private / "execution.log").open("w")

    def compose(*command, capture=False):
        return subprocess.run(
            [args.docker, "compose", "-f", "compose.yaml", "-p", project, *command],
            env=env,
            check=True,
            timeout=900,
            text=True,
            stdout=subprocess.PIPE if capture else log,
            stderr=log,
        ).stdout

    def execute(service, code):
        return json.loads(compose("exec", "-T", service, "python", "-c", code, capture=True))

    try:
        compose("build", "api")
        compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120")
        port = compose("port", "api", "8000", capture=True).strip().split(":")[-1]
        base = "http://127.0.0.1:" + port

        def request(path, actor="one", data=None, *, key="compose-workflow-001"):
            req = urllib.request.Request(
                base + path,
                data=None if data is None else json.dumps(data).encode(),
                headers={
                    "Authorization": "Bearer " + tokens[actor],
                    "Idempotency-Key": key,
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, None

        body = json.loads(Path("datasets/demo.json").read_text())
        docs = {d["id"]: Document.model_validate(d) for d in [body["rfp"], *body["knowledge"]]}
        assert request("/readyz")[0] == 200
        # Verify actual non-owner identities, row-policy enforcement and denied grants.
        role_code = (
            "import json; from sqlalchemy import text; from atlas.local_stack import load_secret, "
            "database_url; from atlas.store import Store; "
            "service='{service}'; settings=load_secret(service); "
            "store=Store(database_url('atlas_'+service,settings['password']).render_as_string("
            "hide_password=False),purpose=service); "
            "conn=store.engine.connect(); "
            'print(json.dumps(dict(conn.execute(text("SELECT current_user AS role, '
            "rolsuper AS superuser, rolbypassrls AS bypass FROM pg_roles "
            'WHERE rolname=current_user")).mappings().one())))'
        )
        api_role = execute("api", role_code.replace("{service}", "api"))
        worker_role = execute("worker", role_code.replace("{service}", "worker"))
        assert api_role == {"role": "atlas_api", "superuser": False, "bypass": False}
        assert worker_role == {"role": "atlas_worker", "superuser": False, "bypass": True}
        assert request("/api/jobs", "analyst", {**body, "execution_mode": "bedrock"})[0] == 503
        compose("stop", "worker")
        code, job = request("/api/jobs", "analyst", body)
        assert code == 202 and job["status"] == "queued"
        assert request("/api/jobs", "analyst", body)[1]["id"] == job["id"]
        assert request("/api/jobs/" + job["id"], "foreign")[0] == 404
        # Recreate the API container (not merely an in-process restart); DB volume persists.
        compose("up", "-d", "--no-build", "--no-deps", "--force-recreate", "--wait", "api")
        port = compose("port", "api", "8000", capture=True).strip().split(":")[-1]
        base = "http://127.0.0.1:" + port
        assert request("/api/jobs/" + job["id"])[1]["status"] == "queued"
        compose("start", "worker")
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            completed = request("/api/jobs/" + job["id"])[1]
            if completed["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.1)
        assert completed["status"] == "succeeded"
        code, run = request("/api/runs/" + completed["result_id"])
        assert code == 200
        citations = 0
        for item in run["assessments"]:
            for value in [item["requirement"]["source"], *item["evidence"]]:
                citation = Citation.model_validate(value)
                assert citation.matches(docs[citation.document_id])
                citations += 1
        item = next(a for a in run["assessments"] if a["status"] == "evidence_found")
        review_path = f"/api/runs/{run['id']}/reviews/{item['requirement']['id']}"
        decision = {"version": 1, "decision": "approved", "note": "Synthetic container review."}
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(
                pool.map(lambda actor: request(review_path, actor, decision)[0], ["one", "two"])
            )
        assert sorted(statuses) == [200, 409]
        # Unfiltered SQL through the actual API role returns no rows without trusted tenant context.
        no_context = execute(
            "api",
            (
                "import json; from sqlalchemy import text,create_engine; "
                "from atlas.local_stack import load_secret,database_url; "
                "engine=create_engine(database_url('atlas_api',load_secret('api')['password'])); "
                "conn=engine.connect(); print(json.dumps(conn.execute(text("
                "'SELECT count(*) FROM runs')).scalar_one()))"
            ),
        )
        assert no_context == 0
        # Full stack down/up preserves PostgreSQL's volume, including review and audit history.
        compose("down")
        compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120")
        port = compose("port", "api", "8000", capture=True).strip().split(":")[-1]
        base = "http://127.0.0.1:" + port
        restored = request("/api/runs/" + run["id"])[1]
        reviewed = next(
            a
            for a in restored["assessments"]
            if a["requirement"]["id"] == item["requirement"]["id"]
        )
        assert reviewed["review_state"] == "approved" and reviewed["version"] == 2
        assert (
            sum(
                e["action"] == "review.approved" for e in request(f"/api/runs/{run['id']}/audit")[1]
            )
            == 1
        )
        assert request("/api/runs/" + run["id"], "foreign")[0] == 404
        recovery = None
        if args.backup_restore:
            from restore_exercise import exercise

            recovery = exercise(compose, private, root, request)
            # Verify the original approved result after logical recovery as well.
            recovered = request("/api/runs/" + run["id"])[1]
            original_review = next(
                a
                for a in recovered["assessments"]
                if a["requirement"]["id"] == item["requirement"]["id"]
            )
            assert original_review["review_state"] == "approved" and original_review["version"] == 2
            assert (
                sum(
                    e["action"] == "review.approved"
                    for e in request(f"/api/runs/{run['id']}/audit")[1]
                )
                == 1
            )
            assert request("/api/runs/" + run["id"], "foreign")[0] == 404
            recovery["approved_review_and_audit_restored"] = True
        database = execute(
            "api",
            (
                "import json; from sqlalchemy import text,create_engine; "
                "from atlas.local_stack import load_secret,database_url; "
                "engine=create_engine(database_url('atlas_api',load_secret('api')['password'])); "
                "conn=engine.connect(); print(json.dumps(dict(conn.execute(text("
                '"SELECT version() AS server_version, (SELECT extversion FROM pg_extension WHERE '
                "extname='vector') AS vector_version, (SELECT version_num FROM alembic_version) AS revision\""
                ")).mappings().one())))"
            ),
        )
        identities = {}
        runtime_configuration = {}
        for service in ("postgres", "api", "worker", "initialize"):
            container = compose("ps", "-a", "-q", service, capture=True).strip()
            info = json.loads(
                subprocess.check_output([args.docker, "inspect", container], text=True)
            )[0]
            identities[service] = info["Image"]
            assert not any(
                secret in json.dumps(info) for secret in [*passwords.values(), *tokens.values()]
            )
            if service in {"api", "worker", "initialize"}:
                assert info["Config"]["User"] == "10001"
                assert "ALL" in info["HostConfig"]["CapDrop"]
                assert "no-new-privileges:true" in info["HostConfig"]["SecurityOpt"]
            if service == "postgres":
                assert not info["HostConfig"]["PortBindings"]
            if service == "api":
                assert all(
                    binding["HostIp"] == "127.0.0.1"
                    for binding in info["HostConfig"]["PortBindings"]["8000/tcp"]
                )
            runtime_configuration[service] = {
                "user": info["Config"]["User"],
                "secret_values_absent_from_inspect": True,
            }
        if snapshot() != frozen:
            raise RuntimeError("Verification inputs changed; public report refused")
        report = {
            "schema_version": 1,
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
            "source_files": frozen,
            "images": identities,
            "database": database,
            "runtime_configuration": runtime_configuration,
            "api_role": api_role,
            "worker_role": worker_role,
            "model_admission_disabled": True,
            "idempotent_queued_job": True,
            "queued_job_survives_api_recreation": True,
            "worker_completed": True,
            "validated_citations": citations,
            "competing_review_statuses": sorted(statuses),
            "unscoped_api_role_rows": no_context,
            "tenant_isolation": True,
            "review_and_audit_survive_stack_recreation": True,
            "repeat_initialization_passed": True,
            "paid_calls": 0,
            "scope": "Actual local Linux ARM64 Compose stack with PostgreSQL/pgvector, explicit "
            "migrations and restricted SCRAM logins, forced row policies, separate HTTP API "
            "and baseline worker. One synthetic workflow, not a load or model-quality study. "
            "Docker administrators are trusted; local secret bind files are not encrypted. "
            "No TLS, live provider, managed identity, remote CI or AWS deployment proof.",
        }
        if recovery is not None:
            report["backup_restore"] = recovery
        output = "reports/backup-restore.json" if args.backup_restore else "reports/compose.json"
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"compose_workflow_passed": True, "validated_citations": citations}))
    finally:
        try:
            compose("logs", "--no-color")
            compose("down", "--volumes", "--remove-orphans")
        finally:
            log.close()


if __name__ == "__main__":
    main()
