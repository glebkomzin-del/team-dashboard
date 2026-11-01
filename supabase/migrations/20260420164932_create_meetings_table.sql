
create table meetings (
  id uuid primary key default gen_random_uuid(),
  meeting_unique_id text unique not null,
  meeting_title text,
  participants text[],
  duration_seconds integer,
  language_code text,
  transcript_content text,
  meeting_link text,
  created_at timestamptz default now()
);
;
