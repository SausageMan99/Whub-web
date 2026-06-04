import test from "node:test";
import assert from "node:assert/strict";

/* ═════════════════════════════════════════════════════════════════════
   Minimal Next.js mocks for middleware
   ═════════════════════════════════════════════════════════════════════ */

class MockCookieJar {
  private store = new Map<string, { value: string; options?: Record<string, unknown> }>();

  getAll() {
    return Array.from(this.store.entries()).map(([name, { value }]) => ({ name, value }));
  }

  set(name: string, value: string, options?: Record<string, unknown>) {
    this.store.set(name, { value, options });
  }

  getSetCookieHeader(): string[] {
    return Array.from(this.store.entries()).map(([name, { value, options }]) => {
      let cookie = `${name}=${value}`;
      if (options) {
        for (const [k, v] of Object.entries(options)) {
          if (v === true) cookie += `; ${k}`;
          else if (v !== false && v !== undefined) cookie += `; ${k}=${v}`;
        }
      }
      return cookie;
    });
  }
}

class MockNextRequest {
  url: string;
  nextUrl: { pathname: string };
  cookies = new MockCookieJar();

  constructor(init: { url: string }) {
    this.url = init.url;
    this.nextUrl = { pathname: new URL(init.url).pathname };
  }
}

class MockNextResponse {
  status = 200;
  headers = new Headers();
  cookies = new MockCookieJar();

  static next({ request }: { request: MockNextRequest }) {
    return new MockNextResponse();
  }

  static redirect(url: string | URL) {
    const res = new MockNextResponse();
    res.status = 307;
    res.headers.set("location", String(url));
    return res;
  }
}

/* ═════════════════════════════════════════════════════════════════════
   middleware tests — single import so module cache is shared and
   mutable mocks control each subtest.
   ═════════════════════════════════════════════════════════════════════ */

test("middleware — all branches", async (t) => {
  let getUserResult: any = { data: { user: null } };
  let setAllInput: any[] = [];

  t.mock.module("next/server", {
    namedExports: {
      NextResponse: MockNextResponse,
      NextRequest: MockNextRequest,
    },
  });

  t.mock.module("@supabase/ssr", {
    namedExports: {
      createServerClient: (
        _url: string,
        _key: string,
        opts: any
      ) => {
        // simulate cookie setAll side-effect
        if (opts.cookies.setAll) {
          opts.cookies.setAll(setAllInput);
        }
        return {
          auth: {
            getUser: async () => getUserResult,
          },
        };
      },
    },
  });

  const { middleware } = await import("../middleware");

  await t.test("redirects unauthenticated /dashboard to /login with redirect param", async () => {
    getUserResult = { data: { user: null } };
    setAllInput = [];
    const req = new MockNextRequest({ url: "http://example.com/dashboard" });
    const res = await middleware(req as any);
    assert.equal(res.status, 307);
    assert.equal((res as any).headers.get("location"), "http://example.com/login?redirect=%2Fdashboard");
  });

  await t.test("redirects unauthenticated /requests/abc to /login with redirect param", async () => {
    getUserResult = { data: { user: null } };
    setAllInput = [];
    const req = new MockNextRequest({ url: "http://example.com/requests/abc-123?tab=files" });
    const res = await middleware(req as any);
    assert.equal(res.status, 307);
    assert.equal(
      (res as any).headers.get("location"),
      "http://example.com/login?redirect=%2Frequests%2Fabc-123%3Ftab%3Dfiles"
    );
  });

  await t.test("passes through authenticated /dashboard", async () => {
    getUserResult = { data: { user: { id: "user-1", email: "user@whub.fr" } } };
    setAllInput = [];
    const req = new MockNextRequest({ url: "http://example.com/dashboard" });
    const res = await middleware(req as any);
    assert.equal(res.status, 200);
  });

  await t.test("passes through unauthenticated /login", async () => {
    getUserResult = { data: { user: null } };
    setAllInput = [];
    const req = new MockNextRequest({ url: "http://example.com/login" });
    const res = await middleware(req as any);
    assert.equal(res.status, 200);
  });

  await t.test("writes refresh cookies to response", async () => {
    getUserResult = { data: { user: { id: "u1", email: "u@whub.fr" } } };
    setAllInput = [
      { name: "sb-access-token", value: "new-access", options: { path: "/", httpOnly: true } as any },
      { name: "sb-refresh-token", value: "new-refresh", options: { path: "/", maxAge: 604800 } as any },
    ];
    const req = new MockNextRequest({ url: "http://example.com/dashboard" });
    const res = await middleware(req as any);

    assert.equal(res.status, 200);
    const cookies = (res as any).cookies.getSetCookieHeader();
    const combined = cookies.join("; ");
    assert.ok(combined.includes("sb-access-token=new-access"), "expected access token");
    assert.ok(combined.includes("sb-refresh-token=new-refresh"), "expected refresh token");
    assert.ok(combined.includes("httpOnly"), "expected httpOnly");
    assert.ok(combined.includes("maxAge=604800") || combined.includes("max-age=604800"), "expected maxAge");
  });

  await t.test("does not block static assets", async () => {
    getUserResult = { data: { user: null } };
    setAllInput = [];
    const req = new MockNextRequest({ url: "http://example.com/_next/static/chunks/main.js" });
    const res = await middleware(req as any);
    assert.equal(res.status, 200);
  });
});
