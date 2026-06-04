import test from "node:test";
import assert from "node:assert/strict";

const SUPABASE_URL = "https://project-ref.supabase.co";

test("next config applies a strict Content-Security-Policy header", async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = SUPABASE_URL;

  const { default: nextConfig } = await import("../next.config");
  assert.equal(typeof nextConfig.headers, "function", "expected next.config to define headers()");

  const headers = await nextConfig.headers!();
  const globalHeaders = headers.find((entry) => entry.source === "/(.*)");
  assert.ok(globalHeaders, "expected CSP headers to apply to all routes");

  const cspHeader = globalHeaders.headers.find(
    (header) => header.key.toLowerCase() === "content-security-policy"
  );
  assert.ok(cspHeader, "expected Content-Security-Policy header");

  const policy = cspHeader.value;

  assert.match(policy, /(?:^|;)\s*default-src 'self'(?:;|$)/);
  assert.match(policy, /(?:^|;)\s*script-src 'self'(?:;|$)/);
  assert.doesNotMatch(policy, /script-src[^;]*'unsafe-inline'/);
  assert.doesNotMatch(policy, /script-src[^;]*'unsafe-eval'/);
  assert.match(policy, /(?:^|;)\s*style-src 'self' 'unsafe-inline'(?:;|$)/);
  assert.match(policy, /(?:^|;)\s*img-src 'self' data: blob:(?:;|$)/);
  assert.match(policy, /(?:^|;)\s*font-src 'self'(?:;|$)/);
  assert.match(policy, new RegExp(`(?:^|;)\\s*connect-src 'self' ${SUPABASE_URL.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:;|$)`));
  assert.match(policy, /(?:^|;)\s*frame-ancestors 'none'(?:;|$)/);
  assert.match(policy, /(?:^|;)\s*base-uri 'self'(?:;|$)/);
  assert.match(policy, /(?:^|;)\s*form-action 'self'(?:;|$)/);
});
