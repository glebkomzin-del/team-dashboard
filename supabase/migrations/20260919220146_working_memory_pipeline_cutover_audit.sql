-- A pipeline cutover for untouched queued jobs is an operational decision in
-- its own right. Do not mislabel it as retry/archive/rebase in the audit log.
alter table public.wm_job_decisions
  drop constraint wm_job_decisions_action_check;
alter table public.wm_job_decisions
  add constraint wm_job_decisions_action_check check(action in (
    'retry','archive_only','rebase_prepared','apply_generation','pipeline_cutover'
  ));
