import test from "node:test";
import assert from "node:assert/strict";

/* ═════════════════════════════════════════════════════════════════════
   verifyAccessCode + rotateAccessCode — all RPC response branches
   (Single parent test so the module cache is fresh with one set of mocks)
   ═════════════════════════════════════════════════════════════════════ */

test("verifyAccessCode + rotateAccessCode — all RPC response branches", async (t) => {
  let rpcResponse: { data: unknown; error: unknown } = { data: true, error: null };

  t.mock.module("@/lib/supabase/admin", {
    namedExports: {
      createSupabaseAdminClient: () => ({
        rpc: async (_name: string, _params: unknown) => rpcResponse,
      }),
    },
  });

  const { verifyAccessCode, rotateAccessCode } = await import("../lib/access-code");

  /* ── verifyAccessCode ─────────────────────────────────────────────── */

  await t.test("verifyAccessCode — RPC returns true", async () => {
    rpcResponse = { data: true, error: null };
    const result = await verifyAccessCode("user@whub.fr", "valid-code");
    assert.equal(result, true);
  });

  await t.test("verifyAccessCode — RPC returns false", async () => {
    rpcResponse = { data: false, error: null };
    const result = await verifyAccessCode("user@whub.fr", "wrong-code");
    assert.equal(result, false);
  });

  await t.test("verifyAccessCode — RPC returns null", async () => {
    rpcResponse = { data: null, error: null };
    const result = await verifyAccessCode("user@whub.fr", "some-code");
    assert.equal(result, false);
  });

  await t.test("verifyAccessCode — RPC returns error", async () => {
    rpcResponse = { data: null, error: { message: "DB error" } };
    const result = await verifyAccessCode("user@whub.fr", "some-code");
    assert.equal(result, false);
  });

  await t.test("verifyAccessCode — empty email returns false", async () => {
    rpcResponse = { data: true, error: null };
    const result = await verifyAccessCode("", "code");
    assert.equal(result, false);
  });

  await t.test("verifyAccessCode — empty code returns false", async () => {
    rpcResponse = { data: true, error: null };
    const result = await verifyAccessCode("user@whub.fr", "");
    assert.equal(result, false);
  });

  await t.test("verifyAccessCode — both empty returns false", async () => {
    rpcResponse = { data: true, error: null };
    const result = await verifyAccessCode("", "");
    assert.equal(result, false);
  });

  /* ── rotateAccessCode ─────────────────────────────────────────────── */

  await t.test("rotateAccessCode — RPC returns code", async () => {
    rpcResponse = { data: "new-secret-xyz", error: null };
    const result = await rotateAccessCode("user@whub.fr");
    assert.equal(result, "new-secret-xyz");
  });

  await t.test("rotateAccessCode — RPC returns null", async () => {
    rpcResponse = { data: null, error: null };
    const result = await rotateAccessCode("user@whub.fr");
    assert.equal(result, null);
  });

  await t.test("rotateAccessCode — RPC returns error", async () => {
    rpcResponse = { data: null, error: { message: "User not found" } };
    const result = await rotateAccessCode("unknown@whub.fr");
    assert.equal(result, null);
  });

  await t.test("rotateAccessCode — empty email returns null", async () => {
    rpcResponse = { data: "should-not-be-called", error: null };
    const result = await rotateAccessCode("");
    assert.equal(result, null);
  });

  await t.test("rotateAccessCode — whitespace-only email returns null", async () => {
    rpcResponse = { data: "should-not-be-called", error: null };
    const result = await rotateAccessCode("   ");
    assert.equal(result, null);
  });
});