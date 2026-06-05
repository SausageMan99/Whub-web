# Audit Remediation Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fix all P0 and P1 security/operational findings from AUDIT_ARCHITECTURE.md in the W hub CV Factory codebase.

**Architecture:** Sequential implementation per audit priority (P0 → P1). Each task = one audit finding with TDD cycle. Cross-component changes (migration + web code + worker config) grouped as single atomic task.

**Tech Stack:** Next.js (apps/web), Supabase (PostgreSQL + Storage), Python worker (workers/cv-worker), TypeScript/Node tests.

---

## Phase 1: P0 Security — Critical (Tasks 1–4)

### Task 1: Add global middleware.ts to protect private routes

**Objective:** Implement Next.js middleware with matcher on `/dashboard`, `/requests/*` forcing redirect to `/login` if JWT invalid (P0-S1)

**Files:**
- Create: `apps/web/middleware.ts`
- Test: `apps/web/tests/middleware.test.ts`

**Step 1: Write failing test**
```typescript
// apps/web/tests/middleware.test.ts
import { NextRequest } from 'next/server';
import { middleware } from '../middleware';

describe('middleware', () => {
  it('redirects unauthenticated /dashboard to /login', async () => {
    const req = new NextRequest('http://localhost/dashboard', { headers: { cookie: '' } });
    const res = await middleware(req);
    expect(res.headers.get('location')).toBe('/login');
  });

  it('allows authenticated /dashboard through', async () => {
    // Mock valid session cookie
    const req = new NextRequest('http://localhost/dashboard', {
      headers: { cookie: 'sb-access-token=valid; sb-refresh-token=valid' }
    });
    const res = await middleware(req);
    expect(res).toBeNull(); // NextResponse.next()
  });
});
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/middleware.test.ts
# Expected: FAIL — middleware not found
```

**Step 3: Write minimal implementation**
```typescript
// apps/web/middleware.ts
import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function middleware(request: NextRequest) {
  const response = NextResponse.next();
  
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll(); },
        setAll(cookiesToSet) { cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options)); }
      }
    }
  );

  const { data: { session } } = await supabase.auth.getSession();
  
  const protectedPaths = ['/dashboard', '/requests'];
  const isProtected = protectedPaths.some(path => request.nextUrl.pathname.startsWith(path));
  
  if (isProtected && !session) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('redirect', request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  
  return response;
}

export const config = {
  matcher: ['/dashboard/:path*', '/requests/:path*']
};
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/middleware.test.ts
# Expected: PASS
```

**Step 5: Commit**
```bash
git add apps/web/middleware.ts apps/web/tests/middleware.test.ts
git commit -m "feat: add middleware.ts for route protection (P0-S1)"
```

---

### Task 2: Harden RLS on cv_requests — members read only own requests

**Objective:** Replace global read policy with per-user ownership + admin override (P0-S2)

**Files:**
- Modify: `supabase/migrations/002_rls.sql:40-41`
- Test: Add verification queries in same migration file

**Step 1: Write failing test (SQL verification queries)**
```sql
-- In 002_rls.sql, add at end for verification
-- Test: member sees only own requests
SET ROLE authenticated;
SET request.jwt.claims = '{"sub": "user-1", "role": "authenticated"}';
SELECT count(*) FROM cv_requests; -- Should return only user-1's rows

-- Test: admin sees all
SET ROLE authenticated;
SET request.jwt.claims = '{"sub": "admin-1", "role": "authenticated", "app_metadata": {"is_admin": true}}';
SELECT count(*) FROM cv_requests; -- Should return all rows
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: FAIL — current policy allows all reads
```

**Step 3: Write minimal implementation**
```sql
-- supabase/migrations/002_rls.sql
-- REPLACE lines 40-41 (the existing policy)

DROP POLICY IF EXISTS "allowed users can read requests" ON public.cv_requests;

-- Members read only their own
CREATE POLICY "members read own requests" ON public.cv_requests
  FOR SELECT TO authenticated
  USING (created_by = auth.uid());

-- Admins read all
CREATE POLICY "admins read all requests" ON public.cv_requests
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.allowed_users
      WHERE user_id = auth.uid() AND is_admin = true
    )
  );
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: PASS — verification queries return expected counts
```

