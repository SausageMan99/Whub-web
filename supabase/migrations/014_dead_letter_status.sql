-- Add dead_letter status to cv_requests
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
    'archived'
  ));

-- Update the claim_next_cv_request RPC to also consider dead_letter as retryable
-- (optional: dead_letter jobs can be retried via unlock_job RPC instead)
-- The unlock_job RPC handles the reset, so we don't include dead_letter here.

-- RPC: unlock_job - reset a failed/dead_letter request to submitted for retry
create or replace function public.unlock_job(p_request_id uuid)
returns public.cv_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.cv_requests%rowtype;
  v_now timestamptz := now();
begin
  -- Fetch the request (must be in failed or dead_letter status)
  select * into v_request
  from public.cv_requests
  where id = p_request_id
    and status in ('failed', 'dead_letter')
  for update;

  if not found then
    raise exception 'Request not found or not in retryable status (failed/dead_letter)';
  end if;

  -- Reset to submitted with worker_attempts = 0
  update public.cv_requests
  set
    status = 'submitted',
    worker_attempts = 0,
    last_error = null,
    worker_locked_at = null,
    worker_locked_by = null,
    started_at = null,
    submitted_at = v_now,
    updated_at = v_now
  where id = p_request_id
  returning *
  into v_request;

  -- Log the unlock event
  insert into public.cv_events (request_id, event_type, actor_type, payload)
  values (p_request_id, 'unlocked', 'system', jsonb_build_object(
    'from_status', 'failed',
    'worker_attempts_reset_to', 0
  ));

  return v_request;
end;
$$;

grant execute on function public.unlock_job(uuid) to whub_worker;
grant execute on function public.unlock_job(uuid) to anon, authenticated;