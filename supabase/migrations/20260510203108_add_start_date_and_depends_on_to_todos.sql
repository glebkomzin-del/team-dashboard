
ALTER TABLE public.todos ADD COLUMN IF NOT EXISTS start_date date;
ALTER TABLE public.todos ADD COLUMN IF NOT EXISTS depends_on uuid[] DEFAULT '{}';
;
