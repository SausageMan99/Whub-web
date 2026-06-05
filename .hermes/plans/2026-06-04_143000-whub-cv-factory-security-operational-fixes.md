# W hub CV Factory – Security & Operational Fixes Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Address all P0 (Critical) and P1 (High) findings from the architecture audit, plus the failed-job requeue bug, using TDD with subagent-driven development.

**Architecture:** Next.js (Vercel) + Supabase (PostgreSQL + Storage + Auth) + Python worker (systemd on VPS). The audit identified 10 security issues (4 Critical, 3 High, 3 Medium) and 8 operational fragility points (3 High, 3 Medium, 2 Low), plus a specific bug where `failed` status jobs with empty `candidate_first_name` never requeue because the claim RPC filters `worker_attempts < 3` only on `submitted`/`revision_requested` statuses.

**Tech Stack:** TypeScript/Next.js 15, Supabase (PostgreSQL 15, Storage, Auth), Python 3.11 worker, Pytest, Vitest.

---

## Phase 1: Critical Security Fixes (P0)

### Task 1.1: Harden RLS on `cv_requests` – members read only their own requests

**Objective:** Replace the global `is_allowed_user()` read policy with per-user ownership + admin override.

**Files:**
- Modify: `supabase/migrations/002_rls.sql:40-41`
- Test: `supabase/migrations/002_rls.sql` (add verification queries)

**Step 1: Write failing test (SQL verification)**
```sql
-- Run as member user (not admin)
SET ROLE authenticated;
SET request.jwt.claims = '{"email": "member@whub.fr"}';
SELECT * FROM public.cv_requests; -- Should return ONLY rows where created_by = auth.uid()
```

**Step 2: Run test to verify failure**  
Current policy returns all rows → FAIL.

**Step 3: Write minimal implementation**
```sql
-- Replace line 40-41 in 002_rls.sql
DROP POLICY "allowed users can read requests" ON public.cv_requests;

CREATE POLICY "members read own requests" ON public.cv_requests
  FOR SELECT TO authenticated
  USING (created_by = auth.uid());

CREATE POLICY "admins read all requests" ON public.cv_requests
  FOR SELECT TO authenticated
  USING (public.current_user_role() = 'admin');
```

**Step 4: Run test to verify pass**  
Member sees only own rows, admin sees all → PASS.

**Step 5: Commit**
```bash
git add supabase/migrations/002_rls.sql
git commit -m "security: harden cv_requests RLS to per-user ownership + admin override"
```

---

### Task 1.2: Replace email-derived access code with random secret + bcrypt

**Objective:** Remove predictable password derivation; store bcrypt hash in `allowed_users`.

**Files:**
- Create: `supabase/migrations/007_access_code_hardening.sql`
- Modify: `apps/web/lib/access-code.ts` (replace logic)
- Modify: `apps/web/app/login/actions.ts` (use bcrypt verify)
- Test: `apps/web/tests/access-code.test.ts`

**Step 1: Write failing test**
```typescript
// apps/web/tests/access-code.test.ts
import { expectedAccessCodeFromEmail, isValidAccessCodeForEmail } from '@/lib/access-code';

test('OLD: access code is deterministic from email', () => {
  expect(expectedAccessCodeFromEmail('cdubosq@whub.fr')).toBe('cdubosq');
  expect(isValidAccessCodeForEmail('cdubosq@whub.fr', 'cdubosq')).toBe(true);
});
```

**Step 2: Run test to verify failure**  
Current implementation passes → this test documents the VULNERABILITY.

**Step 3: Write minimal implementation**

**Migration (007_access_code_hardening.sql):**
```sql
ALTER TABLE public.allowed_users ADD COLUMN IF NOT EXISTS access_code_hash text;

-- Generate secure random codes for existing users (run once)
UPDATE public.allowed_users
SET access_code_hash = crypt(
  encode(gen_random_bytes(16), 'hex'),
  gen_salt('bf')
)
WHERE access_code_hash IS NULL;

-- New users must have hash set on insert
CREATE OR REPLACE FUNCTION public.ensure_access_code_hash()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.access_code_hash IS NULL THEN
    NEW.access_code_hash := crypt(encode(gen_random_bytes(16), 'hex'), gen_salt('bf'));
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER ensure_access_code_hash_trigger
BEFORE INSERT ON public.allowed_users
FOR EACH ROW EXECUTE FUNCTION public.ensure_access_code_hash();
```

