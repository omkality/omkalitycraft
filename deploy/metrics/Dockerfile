FROM python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY omk/__init__.py omk/resource_metrics.py omk/resource_store.py omk/resource_history.py omk/game_metrics.py ./omk/
RUN mkdir /history && chown 10001:10001 /history && chmod 700 /history
USER 10001:10001
ENTRYPOINT ["python", "-m", "omk.resource_history"]
