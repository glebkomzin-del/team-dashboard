ALTER TABLE public.todos
  DROP CONSTRAINT todos_project_id_fkey,
  ADD CONSTRAINT todos_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;

ALTER TABLE public.blockers
  DROP CONSTRAINT blockers_project_id_fkey,
  ADD CONSTRAINT blockers_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;

ALTER TABLE public.open_items
  DROP CONSTRAINT open_items_project_id_fkey,
  ADD CONSTRAINT open_items_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;