**Step 5: Commit**
```bash
git add supabase/migrations/002_rls.sql
git commit -m "feat: harden RLS on cv_requests — per-user ownership + admin override (P0-S2)"
```

---

### Task 3: Replace email-derived access code with random secret + bcrypt

**Objective:** Replace predictable access code derivation with random secret stored as bcrypt hash (P0-S3)

**Files:**
- Modify: `apps/web/lib/access-code.ts`
- Modify: `apps/web/app/login/actions.ts`
- Create: `supabase/migrations/008_access_code_secrets.sql` (new migration)
- Test: `apps/web/tests/access-code.test.ts` (extend existing)

**Step 1: Write failing test**
```typescript
// apps/web/tests/access-code.test.ts — add to existing
describe('access code secrets', () => {
  it('verifyAccessCode rejects predictable email-derived code', async () => {
    // Setup: insert user with bcrypt hash of random secret (not email-derived)
    const result = await verifyAccessCode('user@whub.fr', 'user'); // old predictable code
    expect(result.ok).toBe(false);
  });

  it('verifyAccessCode accepts correct bcrypt-verified secret', async () => {
    // Insert user with known secret, test verification passes
    const result = await verifyAccessCode('user@whub.fr', 'correct-secret');
    expect(result.ok).toBe(true);
  });
});
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/access-code.test.ts
# Expected: FAIL — current impl uses email-derived code
```

**Step 3: Write minimal implementation**
```sql
-- supabase/migrations/008_access_code_secrets.sql
ALTER TABLE allowed_users ADD COLUMN IF NOT EXISTS access_code_hash TEXT;

-- Backfill: generate random secret for each user, store bcrypt hash
-- (Run once, then remove or keep for reference)
UPDATE allowed_users
SET access_code_hash = crypt(gen_random_uuid()::text, gen_salt('bf'))
WHERE access_code_hash IS NULL;
```

```typescript
// apps/web/lib/access-code.ts — REPLACE verifyAccessCode
import { createSupabaseAdminClient } from '@/lib/supabase/admin';
import { normalizeEmail } from './normalize-email'; // existing

export async function verifyAccessCode(email: string, providedCode: string): Promise<{ ok: boolean; userId?: string; error?: string }> {
  const admin = createSupabaseAdminClient();
  const normEmail = normalizeEmail(email);
  
  const { data: user, error } = await admin
    .from('allowed_users')
    .select('user_id, access_code_hash')
    .eq('email', normEmail)
    .single();
  
  if (error || !user) return { ok: false, error: 'user_not_found' };
  if (!user.access_code_hash) return { ok: false, error: 'no_secret_configured' };
  
  // Verify bcrypt hash
  const { data: valid, error: verifyError } = await admin.rpc('verify_bcrypt', {
    hash: user.access_code_hash,
    password: providedCode
  });
  
  if (verifyError || !valid) return { ok: false, error: 'invalid_code' };
  
  return { ok: true, userId: user.user_id };
}
```

```typescript
// apps/web/app/login/actions.ts — UPDATE login() to use new verifyAccessCode
// The function signature stays same, just ensure it calls the updated verifyAccessCode
```

```sql
-- Add helper RPC for bcrypt verify (in same migration 008)
CREATE OR REPLACE FUNCTION verify_bcrypt(hash TEXT, password TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  RETURN hash = crypt(password, hash);
END;
$$;
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/access-code.test.ts
# Expected: PASS
```

**Step 5: Commit**
```bash
git add supabase/migrations/008_access_code_secrets.sql apps/web/lib/access-code.ts apps/web/app/login/actions.ts apps/web/tests/access-code.test.ts
git commit -m "feat: replace email-derived access code with bcrypt random secrets (P0-S3)"
```

---

### Task 4: Restrict worker to dedicated PostgreSQL role (not service_role)

**Objective:** Create `whub_worker` role with minimal GRANTs; update worker config (P0-S4)

**Files:**
- Create: `supabase/migrations/009_worker_role.sql`
- Modify: `workers/cv-worker/src/supabase_client.py`
- Modify: `.env` (add WORKER_DB_PASSWORD, remove service_role usage)

