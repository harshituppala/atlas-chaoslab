import json
import os
import secrets
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .documents import DocumentStore
from .domain import Document, ResourceBudgetExceeded, StrictModel
from .execution import PIPELINE_VERSION, execute, fingerprint
from .http_privacy import ResponsePrivacy
from .ingestion import (
    MAX_FILE_BYTES,
    ExtractionFailed,
    UnsupportedDocument,
    document_id,
    extract_isolated,
)
from .jobs import JobQueue
from .limits import BodyLimit
from .migrations import HEAD, SchemaNotReady, revision
from .models.intelligence import MODEL_PIPELINE_VERSION
from .models.job_spec import load_job_spec
from .observability import RequestTracing, configure
from .security.browser import BrowserLogin
from .security.memberships import MembershipRegistry
from .security.tokens import (
    AccessTokenVerifier,
    InvalidAccessToken,
    KeyServiceUnavailable,
    TokenTrust,
)
from .store import Conflict, NotFound, Store


@dataclass(frozen=True)
class Identity:
    tenant: str
    actor: str
    role: str


class AnalyzeRequest(StrictModel):
    rfp: Document
    knowledge: list[Document] = Field(min_length=1, max_length=30)


class JobRequest(AnalyzeRequest):
    execution_mode: Literal["baseline", "bedrock"] = "baseline"
    expected_model_config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ReviewRequest(StrictModel):
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=2000)


