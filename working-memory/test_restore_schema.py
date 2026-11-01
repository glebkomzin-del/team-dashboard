import tempfile
import unittest
from pathlib import Path

import restore_schema


class RestoreSchemaTests(unittest.TestCase):
    def make_migrations(self, directory: Path):
        files = {
            "20260907132739_working_memory_uncapped_processing.sql": "p_call_index>15",
            restore_schema.BRIDGE_BEFORE: "p_call_index>31",
            restore_schema.BRIDGE_REPLACED: "select 'historical bridge duplicate';",
            restore_schema.BACKUP_REFERENCES: "select 'references';",
            restore_schema.SEQUENTIAL_HYDRATION: "select 'sequential';",
            "20260708192500_move_warm_ping_to_ask_memory.sql": "select 'legacy';",
            "20260919200321_working_memory_original_deletion_ledger.sql": "select 'ledger';",
            "20260919201406_working_memory_original_deletion_purge.sql": "select 'purge';",
            "20260919202831_working_memory_original_deletion_sanitized_receipts.sql": "select 'sanitized';",
            restore_schema.QUESTION_DELETION_EPOCH: "select 'question epoch';",
            restore_schema.DELETION_REIMPORT_STATUS: "select 'reimport status';",
        }
        files.update({name: "select 'tail';" for name in (*restore_schema.RC2_TAIL, *restore_schema.MEMORY_TAIL)})
        files[restore_schema.IMAGE_PLACEHOLDER] = (
            restore_schema.ROOT / 'supabase' / 'migrations' / restore_schema.IMAGE_PLACEHOLDER
        ).read_text()
        for name, body in files.items():
            (directory / name).write_text(body)

    def test_rc2_plan_has_one_checked_bridge_and_orders_deletions(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_migrations(directory)
            paths = restore_schema.migration_paths(directory)
            plan = restore_schema.render_plan(paths)
        self.assertEqual([path.name for path in paths], [
            "20260907132739_working_memory_uncapped_processing.sql",
            restore_schema.BRIDGE_BEFORE,
            restore_schema.DELETION_LEDGER,
            restore_schema.DELETION_PURGE,
            restore_schema.BACKUP_REFERENCES,
            restore_schema.SEQUENTIAL_HYDRATION,
            "20260919202831_working_memory_original_deletion_sanitized_receipts.sql",
            restore_schema.QUESTION_DELETION_EPOCH,
            restore_schema.DELETION_REIMPORT_STATUS,
            *restore_schema.RC2_TAIL,
            *restore_schema.MEMORY_TAIL,
            restore_schema.IMAGE_PLACEHOLDER,
        ])
        self.assertEqual(plan.count("BEGIN restore bridge 15-to-31"), 1)
        self.assertIn("expected wm_reserve_call call limit 15", plan)
        self.assertIn("check (call_index between 0 and 31)", plan)
        self.assertLess(plan.index("select 'ledger'"), plan.index("select 'purge'"))
        self.assertLess(plan.index("select 'purge'"), plan.index("select 'references'"))
        self.assertLess(plan.index("select 'references'"), plan.index("select 'sequential'"))
        self.assertNotIn("select 'legacy'", plan)
        self.assertNotIn("historical bridge duplicate", plan)
        self.assertLess(plan.index("select 'sequential'"), plan.index("select 'sanitized'"))
        self.assertLess(plan.index("select 'sanitized'"), plan.index("select 'question epoch'"))
        self.assertLess(plan.index("select 'tail'"), plan.index("create function public.wm_archive_image_placeholder_job"))

    def test_restore_refuses_missing_queue_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_migrations(directory)
            (directory / restore_schema.IMAGE_PLACEHOLDER).unlink()
            with self.assertRaisesRegex(ValueError, "Required RC2 migration is missing"):
                restore_schema.migration_paths(directory)

    def test_restore_refuses_changed_queue_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_migrations(directory)
            (directory / restore_schema.IMAGE_PLACEHOLDER).write_text("select 'wrong guard';")
            with self.assertRaisesRegex(ValueError, "Required RC2 migration changed"):
                restore_schema.migration_paths(directory)

    def test_plan_refuses_changed_historical_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_migrations(directory)
            (directory / "20260907132739_working_memory_uncapped_processing.sql").write_text("changed")
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                restore_schema.migration_paths(directory)

    def test_workspace_schema_fallback_is_the_workspace_supabase_directory(self):
        self.assertEqual(restore_schema.default_migrations_dir(), restore_schema.ROOT / 'supabase' / 'migrations')


if __name__ == "__main__":
    unittest.main()