**Step 1: Write failing test (SQL)**
```sql
-- In 009_worker_role.sql, add verification
-- Test: whub_worker can ONLY access needed tables
SET ROLE whub_worker;
SELECT 1 FROM cv_requests; -- OK
SELECT 1 FROM cv_versions; -- OK
SELECT 1 FROM cv_events; -- OK
SELECT 1 FROM cv_comments; -- OK
SELECT 1 FROM auth.users; -- MUST FAIL
SELECT 1 FROM storage.objects; -- MUST FAIL
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: FAIL — role doesn't exist yet
```

**Step 3: Write minimal implementation**
```sql
-- supabase/migrations/009_worker_role.sql
CREATE ROLE whub_worker WITH LOGIN PASSWORD 'changeme_set_in_env';

GRANT USAGE ON SCHEMA public TO whub_worker;

GRANT SELECT, INSERT, UPDATE ON cv_requests TO whub_worker;
GRANT SELECT, INSERT, UPDATE ON cv_versions TO whub_worker;
GRANT SELECT, INSERT ON cv_events TO whub_worker;
GRANT SELECT, INSERT ON cv_comments TO whub_worker;

GRANT USAGE, SELECT ON SEQUENCE cv_versions_version_number_seq TO whub_worker;

-- Explicitly REVOKE everything else
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM whub_worker;
-- (The GRANTs above re-allow only what's needed)
```

```python
# workers/cv-worker/src/supabase_client.py — REPLACE create_client
import os
from supabase import create_client

def get_worker_client():
    url = os.environ['SUPABASE_URL']
    key = os.environ['WORKER_DB_PASSWORD']  # Password for whub_worker role
    # Use PostgREST with role password (not service_role)
    # Option: use psycopg2 directly with role credentials
    # For Supabase Python client, we need a different approach
    # Best: use direct psycopg2 connection with role
    pass

# Actually, Supabase Python client uses service_role. 
# Better: switch worker to use psycopg2 with role credentials
```

```python
# workers/cv-worker/src/supabase_client.py — FULL REPLACE with psycopg2
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

DB_URL = os.environ['WORKER_DATABASE_URL']  # postgresql://whub_worker:pass@host:5432/postgres

@contextmanager
def get_db():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Update all worker modules to use get_db() instead of supabase client
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: PASS — verification queries work, unauthorized fail
```

**Step 5: Commit**
```bash
git add supabase/migrations/009_worker_role.sql workers/cv-worker/src/supabase_client.py
git commit -m "feat: restrict worker to dedicated whub_worker PostgreSQL role (P0-S4)"
```

---

## Phase 2: P1 Security/Operational — High (Tasks 5–9)

### Task 5: PDF magic header validation + size limit on upload

**Objective:** Verify `%PDF-` magic bytes server-side; reject non-PDF; enforce max size (P1-S5)

**Files:**
- Modify: `apps/web/app/requests/new/actions.ts:27`
- Test: `apps/web/tests/pdf-validation.test.ts` (new)

**Step 1: Write failing test**
```typescript
// apps/web/tests/pdf-validation.test.ts
import { prepareUpload } from '../app/requests/new/actions';
import { File } from 'web-streams-polyfill';

describe('PDF validation', () => {
  it('rejects file without %PDF- magic header', async () => {
    const fakePdf = new File(['not a pdf'], 'fake.pdf', { type: 'application/pdf' });
    const formData = new FormData();
    formData.set('file', fakePdf);
    formData.set('consignes', 'test');
    
    const result = await prepareUpload(formData);
    expect(result.ok).toBe(false);
    expect(result.error).toBe('invalid_pdf');
  });

  it('accepts valid PDF with %PDF- header', async () => {
    const validPdf = new File(['%PDF-1.4\n...'], 'valid.pdf', { type: 'application/pdf' });
    const formData = new FormData();
    formData.set('file', validPdf);
    formData.set('consignes', 'test');
    
    const result = await prepareUpload(formData);
    expect(result.ok).toBe(true);
  });

  it('rejects files > 10MB', async () => {
    const largePdf = new File([new ArrayBuffer(11 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' });
    const formData = new FormData();
    formData.set('file', largePdf);
    formData.set('consignes', 'test');
    
    const result = await prepareUpload(formData);
    expect(result.ok).toBe(false);
    expect(result.error).toBe('file_too_large');
  });
});
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/pdf-validation.test.ts
# Expected: FAIL — no validation implemented
```

