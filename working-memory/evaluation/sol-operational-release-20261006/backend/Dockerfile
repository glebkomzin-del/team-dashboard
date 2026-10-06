FROM dashboard-memory:sol-operational-20261006-cd564ee70b
USER root
COPY --chown=10001:10001 openai_provider.py server.py build-manifest.json /app/
USER 10001:10001
