"""Build and apply the reviewed RC2 schema restore plan.

This is deliberately separate from Supabase's migration history: the old
15-to-31 call-slot hotfix was applied live but its migration was not retained.
The generated SQL makes that one historical fact explicit and verifies it
before changing anything.  It is intended only for a new, empty target.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


SOURCE_PATH = Path(__file__).resolve()
# The workspace has two parents above working-memory; the runtime copy lives
# directly in /app and uses its packaged /app/schema first.
ROOT = SOURCE_PATH.parents[2] if len(SOURCE_PATH.parents) > 2 else SOURCE_PATH.parent


def default_migrations_dir() -> Path:
    """Prefer the schema copied into a backup/runtime package."""
    for candidate in (Path("/app/schema"), Path(__file__).resolve().parent / "schema",
                      ROOT / "supabase" / "migrations"):
        if candidate.is_dir():
            return candidate
    return Path("/app/schema")
# Some installed schema folders retain this historical file. The checked
# operational bridge below replaces it; never run both.
BRIDGE_REPLACED = "20260908113112_extend_working_memory_model_call_slots.sql"
BRIDGE_BEFORE = "20260908163023_working_memory_hybrid_search.sql"
BACKUP_REFERENCES = "20260919214500_backup_completed_call_references.sql"
# This migration has a CLI-generated filename earlier than BACKUP_REFERENCES,
# but replaces a function patched by it.  It is deliberately appended below.
SEQUENTIAL_HYDRATION = "20260919202704_backup_page_sequential_hydration.sql"
DELETION_LEDGER = "20260919200321_working_memory_original_deletion_ledger.sql"
DELETION_PURGE = "20260919201406_working_memory_original_deletion_purge.sql"
DELETION_SANITIZED_RECEIPTS = "20260919202831_working_memory_original_deletion_sanitized_receipts.sql"
QUESTION_DELETION_EPOCH = "20260919214722_question_deletion_epoch_guard.sql"
DELETION_REIMPORT_STATUS = "20260919215634_source_deletion_reimport_status.sql"
PIPELINE_CUTOVER = "20260919220146_working_memory_pipeline_cutover_audit.sql"
QUESTION_BACKUP_REFERENCES = "20260919220805_backup_completed_question_call_references.sql"
RECOVERY_COSTS = "20260919220820_working_memory_generation_recovery_costs.sql"
ACTIVE_ARCHIVE_ENVELOPE = "20260919222422_archive_active_envelope_after_redaction.sql"
DELETED_DRIVE_MANIFEST = "20260919231025_block_deleted_drive_sources_in_manifest.sql"
ARCHIVE_ONLY_DELETION = "20260919230755_archive_only_source_deletion.sql"
RC2_TAIL = (PIPELINE_CUTOVER, QUESTION_BACKUP_REFERENCES, RECOVERY_COSTS, ACTIVE_ARCHIVE_ENVELOPE, DELETED_DRIVE_MANIFEST, ARCHIVE_ONLY_DELETION)
MEMORY_TAIL = ("20260920160000_pipeline_recovery_diagnostics.sql", "20260920161000_memory_conversations.sql", "20260920162000_memory_conversation_backup.sql", "20260920163000_call_replay_reservation.sql", "20260920164000_job_detail_request_hash.sql", "20260920165000_working_memory_search_work_candidates.sql", "20260920166000_working_memory_search_lexical_candidates.sql", "20260920174816_working_memory_search_vector_index_scan.sql", "20260920202135_working_memory_search_timeout.sql", "20260920210540_working_memory_search_put_timeout.sql")
IMAGE_PLACEHOLDER = "20261005133858_archive_verified_image_placeholder_job.sql"
IMAGE_PLACEHOLDER_SHA256 = "22ac14542d1f2ec8a025e831b5f8c7f4fb23de7ea1dbf3a19a726e6ed99a5f5d"
RC2_DELETIONS = (DELETION_LEDGER, DELETION_PURGE, DELETION_SANITIZED_RECEIPTS, QUESTION_DELETION_EPOCH, DELETION_REIMPORT_STATUS)


BRIDGE_SQL = """-- Operational restore bridge, not a historical migration.
-- The old live hotfix widened wm_reserve_call from 15 to 31 before the
-- following migration widened it from 31 to 1023.  Refuse any other source.
do $$
declare definition text;
begin
  select pg_get_functiondef('public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure)
    into definition;
  if definition is null
     or (definition not like '%p_call_index>15%' and definition not like '%p_call_index > 15%') then
    raise exception 'Restore bridge expected wm_reserve_call call limit 15';
  end if;

  alter table public.wm_model_calls drop constraint wm_model_calls_call_index_check;
  alter table public.wm_model_calls add constraint wm_model_calls_call_index_check
    check (call_index between 0 and 31);
  execute replace(replace(definition, 'p_call_index>15', 'p_call_index>31'),
                  'p_call_index > 15', 'p_call_index > 31');

  select pg_get_functiondef('public.wm_reserve_call(uuid,text,uuid,integer,text,bigint)'::regprocedure)
    into definition;
  if definition not like '%p_call_index>31%' and definition not like '%p_call_index > 31%' then
    raise exception 'Restore bridge did not install wm_reserve_call call limit 31';
  end if;
end $$;
"""


def migration_paths(directory: Path) -> list[Path]:
    """Return the reviewed RC2 set and the required current queue guard."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError(f"Migration directory is unavailable: {directory}")
    paths = []
    for path in sorted(directory.glob("202609*.sql")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Migration must be a regular file: {path.name}")
        if path.name <= BACKUP_REFERENCES and path.name != BRIDGE_REPLACED:
            paths.append(path)
    sequential = directory / SEQUENTIAL_HYDRATION
    if sequential.is_symlink() or not sequential.is_file():
        raise ValueError(f"Required RC2 migration is missing: {SEQUENTIAL_HYDRATION}")
    paths = [path for path in paths if path.name != SEQUENTIAL_HYDRATION]
    paths.append(sequential)
    sanitized = directory / DELETION_SANITIZED_RECEIPTS
    if sanitized.is_symlink() or not sanitized.is_file():
        raise ValueError(f"Required RC2 migration is missing: {DELETION_SANITIZED_RECEIPTS}")
    paths = [path for path in paths if path.name != DELETION_SANITIZED_RECEIPTS]
    paths.append(sanitized)
    epoch = directory / QUESTION_DELETION_EPOCH
    if epoch.is_symlink() or not epoch.is_file():
        raise ValueError(f"Required RC2 migration is missing: {QUESTION_DELETION_EPOCH}")
    paths = [path for path in paths if path.name != QUESTION_DELETION_EPOCH]
    paths.append(epoch)
    reimport_status = directory / DELETION_REIMPORT_STATUS
    if reimport_status.is_symlink() or not reimport_status.is_file():
        raise ValueError(f"Required RC2 migration is missing: {DELETION_REIMPORT_STATUS}")
    paths.append(reimport_status)
    for name in (*RC2_TAIL, *MEMORY_TAIL, IMAGE_PLACEHOLDER):
        tail = directory / name
        if tail.is_symlink() or not tail.is_file():
            raise ValueError(f"Required RC2 migration is missing: {name}")
        if name == IMAGE_PLACEHOLDER and hashlib.sha256(tail.read_bytes()).hexdigest() != IMAGE_PLACEHOLDER_SHA256:
            raise ValueError(f"Required RC2 migration changed: {name}")
        paths.append(tail)
    names = {path.name for path in paths}
    for required in (BRIDGE_BEFORE, BACKUP_REFERENCES, SEQUENTIAL_HYDRATION, *RC2_DELETIONS):
        if required not in names:
            raise ValueError(f"Required RC2 migration is missing: {required}")
    order=[path.name for path in paths]
    if not (order.index(DELETION_LEDGER)<order.index(DELETION_PURGE)<order.index(BACKUP_REFERENCES)
            <order.index(SEQUENTIAL_HYDRATION)<order.index(DELETION_SANITIZED_RECEIPTS)<order.index(QUESTION_DELETION_EPOCH)<order.index(DELETION_REIMPORT_STATUS)):
        raise AssertionError("RC2 deletion and backup migration dependency order changed")
    source = (directory / "20260907132739_working_memory_uncapped_processing.sql").read_text()
    target = (directory / BRIDGE_BEFORE).read_text()
    if "p_call_index>15" not in source or "p_call_index>31" not in target:
        raise ValueError("The historical 15-to-31 restore bridge no longer matches its migrations")
    return paths


def render_plan(paths: list[Path]) -> str:
    # Older migrations use the unqualified vector type; Supabase installs it
    # in extensions, so retain the project's normal restore search path.
    parts = ["\\set ON_ERROR_STOP on\n", "set search_path = public, extensions;\n", "-- Generated by working-memory/restore_schema.py.\n"]
    for path in paths:
        if path.name == BRIDGE_BEFORE:
            parts.extend(["\n-- BEGIN restore bridge 15-to-31\n", BRIDGE_SQL, "-- END restore bridge 15-to-31\n"])
        parts.extend([f"\n-- BEGIN migration {path.name}\n", path.read_text(), "\n-- END migration\n"])
    return "".join(parts)


def target_is_empty(database_url: str) -> None:
    query = "select count(*) from pg_tables where schemaname='public'"
    result = subprocess.run(
        ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--dbname", database_url, "--command", query],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("Could not inspect the target database; no restore was run")
    if result.stdout.strip() != "0":
        raise RuntimeError("Target public schema is not empty; refusing restore")


def apply_plan(plan: str, database_url: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8", delete=False) as stream:
        stream.write(plan)
        temporary = stream.name
    try:
        result = subprocess.run(
            ["psql", "--no-psqlrc", "--set", "ON_ERROR_STOP=1", "--dbname", database_url, "--file", temporary],
            check=False,
        )
        if result.returncode:
            raise RuntimeError("RC2 schema restore failed; inspect psql output and discard this empty target")
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or apply the empty-target RC2 restore plan")
    parser.add_argument("--migrations-dir", type=Path, default=default_migrations_dir())
    parser.add_argument("--output", type=Path, help="write the reviewable operational SQL plan")
    parser.add_argument("--database-url", help="empty target only; never printed")
    parser.add_argument("--apply", action="store_true", help="apply the generated plan after the empty-target check")
    args = parser.parse_args(argv)
    if args.apply and not args.database_url:
        parser.error("--apply requires --database-url")
    paths = migration_paths(args.migrations_dir)
    plan = render_plan(paths)
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"Refusing to overwrite plan: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(plan, encoding="utf-8")
    if args.apply:
        target_is_empty(args.database_url)
        apply_plan(plan, args.database_url)
    print(f"RC2 restore plan: {len(paths)} migrations, bridge before {BRIDGE_BEFORE}; includes {len(RC2_DELETIONS)} reviewed deletion migrations.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, FileExistsError) as error:
        print(f"restore_schema: {error}", file=sys.stderr)
        raise SystemExit(1)
