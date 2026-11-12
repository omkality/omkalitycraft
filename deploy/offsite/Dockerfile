# Transport acceptance tools only; this does not install a host backup job.
FROM python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925
COPY restic rest-server /usr/local/bin/
RUN chmod 0555 /usr/local/bin/restic /usr/local/bin/rest-server
ENTRYPOINT ["python"]