**Step 3: Write minimal implementation**
```typescript
// apps/web/app/requests/new/actions.ts — ADD at start of prepareUpload
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const PDF_MAGIC = Buffer.from('%PDF-');

const file = formData.get('file') as File;
if (!file) return { ok: false, error: 'no_file' };

if (file.size > MAX_FILE_SIZE) {
  return { ok: false, error: 'file_too_large' };
}

// Read first 5 bytes to check magic header
const arrayBuffer = await file.slice(0, 5).arrayBuffer();
const header = Buffer.from(arrayBuffer);
if (!header.equals(PDF_MAGIC)) {
  return { ok: false, error: 'invalid_pdf' };
}

// Continue with existing upload logic...
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/pdf-validation.test.ts
# Expected: PASS
```

**Step 5: Commit**
```bash
git add apps/web/app/requests/new/actions.ts apps/web/tests/pdf-validation.test.ts
git commit -m "feat: PDF magic header validation + 10MB size limit on upload (P1-S5)"
```

---

### Task 6: Atomic version_number via PostgreSQL sequence

**Objective:** Replace race-prone `next_version_number()` with PG sequence (P1-F3)

**Files:**
- Create: `supabase/migrations/010_version_sequence.sql`
- Modify: `workers/cv-worker/src/storage.py` (remove `next_version_number`, use sequence)
- Test: SQL verification in migration

**Step 1: Write failing test**
```sql
-- In 010_version_sequence.sql
-- Test: concurrent inserts get unique version_numbers
SET ROLE whub_worker;
INSERT INTO cv_versions (cv_request_id, version_number, pdf_path, json_path, meta_json)
VALUES ('req-1', nextval('cv_versions_version_number_seq'), '', '', '{}');
INSERT INTO cv_versions (cv_request_id, version_number, pdf_path, json_path, meta_json)
VALUES ('req-1', nextval('cv_versions_version_number_seq'), '', '', '{}');
-- Should get version_number 1 and 2 automatically
SELECT version_number FROM cv_versions WHERE cv_request_id = 'req-1' ORDER BY version_number;
-- Expected: 1, 2 (no collision)
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: FAIL — sequence doesn't exist or not used
```

**Step 3: Write minimal implementation**
```sql
-- supabase/migrations/010_version_sequence.sql
CREATE SEQUENCE IF NOT EXISTS cv_versions_version_number_seq;

ALTER TABLE cv_versions 
  ALTER COLUMN version_number SET DEFAULT nextval('cv_versions_version_number_seq');

-- For existing rows, ensure sequence is ahead
SELECT setval('cv_versions_version_number_seq', COALESCE((SELECT max(version_number) FROM cv_versions), 0) + 1, false);

-- Grant to worker role
GRANT USAGE, SELECT ON SEQUENCE cv_versions_version_number_seq TO whub_worker;
```

```python
# workers/cv-worker/src/storage.py — REPLACE next_version_number()
# REMOVE the function entirely, and in save_success():
# Just INSERT without specifying version_number (uses DEFAULT)
async def save_success(...):
    # ...
    async with get_db() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO cv_versions (cv_request_id, pdf_path, json_path, meta_json)
                VALUES (%s, %s, %s, %s)
                RETURNING version_number
            """, (request_id, pdf_path, json_path, json.dumps(meta)))
            version = await cur.fetchone()
            version_number = version['version_number']
    # ...
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: PASS — concurrent inserts get unique versions
```

**Step 5: Commit**
```bash
git add supabase/migrations/010_version_sequence.sql workers/cv-worker/src/storage.py
git commit -m "feat: atomic version_number via PostgreSQL sequence (P1-F3)"
```

---

### Task 7: Circuit breaker + exponential backoff on polling

**Objective:** Add backoff (max 300s) and circuit breaker after N consecutive errors (P1-F4)