**access-code.ts (new):**
```typescript
// REPLACE entire file
import { createSupabaseAdminClient } from '@/lib/supabase/admin';

export async function verifyAccessCode(email: string, code: string): Promise<boolean> {
  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from('allowed_users')
    .select('access_code_hash')
    .eq('email', email.toLowerCase())
    .maybeSingle();
  
  if (error || !data?.access_code_hash) return false;
  
  // Use Supabase's crypt via RPC or pgcrypto
  const { data: valid } = await admin.rpc('verify_access_code', {
    p_email: email.toLowerCase(),
    p_code: code
  });
  return valid === true;
}

export async function rotateAccessCode(email: string): Promise<string> {
  const admin = createSupabaseAdminClient();
  const newCode = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
  const { error } = await admin.rpc('rotate_access_code', {
    p_email: email.toLowerCase(),
    p_new_code: newCode
  });
  if (error) throw error;
  return newCode;
}
```

**RPC functions (add to migration):**
```sql
CREATE OR REPLACE FUNCTION public.verify_access_code(p_email text, p_code text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  h text;
BEGIN
  SELECT access_code_hash INTO h FROM public.allowed_users WHERE lower(email) = lower(p_email);
  IF h IS NULL THEN RETURN false; END IF;
  RETURN h = crypt(p_code, h);
END $$;

CREATE OR REPLACE FUNCTION public.rotate_access_code(p_email text, p_new_code text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  UPDATE public.allowed_users
  SET access_code_hash = crypt(p_new_code, gen_salt('bf'))
  WHERE lower(email) = lower(p_email);
END $$;
```

**login/actions.ts:** Replace `isValidAccessCodeForEmail` call with `await verifyAccessCode(email, accessCode)`.

**Step 4: Run test to verify pass**  
New test: `verifyAccessCode` returns true only for correct code, false for old deterministic code.

**Step 5: Commit**
```bash
git add supabase/migrations/007_access_code_hardening.sql apps/web/lib/access-code.ts apps/web/app/login/actions.ts
git commit -m "security: replace deterministic access code with random secret + bcrypt"
```

---

### Task 1.3: Restrict worker to dedicated PostgreSQL role (no service_role_key)

**Objective:** Create `whub_worker` role with minimal grants; update worker config.

**Files:**
- Create: `supabase/migrations/008_worker_role.sql`
- Modify: `workers/cv-worker/src/supabase_client.py`
- Modify: `workers/cv-worker/.env` (new key: `SUPABASE_WORKER_KEY`)
- Test: Connection test script

**Step 1: Write failing test**
```python
# test_worker_role.py
from supabase import create_client
import os

def test_worker_cannot_access_admin_tables():
    client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_WORKER_KEY'])
    # Should fail on auth.users (admin only)
    try:
        client.auth.admin.list_users()
        assert False, "Worker should not have admin access"
    except Exception:
        pass  # Expected
```

**Step 2: Run test to verify failure**  
Current service_role_key passes admin calls → FAIL.

**Step 3: Write minimal implementation**

**Migration (008_worker_role.sql):**
```sql
-- Create dedicated role
CREATE ROLE whub_worker NOINHERIT;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO whub_worker;

-- Grant specific table permissions
GRANT SELECT, INSERT, UPDATE ON public.cv_requests TO whub_worker;
GRANT SELECT, INSERT, UPDATE ON public.cv_versions TO whub_worker;
GRANT SELECT, INSERT, UPDATE ON public.cv_comments TO whub_worker;
GRANT SELECT, INSERT ON public.cv_events TO whub_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO whub_worker;

-- Grant storage permissions via bucket policies (handled in 003_storage.sql update)
-- Worker uses service role for storage uploads only (separate key)

-- Create login role with password (generate secure password)
-- Run once: ALTER ROLE whub_worker WITH LOGIN PASSWORD 'generated-secure-password';
```

**supabase_client.py:**
```python
from supabase import create_client
from .config import settings

# Use worker-specific key (not service_role)
client = create_client(settings.supabase_url, settings.supabase_worker_key)
```

**config.py:** Add `supabase_worker_key: str` field.

**Step 4: Run test to verify pass**  
Worker can CRUD cv_* tables but not auth.admin → PASS.

**Step 5: Commit**
```bash
git add supabase/migrations/008_worker_role.sql workers/cv-worker/src/supabase_client.py workers/cv-worker/src/config.py
git commit -m "security: restrict worker to dedicated PostgreSQL role whub_worker"
```

---

### Task 1.4: Add global middleware.ts (already exists – verify completeness)

**Objective:** Confirm middleware protects all private routes; add CSP headers.

**Files:**
- Verify: `apps/web/middleware.ts`
- Modify: `apps/web/next.config.ts` (add CSP)

