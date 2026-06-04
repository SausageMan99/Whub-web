import test from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";

/* ═════════════════════════════════════════════════════════════════════
   1. login action — all redirect branches (grouped in one parent test
      so the module cache of ../app/login/actions stays fresh with a
      single set of mutable mocks).
   ═════════════════════════════════════════════════════════════════════ */

test("login action — all redirect branches", async (t) => {
  let redirectUrl = "";
  const redirect = (url: string) => {
    redirectUrl = url;
    const err = new Error("NEXT_REDIRECT") as any;
    err.digest = `NEXT_REDIRECT;replace;${url};307;`;
    throw err;
  };

  let maybeSingle: any = { data: null, error: null };
  let signInError: any = null;
  let validCode = false;
  let normalizeEmailImpl = (v: any) => String(v ?? "").trim().toLowerCase();

  t.mock.module("next/navigation", {
    namedExports: { redirect },
  });

  t.mock.module("@/lib/supabase/admin", {
    namedExports: {
      createSupabaseAdminClient: () => ({
        from: () => ({
          select: () => ({
            eq: () => ({
              maybeSingle: async () => maybeSingle,
            }),
          }),
        }),
        auth: {
          admin: {
            listUsers: async () => ({ data: { users: [] }, error: null }),
            createUser: async () => ({ error: null }),
            updateUserById: async () => ({ error: null }),
          },
        },
      }),
    },
  });

  t.mock.module("@/lib/supabase/server", {
    namedExports: {
      createSupabaseServerClient: async () => ({
        auth: {
          signInWithPassword: async () => ({ error: signInError }),
        },
      }),
    },
  });

  t.mock.module("@/lib/access-code", {
    namedExports: {
      normalizeEmail: (...args: any[]) => normalizeEmailImpl(...args),
      normalizeAccessCode: (v: any) => String(v ?? "").trim().toLowerCase(),
      verifyAccessCode: () => validCode,
      rotateAccessCode: () => Promise.resolve("new-code"),
    },
  });

  const { login } = await import("../app/login/actions");

  /* ── missing email ──────────────────────────────────────────────── */
  await t.test("missing email", async () => {
    const prev = normalizeEmailImpl;
    normalizeEmailImpl = () => "";
    redirectUrl = "";

    const fd = new FormData();
    fd.append("email", "");
    fd.append("access_code", "123");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("missing_email"));
    } finally {
      normalizeEmailImpl = prev;
    }
  });

  /* ── missing access code ────────────────────────────────────────── */
  await t.test("missing access code", async () => {
    redirectUrl = "";
    const fd = new FormData();
    fd.append("email", "test@whub.fr");
    fd.append("access_code", "");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("missing_code"));
    }
  });

  /* ── not whitelisted ────────────────────────────────────────────── */
  await t.test("not whitelisted", async () => {
    redirectUrl = "";
    maybeSingle = { data: null, error: null };
    const fd = new FormData();
    fd.append("email", "unknown@whub.fr");
    fd.append("access_code", "abc");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("not_allowed"));
    }
  });

  /* ── bad access code ────────────────────────────────────────────── */
  await t.test("bad access code", async () => {
    redirectUrl = "";
    maybeSingle = { data: { email: "user@whub.fr" }, error: null };
    validCode = false;
    const fd = new FormData();
    fd.append("email", "user@whub.fr");
    fd.append("access_code", "wrong");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("bad_code"));
    }
  });

  /* ── whitelist query error ──────────────────────────────────────── */
  await t.test("whitelist query error", async () => {
    redirectUrl = "";
    maybeSingle = { data: null, error: { message: "DB down" } };
    const fd = new FormData();
    fd.append("email", "user@whub.fr");
    fd.append("access_code", "some");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("config"));
    }
  });

  /* ── successful login ───────────────────────────────────────────── */
  await t.test("successful login", async () => {
    redirectUrl = "";
    maybeSingle = { data: { email: "user@whub.fr" }, error: null };
    validCode = true;
    signInError = null;
    const fd = new FormData();
    fd.append("email", "user@whub.fr");
    fd.append("access_code", "user");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("/dashboard"));
    }
  });

  /* ── Supabase sign-in failure ───────────────────────────────────── */
  await t.test("Supabase sign-in failure", async () => {
    redirectUrl = "";
    maybeSingle = { data: { email: "user@whub.fr" }, error: null };
    validCode = true;
    signInError = { code: "invalid_credentials", name: "AuthApiError" };
    const fd = new FormData();
    fd.append("email", "user@whub.fr");
    fd.append("access_code", "user");

    try {
      await login(fd);
      assert.fail("expected redirect");
    } catch (e: any) {
      assert.ok(e.digest?.includes("invalid_credentials"));
    }
  });
});

/* ═════════════════════════════════════════════════════════════════════
   2. Login page — error messages & UI states
   ═════════════════════════════════════════════════════════════════════ */

async function renderLoginPage(
  t: any,
  searchParams: Record<string, string>
) {
  t.mock.module("@/components/Brand", {
    namedExports: {
      Eyebrow: () => null,
      WhubMark: () => null,
    },
  });

  t.mock.module("@/app/login/actions", {
    namedExports: {
      login: () => {},
    },
  });

  const { default: LoginPage } = await import("../app/login/page");
  const element = await LoginPage({
    searchParams: Promise.resolve(searchParams),
  });
  return renderToString(element);
}

test("LoginPage shows correct error message for bad_code", async (t) => {
  const html = await renderLoginPage(t, { error: "bad_code" });
  assert.ok(html.includes("Code d\u2019acc\u00e8s incorrect pour cette adresse email."));
});

test("LoginPage shows correct error message for not_allowed", async (t) => {
  const html = await renderLoginPage(t, { error: "not_allowed" });
  assert.ok(
    html.includes("Cette adresse n\u2019est pas encore whitelist\u00e9e dans Supabase.")
  );
});

test("LoginPage shows correct error message for auth_callback", async (t) => {
  const html = await renderLoginPage(t, { error: "auth_callback" });
  assert.ok(
    html.includes("Session invalide ou expir\u00e9e. Reconnecte-toi.")
  );
});

test("LoginPage shows correct error message for missing_email", async (t) => {
  const html = await renderLoginPage(t, { error: "missing_email" });
  assert.ok(html.includes("Entre une adresse email valide."));
});

test("LoginPage shows correct error message for missing_code", async (t) => {
  const html = await renderLoginPage(t, { error: "missing_code" });
  assert.ok(html.includes("Entre ton code d\u2019acc\u00e8s."));
});

test("LoginPage shows correct error message for config", async (t) => {
  const html = await renderLoginPage(t, { error: "config" });
  assert.ok(
    html.includes("Configuration Supabase incompl\u00e8te. Connexion impossible.")
  );
});

test("LoginPage shows generic auth fallback for unknown error", async (t) => {
  const html = await renderLoginPage(t, { error: "some_random_error" });
  assert.ok(html.includes("Erreur Supabase : some_random_error"));
});

test("LoginPage does not show error block when no error query param", async (t) => {
  const html = await renderLoginPage(t, {});
  assert.ok(!html.includes("bg-red-50"));
});

test("LoginPage shows success block when sent=1", async (t) => {
  const html = await renderLoginPage(t, { sent: "1" });
  assert.ok(html.includes("Connexion valid\u00e9e."));
});