**Files:**
- Modify: `workers/cv-worker/src/main.py`
- Test: `workers/cv-worker/tests/test_main.py` (new or extend)

**Step 1: Write failing test**
```python
# workers/cv-worker/tests/test_main.py
import pytest
from unittest.mock import patch, AsyncMock
from main import poll_with_backoff

@pytest.mark.asyncio
async def test_exponential_backoff_on_errors():
    errors = [Exception("db down")] * 5 + [None]  # 5 errors then success
    call_count = 0
    
    async def mock_claim(*args, **kwargs):
        nonlocal call_count
        if call_count < 5:
            call_count += 1
            raise errors[call_count - 1]
        call_count += 1
        return {"id": "job-1"}
    
    with patch('main.claim_next_cv_request', mock_claim):
        with patch('main.time.sleep') as mock_sleep:
            result = await poll_with_backoff(max_retries=10)
            assert result == {"id": "job-1"}
            # Check backoff: 10s, 20s, 40s, 80s, 160s (capped at 300s)
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert delays == [10, 20, 40, 80, 160]

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_10_consecutive_errors():
    with patch('main.claim_next_cv_request', side_effect=Exception("persistent")):
        with patch('main.time.sleep'):
            with pytest.raises(Exception, match="Circuit breaker open"):
                await poll_with_backoff(max_retries=15)
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory/workers/cv-worker && python -m pytest tests/test_main.py -v
# Expected: FAIL — no backoff/circuit breaker implemented
```

**Step 3: Write minimal implementation**
```python
# workers/cv-worker/src/main.py — REPLACE the polling loop
import time
import logging

class CircuitBreaker:
    def __init__(self, failure_threshold=10, recovery_timeout=300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self):
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logging.warning(f"Circuit breaker OPEN after {self.failure_count} failures")
    
    def can_attempt(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        # half-open: allow one attempt
        return True

async def poll_with_backoff(settings, max_retries=None):
    breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=300)
    base_delay = settings.poll_interval_seconds  # 10s
    max_delay = 300
    attempt = 0
    
    while max_retries is None or attempt < max_retries:
        if not breaker.can_attempt():
            raise Exception("Circuit breaker open - Supabase unavailable")
        
        try:
            job = await claim_next_cv_request()
            if job:
                breaker.record_success()
                return job
            breaker.record_success()  # No job is not an error
            await asyncio.sleep(base_delay)
            attempt = 0  # Reset on successful poll (even if no job)
        except Exception as e:
            breaker.record_failure()
            attempt += 1
            if breaker.state == "open":
                raise Exception("Circuit breaker open") from e
            
            # Exponential backoff
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logging.warning(f"Poll attempt {attempt} failed: {e}. Backing off {delay}s")
            await asyncio.sleep(delay)
    
    return None
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory/workers/cv-worker && python -m pytest tests/test_main.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add workers/cv-worker/src/main.py workers/cv-worker/tests/test_main.py
git commit -m "feat: circuit breaker + exponential backoff on polling (P1-F4)"
```

---

### Task 8: Explicit workdir cleanup in try/finally

**Objective:** Ensure `/tmp/whub-cv-factory-*` cleaned up on success and crash (P1-F5)

**Files:**
- Modify: `workers/cv-worker/src/main.py` (process_job function)
- Test: `workers/cv-worker/tests/test_cleanup.py` (new)

