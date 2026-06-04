import test from "node:test";
import assert from "node:assert/strict";

/* ═════════════════════════════════════════════════════════════════════
   verifyAccessCode + rotateAccessCode — all RPC response branches
   (Single parent test so the module cache is fresh with one set of mocks)
   ═════════════════════════════════════════════════════════════════════ */

test("verifyAccessCode + rotateAccessCode — all RPC response branches", async (t) => {
  let rpcResponse: { data: unknown; error: unknown } = { data: true, error: null };
  let allowedUserResponse: { data: { access_code_hash: string } | null; error: unknown } = {
    data: { access_code_hash: "$2a$10$abcdefghijklmnopqrstuuabcdabcdabcdabcdabcdabcdabcd" },
    error: null,
  };
  const rpcCalls: Array<{ name: string; params: unknown }> = [];

  t.mock.module("@/lib/supabase/admin", {
    namedExports: {
      createSupabaseAdminClient: () => ({
        from: (table: string) => ({
          select: (columns: string) => ({
            eq: (column: string, value: string) => ({
              maybeSingle: async () => {
                assert.equal(table, "allowed_users");
                assert.equal(columns, "access_code_hash");
                assert.equal(column, "email");
                assert.equal(value, value.toLowerCase());
                return allowedUserResponse;
              },
            }),
          }),
        }),
        rpc: async (name: string, params: unknown) => {
          rpcCalls.push({ name, params });
          return rpcResponse;
        },
      }),
    },
  });

  const { verifyAccessCode, rotateAccessCode } = await import("../lib/access-code");

  /* ── verifyAccessCode ─────────────────────────────────────────────── */

  await t.test("verifyAccessCode — correct bcrypt-verified secret is accepted", async () => {
    rpcCalls.length = 0;
    allowedUserResponse = { data: { access_code_hash: "$2a$10$storedHashForUser" }, error: null };
    rpcResponse = { data: true, error: null };

    const result = await verifyAccessCode("User@WHUB.fr", "valid-random-secret");

    assert.equal(result, true);
    assert.deepEqual(rpcCalls, [
      {
        name: "verify_bcrypt",
        params: {
          plain_text: "valid-random-secret",
          password_hash: "$2a$10$storedHashForUser",
        },
      },
    ]);
  });

  await t.test("verifyAccessCode — old email-derived code is rejected", async () => {
    rpcCalls.length = 0;
    allowedUserResponse = { data: { access_code_hash: "$2a$10$storedHashForUser" }, error: null };
    rpcResponse = { data: false, error: null };

    const result = await verifyAccessCode("user@whub.fr", "user");

    assert.equal(result, false);
    assert.equal(rpcCalls[0]?.name, "verify_bcrypt");
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