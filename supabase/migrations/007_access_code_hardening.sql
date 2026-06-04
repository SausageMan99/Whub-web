-- 007_access_code_hardening.sql
-- Replace deterministic email-derived access codes with random secrets + bcrypt
--
-- VULNERABILITY FIXED:
--   The old approach derived access codes from the email local part:
--     expectedAccessCodeFromEmail('cdubosq@whub.fr') → 'cdubosq'
--   Anyone who knew a user's email could compute their access code with no
--   database lookup. The access code offered zero protection beyond the email.
--
-- NEW APPROACH:
--   1. allowed_users gains an access_code_hash column (bcrypt hash of a random secret)
--   2. A trigger auto-generates a random 48-bit hex secret and hashes it on INSERT
--   3. RPC verify_access_code(email, code) checks a plaintext code against the hash
--   4. RPC rotate_access_code(email) generates a new secret, hashes it, returns plaintext
--   5. Uses pgcrypto's gen_random_bytes, gen_salt('bf' = bcrypt), and crypt

-- ── 1. Add the hash column ──
alter table public.allowed_users
  add column if not exists access_code_hash text;

-- ── 2. Helper: generate a random 12-char hex access code (48 bits) ──
create or replace function public.generate_access_code()
returns text
language sql
security definer
set search_path = public
as $$
  select encode(gen_random_bytes(6), 'hex');
$$;

-- ── 3. Helper: bcrypt-hash a plaintext access code ──
create or replace function public.hash_access_code(code text)
returns text
language sql
security definer
set search_path = public
as $$
  select crypt(code, gen_salt('bf'));
$$;

-- ── 4. RPC: verify a plaintext code against the stored bcrypt hash ──
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
      and au.access_code_hash = crypt(verify_access_code.code, au.access_code_hash)
  );
$$;

-- ── 5. RPC: generate a new access code, hash it, return the plaintext ──
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
  where email = rotate_access_code.email;
  return new_code;
end;
$$;

-- ── 6. Trigger: auto-generate + hash an access code on new allowed_user insert ──
create or replace function public.set_initial_access_code()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  new_code text;
begin
  new_code := public.generate_access_code();
  new.access_code_hash := public.hash_access_code(new_code);
  raise log 'Access code for % is: %', new.email, new_code;
  return new;
end;
$$;

drop trigger if exists trg_set_initial_access_code on public.allowed_users;
create trigger trg_set_initial_access_code
  before insert on public.allowed_users
  for each row
  execute function public.set_initial_access_code();

-- ── 7. Backfill: generate access codes for existing rows where hash is null ──
do $$
declare
  rec record;
  new_code text;
begin
  for rec in select email from public.allowed_users where access_code_hash is null
  loop
    new_code := public.generate_access_code();
    update public.allowed_users
    set access_code_hash = public.hash_access_code(new_code)
    where email = rec.email;
    raise log 'Backfilled access code for % is: %', rec.email, new_code;
  end loop;
end;
$$;