**Step 1: Write failing test**
```typescript
// apps/web/tests/middleware.test.ts
import { middleware } from '@/middleware';
import { NextRequest } from 'next/server';

test('redirects unauthenticated /dashboard to /login', async () => {
  const req = new NextRequest('http://localhost/dashboard');
  const res = await middleware(req);
  expect(res.headers.get('location')).toContain('/login');
});
```

**Step 2: Run test** – Should pass (middleware exists).

**Step 3: Add CSP to next.config.ts**
```typescript
// apps/web/next.config.ts
const nextConfig = {
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://va.vercel-scripts.com",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: https:",
              "connect-src 'self' https://*.supabase.co https://va.vercel-scripts.com",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'"
            ].join('; ')
          }
        ]
      }
    ];
  }
};
```

**Step 4: Commit**
```bash
git add apps/web/next.config.ts
git commit -m "security: add Content-Security-Policy headers"
```

---

## Phase 2: High Security Fixes (P1)

### Task 2.1: Rate limiting on login and upload Server Actions

**Objective:** Prevent brute-force and DoS via Vercel KV or in-memory with sliding window.

**Files:**
- Create: `apps/web/lib/rate-limit.ts`
- Modify: `apps/web/app/login/actions.ts`
- Modify: `apps/web/app/requests/new/actions.ts`
- Test: `apps/web/tests/rate-limit.test.ts`

**Step 1: Write failing test**
```typescript
// apps/web/tests/rate-limit.test.ts
import { rateLimit } from '@/lib/rate-limit';

test('blocks after 5 requests in 1 minute', async () => {
  const key = 'test:login:ip:1.2.3.4';
  for (let i = 0; i < 5; i++) {
    expect(await rateLimit(key, 5, 60_000)).toBe(true);
  }
  expect(await rateLimit(key, 5, 60_000)).toBe(false);
});
```

**Step 2: Run test to verify failure** – No implementation → FAIL.

**Step 3: Write minimal implementation (Vercel KV)**
```typescript
// apps/web/lib/rate-limit.ts
import { kv } from '@vercel/kv';

export async function rateLimit(key: string, limit: number, windowMs: number): Promise<boolean> {
  const now = Date.now();
  const windowStart = now - windowMs;
  
  const pipeline = kv.pipeline();
  pipeline.zremrangebyscore(key, 0, windowStart);
  pipeline.zcard(key);
  pipeline.zadd(key, { score: now, member: `${now}-${Math.random()}` });
  pipeline.expire(key, Math.ceil(windowMs / 1000) + 1);
  
  const results = await pipeline.exec();
  const currentCount = results[1] as number;
  
  return currentCount < limit;
}
```

**login/actions.ts:** Add at top of `login()`:
```typescript
const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
if (!await rateLimit(`login:ip:${ip}`, 5, 60_000)) {
  redirect('/login?error=rate_limited');
}
```

**requests/new/actions.ts:** Add similar for `createRequest`.

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**
```bash
git add apps/web/lib/rate-limit.ts apps/web/app/login/actions.ts apps/web/app/requests/new/actions.ts
git commit -m "security: add rate limiting on login and upload actions"
```

---

### Task 2.2: PDF magic header validation on upload

**Objective:** Reject non-PDF files even with correct MIME type.

**Files:**
- Modify: `apps/web/app/requests/new/actions.ts` (prepareUpload/createRequest)
- Test: `apps/web/tests/upload.test.ts`

**Step 1: Write failing test**
```typescript
// apps/web/tests/upload.test.ts
import { createRequest } from '@/app/requests/new/actions';

test('rejects executable renamed as .pdf', async () => {
  const fakePdf = new File(['MZ\x90\x00'], 'malware.pdf', { type: 'application/pdf' });
  const formData = new FormData();
  formData.append('file', fakePdf);
  // ... setup request
  const result = await createRequest(formData);
  expect(result.ok).toBe(false);
});
```

**Step 2: Run test to verify failure** – Current code only checks MIME → FAIL.

**Step 3: Write minimal implementation**
```typescript
// In prepareUpload or createRequest, after receiving file buffer
const buffer = await file.arrayBuffer();
const bytes = new Uint8Array(buffer);
if (bytes.length < 5 || 
    bytes[0] !== 0x25 || bytes[1] !== 0x50 || bytes[2] !== 0x44 || bytes[3] !== 0x46 || bytes[4] !== 0x2d) {
  // Not a valid PDF (%PDF-)
  return { ok: false, error: 'invalid_pdf' };
}
```

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**
```bash
git add apps/web/app/requests/new/actions.ts
git commit -m "security: validate PDF magic header on upload"
```

---

### Task 2.3: Atomic version_number via PostgreSQL sequence

