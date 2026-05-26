create extension if not exists "pgcrypto";

create table public.allowed_users (
  email text primary key,
  role text not null default 'member' check (role in ('member', 'admin')),
  created_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  full_name text,
  role text not null default 'member' check (role in ('member', 'admin')),
  created_at timestamptz not null default now()
);

create table public.cv_requests (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references public.profiles(id),
  title text,
  candidate_first_name text,
  candidate_internal_label text,
  source_file_path text not null,
  source_file_name text not null,
  source_file_mime text,
  source_file_size bigint,
  instructions text,
  priority text not null default 'normal' check (priority in ('normal', 'high', 'urgent')),
  status text not null default 'submitted' check (status in ('submitted','processing','qa_failed','ready','revision_requested','failed','cancelled','archived')),
  current_version_id uuid,
  worker_locked_at timestamptz,
  worker_locked_by text,
  worker_attempts int not null default 0,
  last_error text,
  submitted_at timestamptz not null default now(),
  started_at timestamptz,
  ready_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.cv_versions (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.cv_requests(id) on delete cascade,
  version_number int not null,
  structured_json jsonb,
  renderer_input_path text,
  final_pdf_path text,
  qa_status text not null default 'pending' check (qa_status in ('pending','passed','failed')),
  qa_report jsonb,
  generated_by text not null default 'worker',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(request_id, version_number)
);

alter table public.cv_requests
  add constraint cv_requests_current_version_fk
  foreign key (current_version_id) references public.cv_versions(id) on delete set null;

create table public.cv_comments (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.cv_requests(id) on delete cascade,
  version_id uuid references public.cv_versions(id) on delete set null,
  author_id uuid not null references public.profiles(id),
  body text not null,
  comment_type text not null default 'general' check (comment_type in ('general','revision','qa','internal')),
  resolved boolean not null default false,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table public.cv_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.cv_requests(id) on delete cascade,
  actor_id uuid references public.profiles(id),
  actor_type text not null default 'user' check (actor_type in ('user','worker','system')),
  event_type text not null,
  payload jsonb,
  created_at timestamptz not null default now()
);

create index cv_requests_status_created_idx on public.cv_requests(status, created_at);
create index cv_requests_created_by_idx on public.cv_requests(created_by);
create index cv_versions_request_idx on public.cv_versions(request_id, version_number desc);
create index cv_comments_request_idx on public.cv_comments(request_id, created_at);
create index cv_events_request_idx on public.cv_events(request_id, created_at desc);
