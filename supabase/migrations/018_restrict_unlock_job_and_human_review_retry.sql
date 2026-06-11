-- Restrict unlock_job privileges and make needs_human_review retryable.

create or replace function public.unlock_job(p_request_id uuid)
returns public.cv_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.cv_requests%rowtype;
  v_from_status text;
  v_now timestamptz := now();
begin
  -- Fetch the request (must be in a retryable terminal/manual-review status)
  select * into v_request
  from public.cv_requests
  where id = p_request_id
    and status in ('failed', 'dead_letter', 'needs_human_review')
  for update;

  if not found then
    raise exception 'Request not found or not in retryable status (failed/dead_letter/needs_human_review)';
  end if;

  v_from_status := v_request.status;

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
    'from_status', v_from_status,
    'worker_attempts_reset_to', 0
  ));

  return v_request;
end;
$$;

revoke all on function public.unlock_job(uuid) from public;
revoke execute on function public.unlock_job(uuid) from anon;
revoke execute on function public.unlock_job(uuid) from authenticated;
grant execute on function public.unlock_job(uuid) to whub_worker;
grant execute on function public.unlock_job(uuid) to service_role;
