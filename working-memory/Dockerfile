FROM python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
WORKDIR /app
COPY openai_provider.py memory.py processor.py server.py review_api.py access.py archive_index.py context_window.py corrections.py verify_actions.py reconcile.py temporal_guard.py call_budget.py service_worker.py human_decisions.py journal_store.py journal_projection.py ./
COPY journal_service.py matter_links.py job_recovery.py generation_review.py generation_service.py source_edit.py ./
COPY gateway_journal.py planner.py ./
COPY hybrid_pipeline.py hybrid_schema.py hybrid_index.py ./
COPY canonical_archive.py canonical_worker.py durable_calls.py future_summary.py meeting_naming.py meeting_title_backfill.py archive_drive.py drive_intake.py drive_completion.py ./
COPY compact_reconcile.py retrieval_context.py ./
COPY evaluation/prompt-v2.txt evaluation/schema-v2.json evaluation/prompt-v3.txt evaluation/schema-v3.json evaluation/prompt-v4.txt evaluation/schema-v4.json evaluation/prompt-v5.txt evaluation/schema-v5.json ./evaluation/
COPY evaluation/work-gate-prompt.txt evaluation/source-corrections.json ./evaluation/
COPY evaluation/prompt-v6.txt evaluation/schema-v6.json evaluation/prompt-v7.txt evaluation/schema-v7.json evaluation/prompt-v8.txt evaluation/schema-v8.json evaluation/prompt-v9.txt evaluation/schema-v9.json ./evaluation/
COPY evaluation/work-gate-prompt-v6.txt evaluation/work-gate-schema-v6.json evaluation/work-gate-prompt-v7.txt evaluation/work-gate-schema-v7.json evaluation/work-gate-prompt-v8.txt evaluation/work-gate-schema-v8.json evaluation/work-gate-prompt-v9.txt evaluation/work-gate-schema-v9.json ./evaluation/
RUN mkdir -p /app/.local && chown -R 10001:10001 /app
USER 10001:10001
ENV MEMORY_BIND=0.0.0.0 MEMORY_DB=/app/.local/service.sqlite PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "server.py"]
