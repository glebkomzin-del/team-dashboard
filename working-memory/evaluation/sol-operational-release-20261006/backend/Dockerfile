FROM dashboard-memory:sol-counter-fix-20261006-9a9a0b1016
USER root
COPY --chown=10001:10001 reconcile.py compact_reconcile.py build-manifest.json /app/
USER 10001:10001
