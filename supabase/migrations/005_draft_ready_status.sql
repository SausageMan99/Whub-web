alter table public.cv_requests
  drop constraint if exists cv_requests_status_check;

alter table public.cv_requests
  add constraint cv_requests_status_check
  check (status in (
    'submitted',
    'processing',
    'qa_failed',
    'ready',
    'draft_ready',
    'revision_requested',
    'failed',
    'cancelled',
    'archived'
  ));

alter table public.cv_versions
  drop constraint if exists cv_versions_qa_status_check;

alter table public.cv_versions
  add constraint cv_versions_qa_status_check
  check (qa_status in ('pending', 'passed', 'draft', 'failed'));