**Step 1: Write failing test**
```python
# workers/cv-worker/tests/test_cleanup.py
import tempfile
import os
from unittest.mock import patch, MagicMock
from main import process_job

def test_workdir_cleaned_on_success():
    with tempfile.TemporaryDirectory() as tmp:
        job = {"id": "test-1", "source_path": "cv-sources/test.pdf"}
        with patch('main.download_source') as mock_dl:
            with patch('main.extract_text') as mock_ext:
                with patch('main.structure_cv') as mock_struct:
                    with patch('main.render_pdf') as mock_render:
                        with patch('main.qa_check') as mock_qa:
                            with patch('main.save_success') as mock_save:
                                mock_dl.return_value = os.path.join(tmp, "source.pdf")
                                mock_ext.return_value = "text"
                                mock_struct.return_value = {}
                                mock_render.return_value = os.path.join(tmp, "out.pdf")
                                mock_qa.return_value = True
                                
                                process_job(job)
                                
                                # Verify workdir cleaned
                                workdirs = [d for d in os.listdir('/tmp') if d.startswith('whub-cv-factory')]
                                assert len(workdirs) == 0

def test_workdir_cleaned_on_exception():
    with tempfile.TemporaryDirectory() as tmp:
        job = {"id": "test-2", "source_path": "cv-sources/test.pdf"}
        with patch('main.download_source') as mock_dl:
            mock_dl.side_effect = Exception("Download failed")
            
            try:
                process_job(job)
            except:
                pass
            
            workdirs = [d for d in os.listdir('/tmp') if d.startswith('whub-cv-factory')]
            assert len(workdirs) == 0
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory/workers/cv-worker && python -m pytest tests/test_cleanup.py -v
# Expected: FAIL — no try/finally cleanup
```

**Step 3: Write minimal implementation**
```python
# workers/cv-worker/src/main.py — WRAP process_job body in try/finally
import tempfile
import shutil
import os

async def process_job(job: dict):
    workdir = tempfile.mkdtemp(prefix='whub-cv-factory-')
    try:
        # ... existing process_job logic ...
        # Use workdir for all temp files
        pass
    finally:
        # Explicit cleanup
        shutil.rmtree(workdir, ignore_errors=True)
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory/workers/cv-worker && python -m pytest tests/test_cleanup.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add workers/cv-worker/src/main.py workers/cv-worker/tests/test_cleanup.py
git commit -m "feat: explicit workdir cleanup in try/finally (P1-F5)"
```

---

### Task 9: Fix claim RPC to requeue failed jobs with empty candidate_first_name

**Objective:** Allow requeue of failed jobs where `candidate_first_name=''` (P1 from user message)

**Files:**
- Modify: `supabase/migrations/011_claim_rpc_fix.sql`
- Test: SQL verification in migration

**Step 1: Write failing test**
```sql
-- In 011_claim_rpc_fix.sql
-- Setup: failed job with empty candidate_first_name
INSERT INTO cv_requests (id, status, worker_attempts, candidate_first_name, last_error)
VALUES ('failed-empty-name', 'failed', 3, '', 'Worker error');

-- Test: claim_next_cv_request should pick it up after reset
SELECT claim_next_cv_request('worker-test');
-- Expected: returns the failed-empty-name job
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: FAIL — current RPC filters out failed status
```

**Step 3: Write minimal implementation**
```sql
-- supabase/migrations/011_claim_rpc_fix.sql
CREATE OR REPLACE FUNCTION claim_next_cv_request(worker_name TEXT)
RETURNS SETOF cv_requests
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    row cv_requests;
BEGIN
    -- Requeue failed jobs with empty candidate_first_name (stuck jobs)
    UPDATE cv_requests
    SET status = 'submitted',
        worker_attempts = 0,
        last_error = NULL,
        error_category = NULL,
        updated_at = now()
    WHERE status = 'failed'
      AND candidate_first_name = ''
      AND worker_attempts >= 3;
    
    -- Standard claim: submitted jobs, ordered by priority then created_at
    FOR row IN
        SELECT * FROM cv_requests
        WHERE status = 'submitted'
          AND (worker_locked_at IS NULL OR worker_locked_at < now() - interval '30 minutes')
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    LOOP
        UPDATE cv_requests
        SET status = 'processing',
            worker_locked_by = worker_name,
            worker_locked_at = now(),
            worker_attempts = worker_attempts + 1,
            updated_at = now()
        WHERE id = row.id;
        
        RETURN NEXT row;
    END LOOP;
    
    RETURN;
END;
$$;

GRANT EXECUTE ON FUNCTION claim_next_cv_request(TEXT) TO whub_worker;
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && supabase db reset --linked
# Expected: PASS — failed jobs with empty name get requeued
```

**Step 5: Commit**
```bash
git add supabase/migrations/011_claim_rpc_fix.sql
git commit -m "fix: claim RPC requeues failed jobs with empty candidate_first_name"
```

---

## Phase 3: P1 Operational — Retry Button (Task 10)

