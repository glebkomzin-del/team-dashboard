FROM dashboard-memory:queue-placeholder-20261005-b3e22868
USER root
COPY --chown=10001:10001 hybrid_pipeline.py processor.py future_summary.py canonical_worker.py canonical_archive.py journal_service.py hybrid_index.py build-manifest.json /app/
COPY --chown=10001:10001 evaluation/endstate-gate-schema-v1.json evaluation/endstate-gate-prompt-v1.txt /app/evaluation/
USER 10001:10001
