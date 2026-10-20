FROM node:24-bookworm-slim AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home atlas
COPY src/ src/
COPY datasets/ datasets/
COPY reports/ reports/
COPY deployment/postgres-runtime-roles.sql deployment/postgres-runtime-roles.sql
COPY --from=frontend /build/dist apps/web/dist/
RUN mkdir -p var && chown atlas:atlas var
USER 10001
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "atlas.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
