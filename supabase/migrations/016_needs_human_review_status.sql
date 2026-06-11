-- Add needs_human_review status to cv_requests.
--
-- This status is set by the worker when the source profile classifier
-- decides the CV is too uncertain to auto-generate (very short text,
-- scanned/empty extraction, no inferable first name and no signal).
-- No PDF is produced. The web cockpit surfaces it as a clear "validate
-- before retry" status. It is retryable the same way draft_ready is:
-- via the existing comment/revision path or after the user adds a
-- clarifying instruction.
alter table public.cv_requests
  drop constraint if exists cv_requests_status_check;

alter table public.cv_requests
  add constraint cv_requests_status_check
  check (status in (
    'submitted',
    'processing',
    'qa_failed',
    'draft_ready',
    'ready',
    'revision_requested',
    'failed',
    'dead_letter',
    'cancelled',
    'archived',
    'needs_human_review'
  ));
