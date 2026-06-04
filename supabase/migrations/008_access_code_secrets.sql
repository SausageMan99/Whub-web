-- 008_access_code_secrets.sql
-- Replace email-derived access codes with random secrets stored as bcrypt hashes.
-- Idempotent hardening migration: safe to run after 007_access_code_hardening.sql.

-- Ensure pgcrypto helpers are available through the extensions schema used by
-- earlier migrations.
create extension if not exists pgcrypto with schema extensions;

-- Store only bcrypt hashes; plaintext access codes must never be persisted.
alter table public.allowed_users
  add column if not exists access_code_hash text;

-- Generic bcrypt verification RPC used by the web app. Supabase exposes SQL
-- parameters by name, so keep plain_text/password_hash in sync with
-- apps/web/lib/access-code.ts.
create or replace function public.verify_bcrypt(plain_text text, password_hash text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select coalesce(password_hash = extensions.crypt(plain_text, password_hash), false);
$$;

-- Strong random one-time-ish access secret: 128 bits encoded as 32 lowercase hex
-- characters. This intentionally has no relationship to the user's email.
create or replace function public.generate_access_code()
returns text
language sql
security definer
set search_path = public
as $$
  select encode(extensions.gen_random_bytes(16), 'hex');
$$;

create or replace function public.hash_access_code(code text)
returns text
language sql
security definer
set search_path = public
as $$
  select extensions.crypt(code, extensions.gen_salt('bf'));
$$;

-- Keep the legacy/previous verify_access_code RPC as a database-side wrapper for
-- compatibility, but make it delegate to verify_bcrypt against the stored hash.
create or replace function public.verify_access_code(email text, code text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.allowed_users au
    where au.email = verify_access_code.email
      and public.verify_bcrypt(verify_access_code.code, au.access_code_hash)
  );
$$;

-- Admin helper for issuing a fresh random secret. It returns the plaintext once
-- so it can be delivered out-of-band, and stores only the bcrypt hash.
create or replace function public.rotate_access_code(email text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  new_code text;
begin
  new_code := public.generate_access_code();

  update public.allowed_users
  set access_code_hash = public.hash_access_code(new_code)
  where allowed_users.email = rotate_access_code.email;

  if not found then
    return null;
  end if;

  return new_code;
end;
$$;

-- New rows get a random hashed secret. The plaintext is deliberately not logged;
-- use rotate_access_code(email) to issue a deliverable code.
create or replace function public.set_initial_access_code()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.access_code_hash is null then
    new.access_code_hash := public.hash_access_code(public.generate_access_code());
  end if;
  return new;
end;
$$;

drop trigger if exists trg_set_initial_access_code on public.allowed_users;
create trigger trg_set_initial_access_code
  before insert on public.allowed_users
  for each row
  execute function public.set_initial_access_code();

-- Backfill existing rows that do not yet have hashes with random secrets. Because
-- plaintext is not stored or logged, admins should rotate codes for users who
-- need a known deliverable secret.
update public.allowed_users
set access_code_hash = public.hash_access_code(public.generate_access_code())
where access_code_hash is null;
