FROM dashboard-memory:archive-generation-reason-overlay-20261005-2bfdad83-v2
USER root
COPY --chown=10001:10001 journal_projection.py generation_review.py build-manifest.json /app/
USER 10001:10001