**Objective:** Eliminate race condition in `next_version_number()`.

**Files:**
- Create: `supabase/migrations/009_version_sequence.sql`
- Modify: `workers/cv-worker/src/storage.py`
- Test: `workers/cv-worker/tests/test_version_atomic.py`

**Step 1: Write failing test**
```python
# workers/cv-worker/tests/test_version_atomic.py
import asyncio
from src.storage import next_version_number

async def test_concurrent_version_numbers():
    # Simulate concurrent calls
    results = await asyncio.gather(*[next_version_number('test-req') for _ in range(10)])
    assert len(set(results)) == 10, "All version numbers must be unique"
```

**Step 2: Run test to verify failure** – Current SELECT+1 race → duplicates → FAIL.

**Step 3: Write minimal implementation**

**Migration (009_version_sequence.sql):**
```sql
CREATE SEQUENCE public.cv_version_seq;

ALTER TABLE public.cv_versions ALTER COLUMN version_number SET DEFAULT nextval('public.cv_version_seq');

-- Or use per-request sequence via RPC
CREATE OR REPLACE FUNCTION public.next_version_number(p_request_id uuid)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v int;
BEGIN
  LOCK TABLE public.cv_versions IN SHARE ROW EXCLUSIVE MODE;
  SELECT COALESCE(MAX(version_number), 0) + 1 INTO v
  FROM public.cv_versions WHERE request_id = p_request_id;
  RETURN v;
END $$;
```

**storage.py:**
```python
def next_version_number(request_id: str) -> int:
    res = client.rpc("next_version_number", {"p_request_id": request_id}).execute()
    return int(res.data)
```

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**
```bash
git add supabase/migrations/009_version_sequence.sql workers/cv-worker/src/storage.py
git commit -m "fix: atomic version_number via PostgreSQL sequence/RPC"
```

---

### Task 2.4: Circuit breaker + exponential backoff on polling

**Objective:** Stop worker from hammering Supabase during outages.

**Files:**
- Modify: `workers/cv-worker/src/main.py`
- Test: `workers/cv-worker/tests/test_circuit_breaker.py`

**Step 1: Write failing test**
```python
# workers/cv-worker/tests/test_circuit_breaker.py
from src.main import CircuitBreaker

def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == 'open'
    import time; time.sleep(1.1)
    assert cb.state == 'half_open'
```

**Step 2: Run test to verify failure** – No CircuitBreaker class → FAIL.

**Step 3: Write minimal implementation**
```python
# In main.py, add at top
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = CircuitState.CLOSED
    
    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN
        return True

# In main(), wrap claim_next_job:
breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

while True:
    if not breaker.can_execute():
        log.warning("Circuit breaker open, backing off")
        time.sleep(settings.poll_interval_seconds * 4)  # longer backoff
        continue
    job = claim_next_job()
    if not job:
        time.sleep(settings.poll_interval_seconds)
        continue
    try:
        process_job(job)
        breaker.record_success()
    except Exception as exc:
        breaker.record_failure()
        # ... existing error handling
```

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**
```bash
git add workers/cv-worker/src/main.py
git commit -m "ops: add circuit breaker and exponential backoff on Supabase polling"
```

---

### Task 2.5: Explicit workdir cleanup in try/finally

**Objective:** Prevent /tmp filling up on worker crashes.

**Files:**
- Modify: `workers/cv-worker/src/main.py` (process_job)
- Test: `workers/cv-worker/tests/test_workdir_cleanup.py`

**Step 1: Write failing test**
```python
# workers/cv-worker/tests/test_workdir_cleanup.py
from src.main import process_job
from unittest.mock import patch, MagicMock
import tempfile
import os

def test_workdir_cleaned_on_exception():
    with tempfile.TemporaryDirectory() as tmp:
        with patch('src.main.settings.tmp_dir', tmp):
            job = {'id': 'test-cleanup', 'candidate_first_name': 'Jean'}
            with patch('src.main.download_source', side_effect=Exception('boom')):
                process_job(job)
            # workdir should not exist
            workdir = os.path.join(tmp, 'test-cleanup')
            assert not os.path.exists(workdir), "Workdir should be cleaned up"
```

**Step 2: Run test to verify failure** – Current code only cleans at START → FAIL.

**Step 3: Write minimal implementation**
```python
# In process_job, wrap everything in try/finally
workdir = Path(settings.tmp_dir) / request_id
try:
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # ... all processing
finally:
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)
```

**Step 4: Run test to verify pass** → PASS.

**Step 5: Commit**
```bash
git add workers/cv-worker/src/main.py
git commit -m "ops: explicit workdir cleanup in try/finally"
```

