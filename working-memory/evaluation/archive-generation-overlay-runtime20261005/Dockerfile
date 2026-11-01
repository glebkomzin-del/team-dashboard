FROM dashboard-memory:queue-placeholder-20261005-b3e22868
USER root
COPY --chown=10001:10001 canonical_archive.py journal_service.py hybrid_index.py build-manifest.json /app/
USER 10001:10001
