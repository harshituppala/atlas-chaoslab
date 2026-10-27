FROM node:24-bookworm-slim AS frontend
WORKDIR /build/apps/web
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
COPY reports/scenarios-baseline.json reports/scenarios-live-v4.json reports/reasoning-transfer-baseline.json reports/reasoning-transfer-live-v4.json reports/contract-model-test.json reports/contract-model-test-standalone-replay.json /build/reports/
COPY datasets/reasoning-transfer.json /build/datasets/
RUN pnpm build

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home atlas
COPY src/ src/
COPY datasets/ datasets/
COPY reports/ reports/
COPY deployment/postgres-runtime-roles.sql deployment/postgres-runtime-roles.sql
COPY --from=frontend /build/apps/web/dist apps/web/dist/
RUN mkdir -p var && chown atlas:atlas var
USER 10001
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "atlas.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# Explicit opt-in private workbench. Default builds below keep the bearer profile.
FROM runtime AS managed
COPY scripts/run_managed_workbench.py scripts/run_managed_worker.py scripts/
CMD ["python", "scripts/run_managed_workbench.py", "--settings", "/run/atlas/runtime.json"]

FROM runtime AS default
