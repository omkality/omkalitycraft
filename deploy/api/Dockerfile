FROM ghcr.io/astral-sh/uv:0.11.12@sha256:3a59a3cdd5f7c217faa36e32dbc7fddbb0412889c2a0a5229f6d790e5a019dd7 AS uv
FROM python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925
WORKDIR /backend
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-cache --no-install-project --no-default-groups --group shared --group api
COPY api/ api/
COPY omk/__init__.py omk/
COPY omk/accounts/__init__.py omk/accounts/drasl.py omk/accounts/
COPY omk/game/__init__.py omk/game/minecraft_status.py omk/game/
COPY omk/observability/__init__.py omk/observability/diagnostics.py omk/observability/incidents.py omk/observability/report_store.py omk/observability/
COPY omk/shared/__init__.py omk/shared/content_policy.py omk/shared/fs.py omk/shared/
CMD [".venv/bin/python", "-m", "api"]
