-- Auth désactivé — plus de created_by obligatoire
alter table public.cv_requests
  alter column created_by drop not null;

alter table public.cv_comments
  alter column author_id drop not null;

alter table public.cv_events
  alter column actor_id drop not null;