### Task 10: Frontend "Relancer la génération" button for failed jobs

**Objective:** Allow users to retry failed jobs via UI (P1-F6)

**Files:**
- Modify: `apps/web/app/requests/[id]/actions.ts` (add retryRequest)
- Modify: `apps/web/app/requests/[id]/page.tsx` (add button)
- Test: `apps/web/tests/retry-request.test.ts` (new)

**Step 1: Write failing test**
```typescript
// apps/web/tests/retry-request.test.ts
import { retryRequest } from '../app/requests/[id]/actions';

describe('retryRequest', () => {
  it('resets failed request to submitted with attempts=0', async () => {
    const result = await retryRequest('failed-job-id');
    expect(result.ok).toBe(true);
    
    // Verify in DB
    const { data } = await supabase.from('cv_requests').select('*').eq('id', 'failed-job-id').single();
    expect(data.status).toBe('submitted');
    expect(data.worker_attempts).toBe(0);
    expect(data.last_error).toBeNull();
  });
});
```

**Step 2: Run test to verify failure**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/retry-request.test.ts
# Expected: FAIL — retryRequest doesn't exist
```

**Step 3: Write minimal implementation**
```typescript
// apps/web/app/requests/[id]/actions.ts — ADD new function
export async function retryRequest(requestId: string): Promise<{ ok: boolean; error?: string }> {
  const admin = createSupabaseAdminClient();
  
  const { error } = await admin
    .from('cv_requests')
    .update({
      status: 'submitted',
      worker_attempts: 0,
      last_error: null,
      error_category: null,
      updated_at: new Date().toISOString()
    })
    .eq('id', requestId)
    .eq('status', 'failed'); // Only allow retry from failed
  
  if (error) return { ok: false, error: 'retry_failed' };
  return { ok: true };
}
```

```tsx
// apps/web/app/requests/[id]/page.tsx — ADD button in failed state
{request.status === 'failed' && (
  <form action={async () => {
    const result = await retryRequest(request.id);
    if (result.ok) refresh();
  }}>
    <button type="submit" className="btn-primary">Relancer la génération</button>
  </form>
)}
```

**Step 4: Run test to verify pass**
```bash
cd /root/whub-cv-factory && npm test -- apps/web/tests/retry-request.test.ts
# Expected: PASS
```

**Step 5: Commit**
```bash
git add apps/web/app/requests/[id]/actions.ts apps/web/app/requests/[id]/page.tsx apps/web/tests/retry-request.test.ts
git commit -m "feat: retry button for failed jobs (P1-F6)"
```

---

## Verification Checklist (End-to-End)

After all tasks complete, run full validation:

```bash
# 1. All tests pass
cd /root/whub-cv-factory && npm test
cd /root/whub-cv-factory/workers/cv-worker && python -m pytest

# 2. Database migrations apply cleanly
supabase db reset --linked

# 3. Security verification
# - Middleware protects /dashboard and /requests/*
# - RLS: member sees only own, admin sees all
# - Access code uses bcrypt, not email-derived
# - Worker uses whub_worker role, not service_role
# - PDF upload validates magic header + size

# 4. Operational verification
# - Version sequence works under concurrency
# - Worker polling has backoff + circuit breaker
# - Workdir cleaned on success and crash
# - Failed jobs with empty name requeue
# - Retry button works in UI
```

---

## Risks & Tradeoffs

| Risk | Mitigation |
|------|------------|
| Migration 008/009 require manual secret rotation | Document in README; provide rotation script |
| Worker psycopg2 refactor is invasive | Task 4 includes full client replacement; test thoroughly |
| Circuit breaker may mask real issues | Log state changes prominently; add health endpoint |
| Sequence migration needs care with existing data | `setval` to max+1 handles it; verify in staging first |

---

## Open Questions

1. **Task 3 (access codes):** Should we send new secrets to existing users via email, or require admin to distribute? → Decision needed before migration 008.
2. **Task 4 (worker role):** Supabase Python client requires service_role for some operations. Full psycopg2 migration confirmed? → Yes, per audit.
3. **Task 10 (retry):** Should retry be limited (e.g., max 1 retry per user)? → Current spec: unlimited from failed state. Can add limit later if abused.