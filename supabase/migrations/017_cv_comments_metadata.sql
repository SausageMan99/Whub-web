-- Add a structured metadata column to cv_comments so that user feedback
-- (corrections, layout complaints, fidelity issues) can be categorized
-- without polluting the comment body. This powers the auto-improvement
-- loop: each feedback category becomes a known regression class.
--
-- The metadata column is jsonb and defaults to '{}' so existing rows are
-- unaffected. Allowed keys are enforced at the application layer
-- (see apps/web/app/requests/[id]/actions.ts) rather than at the DB level
-- to keep the constraint easy to evolve.
alter table public.cv_comments
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists cv_comments_metadata_gin_idx
  on public.cv_comments using gin (metadata);