---

## Phase 3: Failed-Job Requeue Bug (Critical Operational)

### Task 3.1: Fix claim RPC to requeue failed jobs with empty candidate_first_name

**Objective:** Allow `failed` status jobs to be re-claimed when `worker_attempts < 3`.

**Files:**
- Modify: `supabase/migrations/004_claim_rpc.sql`
- Test: SQL verification

**Step 1: Write failing test**
```sql
-- Insert a failed job with candidate_first_name = '' and worker_attempts = 1
INSERT INTO public.cv_requests (id, created_by, candidate_first_name, status, worker_attempts)
VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000000'::uuid, '', 'failed', 1);

-- Call claim RPC
SELECT * FROM public.claim_next_cv_request('test-worker');
-- Should return the failed job (currently returns nothing)
```

**Step 2: Run test to verify failure** – Current WHERE clause excludes `failed` status → FAIL.

**Step 3: Write minimal implementation**
```sql
-- In 004_claim_rpc.sql, modify WHERE clause (lines 20-22)
WHERE r.id = (
    SELECT id
    FROM public.cv_requests
    WHERE status IN ('submitted', 'revision_requested', 'failed')  -- ADD 'failed'
      AND (worker_locked_at IS NULL OR worker_locked_at < NOW() - INTERVAL '30 MINUTES')
      AND worker_attempts < 3
    ORDER BY
      CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
      created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
```

**Step 4: Run test to verify pass** → PASS (failed job with attempts < 3 gets claimed).

**Step 5: Commit**
```bash
git add supabase/migrations/004_claim_rpc.sql
git commit -m "fix: claim RPC includes failed status for requeue (worker_attempts < 3)"
```

---

### Task 3.2: Add "Relancer la génération" button in frontend (already exists in retryRequest)

**Objective:** Verify `retryRequest` action works for the empty-first-name case.

**Files:**
- Verify: `apps/web/app/requests/[id]/actions.ts` (retryRequest)
- Test: `apps/web/tests/retry-request.test.ts`

**Step 1: Write failing test** – Test that retryRequest resets `worker_attempts=0` and `status='submitted'` for `failed` jobs.

**Step 2: Run test** – Should pass (code exists at lines 107-118).

**Step 3: Commit if any changes needed** – Likely no changes.

---

## Phase 4: Medium Operational Fixes (P2) – Deferred but Planned

| Task | Description | Files |
|------|-------------|-------|
| 4.1 | Dockerize worker + package assets | `Dockerfile`, `infra/` |
| 4.2 | Health endpoint + metrics | `workers/cv-worker/src/main.py` (`/health`) |
| 4.3 | Signed URLs for Storage (no public paths) | `003_storage.sql`, download routes |
| 4.4 | Migrate polling to Redis/BullMQ queue | Architecture change |

---

## Verification Checklist

After all P0/P1 tasks complete:

- [ ] Run full test suite: `cd workers/cv-worker && pytest -v` and `cd apps/web && npm test`
- [ ] Apply migrations to staging Supabase: `supabase db push`
- [ ] Deploy worker with new config (service_role → worker key)
- [ ] Deploy web to Vercel preview
- [ ] End-to-end test: upload PDF → worker processes → PDF generated → download works
- [ ] Test failed-job requeue: create job with empty first_name → fails → click "Relancer" → succeeds
- [ ] Security audit: verify RLS (member sees only own), access code not derivable, worker key limited

---

## Risk & Trade-offs

| Risk | Mitigation |
|------|------------|
| Migration 007/008 require downtime | Run during low-traffic; `allowed_users` is small |
| Worker key rotation | Generate new key, update VPS `.env`, restart systemd |
| CSP may break inline scripts | Start with `report-only` mode, monitor console |
| Rate limit false positives | Set generous limits (5/min login, 10/min upload), monitor logs |

---

## Execution Order

1. **Task 1.1** (RLS) – Independent, high impact
2. **Task 1.2** (Access code) – Independent, high impact  
3. **Task 1.3** (Worker role) – Requires VPS deploy coordination
4. **Task 1.4** (CSP) – Quick win
5. **Task 2.1** (Rate limit) – Requires Vercel KV enabled
6. **Task 2.2** (PDF validation) – Independent
7. **Task 2.3** (Version sequence) – Independent
8. **Task 2.4** (Circuit breaker) – Independent
9. **Task 2.5** (Workdir cleanup) – Independent
10. **Task 3.1** (Claim RPC fix) – Critical for current blocked jobs
11. **Task 3.2** (Verify retry) – Quick verification

---

**Ready to execute using subagent-driven-development. Shall I proceed with Task 1.1?**