def create_app(
    database_url=None,
    principals=None,
    token_verifier=None,
    *,
    readiness_probe=None,
    login_exchange=None,
):
    configure("atlas-api")
    owns_verifier = False
    browser_login = None

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if browser_login is not None:
                browser_login.close()
            if owns_verifier:
                token_verifier.close()

    app = FastAPI(
        title="ATLAS Evidence API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    store = Store(
        database_url or os.getenv("ATLAS_DATABASE_URL", "sqlite:///var/atlas.db"), purpose="api"
    )
    queue = JobQueue(store)
    model_spec_path = os.getenv("ATLAS_MODEL_JOB_SPEC")
    model_spec = load_job_spec(model_spec_path) if model_spec_path else None
    documents = DocumentStore(store)
    memberships = MembershipRegistry(store)
    trust_config = os.getenv("ATLAS_TOKEN_TRUST")
    if token_verifier is None and trust_config:
        if len(trust_config) > 8192:
            raise ValueError("Token trust configuration exceeds budget")
        token_verifier = AccessTokenVerifier(TokenTrust(**json.loads(trust_config)))
        owns_verifier = True
    if login_exchange is not None:
        if token_verifier is None:
            token_verifier = login_exchange.verifier
        if token_verifier.trust != login_exchange.config.trust:
            raise ValueError("Browser login and API token trust must match")
        browser_login = BrowserLogin(login_exchange)
    ingestion_slots = threading.BoundedSemaphore(2)
    app.add_middleware(BodyLimit)
    app.add_middleware(RequestTracing)
    app.add_middleware(ResponsePrivacy)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Pydantic errors can include whole source documents, notes, or unknown field values.
        # Even locations and validator messages can contain caller-controlled text.
        return JSONResponse(
            status_code=422, content={"detail": "Request does not match the API schema"}
        )

    configured = (
        principals if principals is not None else json.loads(os.getenv("ATLAS_PRINCIPALS", "{}"))
    )
    security = HTTPBearer(auto_error=False)

    def identity(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
        workspace: Annotated[str | None, Header(alias="X-Workspace-ID", max_length=128)] = None,
    ):
        if browser_login is not None and browser_login.has_session_cookie(request):
            if "authorization" in request.headers:
                raise HTTPException(400, "Choose one authentication method")
            credential = browser_login.credential(request).access_token
        elif credentials:
            credential = credentials.credentials
        else:
            raise HTTPException(
                401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
            )
        if token_verifier is not None:
            try:
                subject = token_verifier.verify(credential)
            except InvalidAccessToken:
                raise HTTPException(
                    401, "Invalid credential", headers={"WWW-Authenticate": "Bearer"}
                ) from None
            except KeyServiceUnavailable:
                raise HTTPException(
                    503, "Identity verification unavailable", headers={"Retry-After": "10"}
                ) from None
            member = memberships.resolve(subject, workspace)
            if member is None:
                raise HTTPException(403, "Authorized workspace selection required")
            return Identity(**member)
        for token, value in configured.items():
            if secrets.compare_digest(credential.encode(), token.encode()):
                if workspace is not None and workspace != value["tenant"]:
                    raise HTTPException(403, "Authorized workspace selection required")
                return Identity(**value)
        raise HTTPException(401, "Invalid credential", headers={"WWW-Authenticate": "Bearer"})

    if browser_login is not None:
        browser_login.attach(app)
    User = Annotated[Identity, Depends(identity)]
    IdempotencyKey = Annotated[str, Header(min_length=8, max_length=128)]

    def translate(fn):
        try:
            return fn()
        except NotFound:
            raise HTTPException(404, "Resource not found") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ResourceBudgetExceeded:
            raise HTTPException(422, "Analysis work budget exceeded") from None

    @app.get("/api/execution-options")
    def execution_options(user: User):
        enabled = os.getenv("ATLAS_ENABLE_BEDROCK_JOBS") == "1" and model_spec is not None
        if not enabled:
            return {"model": {"enabled": False}}
        from .models.benchmark import reservation_plan

        plan = reservation_plan(model_spec.config(), 1)
        return {
            "model": {
                "enabled": True,
                "model_id": model_spec.model_id,
                "region": model_spec.region,
                "model_config_sha256": model_spec.digest(),
                "maximum_reserved_inference_usd": plan["maximum_reserved_inference_usd"],
            }
        }

    @app.get("/api/me")
    def current_identity(user: User):
        return {
            "tenant": user.tenant,
            "actor": user.actor,
            "role": user.role,
            "authentication": "managed-access-token"
            if token_verifier is not None
            else "local-bearer",
        }

    @app.get("/healthz")
    def health():
        return {"status": "ok", "provider": "extractive-baseline", "production_validated": False}

    @app.get("/readyz")
    def ready():
        try:
            with store.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                if revision(connection) != HEAD:
                    raise SchemaNotReady()
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable") from None
        except SchemaNotReady:
            raise HTTPException(503, "Database schema is not ready") from None
        if readiness_probe is not None and not readiness_probe():
            raise HTTPException(503, "Local worker is not ready")
        return {"status": "ready", "schema_revision": HEAD}

    @app.get("/api/runs")
    def list_runs(user: User):
        return store.list(user.tenant)

    @app.get("/api/documents")
    def list_documents(user: User):
        return documents.list(user.tenant)

    @app.get("/api/documents/{document_id}")
    def get_document(document_id: str, user: User):
        return translate(lambda: documents.get(user.tenant, document_id))

    @app.get("/api/documents/{document_id}/original")
    def original_document(document_id: str, user: User):
        raw, document = translate(lambda: documents.original(user.tenant, document_id))
        format = document.source_map.format
        media_type = (
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return Response(
            raw,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{document.id}.{format}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/documents", status_code=201)
    def upload_document(
        request: Request,
        user: User,
        format: Literal["pdf", "docx"],
        kind: Literal["rfp", "knowledge"],
        title: Annotated[str, Query(min_length=1, max_length=200)],
    ):
        # The bounded middleware exposes raw bytes; no multipart parser or disk filenames.
        if user.role not in {"analyst", "reviewer", "admin"}:
            raise HTTPException(403, "Analyst role required")
        raw = request.scope.get("atlas.body", b"")
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise HTTPException(413, "Upload must contain 1 to 1,000,000 bytes")
        try:
            existing = documents.get(user.tenant, document_id(raw, kind))
            if existing.source_map.format != format:
                raise HTTPException(422, "File format differs from its immutable source")
            return existing
        except NotFound:
            pass
        if not ingestion_slots.acquire(blocking=False):
            raise HTTPException(
                429, "Document service is busy. Try again shortly.", headers={"Retry-After": "2"}
            )
        try:
            document = extract_isolated(raw, format, title, kind)
            return documents.save(user.tenant, user.actor, document, raw)
        except UnsupportedDocument as exc:
            raise HTTPException(422, str(exc)) from None
        except ResourceBudgetExceeded:
            raise HTTPException(
                413, "Document extraction or workspace storage budget exceeded"
            ) from None
        except ExtractionFailed:
            raise HTTPException(422, "Document could not be extracted safely") from None
        finally:
            ingestion_slots.release()

    def validate_request(request, user):
        if user.role not in {"analyst", "reviewer", "admin"}:
            raise HTTPException(403, "Analyst role required")
        if request.rfp.kind != "rfp" or any(d.kind != "knowledge" for d in request.knowledge):
            raise HTTPException(422, "Invalid document kinds")
        documents = [request.rfp, *request.knowledge]
        if len({d.id for d in documents}) != len(documents):
            raise HTTPException(422, "Document IDs must be unique")
        if sum(len(d.text) for d in documents) > 300_000:
            raise HTTPException(413, "Document budget exceeded")
        for document in documents:
            translate(lambda document=document: app.state.documents.verify(user.tenant, document))

    @app.post("/api/jobs", status_code=202)
    def submit_job(request: JobRequest, idempotency_key: IdempotencyKey, user: User):
        validate_request(request, user)
        if request.execution_mode == "bedrock" and (
            os.getenv("ATLAS_ENABLE_BEDROCK_JOBS") != "1" or model_spec is None
        ):
            raise HTTPException(503, "Model-backed jobs are not enabled")
        if (
            request.execution_mode == "bedrock"
            and request.expected_model_config_sha256 != model_spec.digest()
        ):
            raise HTTPException(409, "Model settings changed; reconnect before submitting")
        if (
            request.execution_mode == "baseline"
            and request.expected_model_config_sha256 is not None
        ):
            raise HTTPException(422, "Baseline jobs do not accept model settings")
        return translate(
            lambda: queue.submit(
                user.tenant,
                user.actor,
                idempotency_key,
                request.model_dump(exclude={"execution_mode", "expected_model_config_sha256"}),
                pipeline_version=MODEL_PIPELINE_VERSION
                if request.execution_mode == "bedrock"
                else PIPELINE_VERSION,
                model_spec=model_spec.model_dump(mode="json")
                if request.execution_mode == "bedrock"
                else None,
            )
        )

    @app.get("/api/jobs")
    def list_jobs(user: User):
        return queue.list(user.tenant)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, user: User):
        return translate(lambda: queue.get(user.tenant, job_id))

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, user: User):
        if user.role not in {"analyst", "reviewer", "admin"}:
            raise HTTPException(403, "Analyst role required")
        return translate(lambda: queue.cancel(user.tenant, user.actor, job_id))

    @app.get("/api/jobs/{job_id}/audit")
    def job_events(job_id: str, user: User):
        return translate(lambda: queue.events(user.tenant, job_id))

    @app.post("/api/runs")
    def create_run(request: AnalyzeRequest, idempotency_key: IdempotencyKey, user: User):
        # Retained as the synchronous baseline API for comparisons and existing clients.
        validate_request(request, user)
        if idempotency_key.startswith("job:"):
            raise HTTPException(422, "Reserved idempotency namespace")
        body = request.model_dump()
        digest = fingerprint(body)
        existing = store.lookup_key(user.tenant, idempotency_key)
        if existing:
            if existing["fingerprint"] != digest:
                raise HTTPException(409, "Idempotency key reused with different content")
            return store.get(user.tenant, existing["id"])
        return translate(
            lambda: store.save(user.tenant, idempotency_key, digest, execute(body), user.actor)
        )

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, user: User):
        return translate(lambda: store.get(user.tenant, run_id))

    @app.post("/api/runs/{run_id}/reviews/{requirement_id}")
    def review(run_id: str, requirement_id: str, request: ReviewRequest, user: User):
        if user.role not in {"reviewer", "admin"}:
            raise HTTPException(403, "Reviewer role required")
        return translate(
            lambda: store.review(
                user.tenant,
                user.actor,
                run_id,
                requirement_id,
                request.version,
                request.decision,
                request.note,
            )
        )

    @app.get("/api/runs/{run_id}/audit")
    def events(run_id: str, user: User):
        return translate(lambda: store.events(user.tenant, run_id))

    @app.get("/api/demo")
    def demo(user: User):
        return json.loads(
            (Path(__file__).resolve().parents[2] / "datasets" / "demo.json").read_text()
        )

    @app.get("/api/benchmarks")
    def benchmarks(user: User):
        path = Path("reports/baseline.json")
        if not path.exists():
            raise HTTPException(404, "Run CHAOSLAB to generate a report")
        report = json.loads(path.read_text())
        recovery = Path("reports/recovery.json")
        if recovery.exists():
            report["recovery"] = json.loads(recovery.read_text())
        retrieval = Path("reports/retrieval.json")
        if retrieval.exists():
            report["retrieval"] = json.loads(retrieval.read_text())
        ingestion = Path("reports/ingestion.json")
        if ingestion.exists():
            report["ingestion"] = json.loads(ingestion.read_text())
        postgres = Path("reports/postgres.json")
        if postgres.exists():
            report["postgres"] = json.loads(postgres.read_text())
        persistent = Path("reports/persistent-retrieval.json")
        if persistent.exists():
            report["persistent_retrieval"] = json.loads(persistent.read_text())
        adversarial = Path("reports/adversarial.json")
        if adversarial.exists():
            report["adversarial"] = json.loads(adversarial.read_text())
        reasoning = Path("reports/reasoning.json")
        if reasoning.exists():
            report["reasoning"] = json.loads(reasoning.read_text())
        # Explicit public report allowlist: never discover private provider artifacts.
        report["live_reasoning"] = [
            json.loads(path.read_text())
            for filename in (
                "reasoning-live-v2.json",
                "reasoning-live-v3.json",
                "reasoning-live-v4.json",
                "reasoning-transfer-live-v4.json",
            )
            if (path := Path("reports") / filename).exists()
        ]
        for key, filename in (
            ("scenario_baseline", "scenarios-baseline.json"),
            ("scenario_live", "scenarios-live-v4.json"),
        ):
            path = Path("reports") / filename
            if path.exists():
                report[key] = json.loads(path.read_text())
        return report

    frontend = Path("apps/web/dist")
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="web")
    app.state.browser_login = browser_login
    app.state.store = store
    app.state.queue = queue
    app.state.documents = documents
    app.state.ingestion_slots = ingestion_slots
    app.state.memberships = memberships
    return app
