create or replace function public.claim_next_cv_request(worker_name text)
returns setof public.cv_requests
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  update public.cv_requests r
  set
    status = 'processing',
    worker_locked_at = now(),
    worker_locked_by = worker_name,
    worker_attempts = r.worker_attempts + 1,
    started_at = coalesce(r.started_at, now()),
    updated_at = now()
  where r.id = (
    select id
    from public.cv_requests
    where status in ('submitted', 'revision_requested')
      and (worker_locked_at is null or worker_locked_at < now() - interval '30 minutes')
      and worker_attempts < 3
    order by
      case priority when 'urgent' then 0 when 'high' then 1 else 2 end,
      created_at asc
    for update skip locked
    limit 1
  )
  returning r.*;
end;
$$;
