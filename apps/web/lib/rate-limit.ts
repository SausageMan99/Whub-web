type RateLimitOptions = {
  action: string;
  limit: number;
  windowMs: number;
  ip?: string | null;
};

type RateLimitResult = {
  allowed: boolean;
  limit: number;
  remaining: number;
  resetAt: number;
  key: string;
};

type HeadersLike = {
  get(name: string): string | null;
};

const buckets = new Map<string, number[]>();

function isTestRuntime() {
  return (
    process.env.NODE_ENV === "test" ||
    process.env.npm_lifecycle_event === "test" ||
    process.argv.some((arg) => arg.includes("--test"))
  );
}

function parseForwardedFor(value: string | null) {
  return value?.split(",")[0]?.trim() || null;
}

async function readHeaders(): Promise<HeadersLike | null> {
  try {
    const mod = (await import("next/headers")) as { headers?: () => HeadersLike | Promise<HeadersLike> };
    if (typeof mod.headers !== "function") return null;
    return await mod.headers();
  } catch {
    return null;
  }
}

export async function getClientIp() {
  const requestHeaders = await readHeaders();
  if (!requestHeaders) return null;

  return (
    parseForwardedFor(requestHeaders.get("x-forwarded-for")) ||
    requestHeaders.get("x-real-ip")?.trim() ||
    requestHeaders.get("cf-connecting-ip")?.trim() ||
    "unknown"
  );
}

function cleanup(now: number, windowMs: number) {
  for (const [key, timestamps] of buckets.entries()) {
    const recent = timestamps.filter((timestamp) => now - timestamp < windowMs);
    if (recent.length === 0) buckets.delete(key);
    else buckets.set(key, recent);
  }
}

async function checkUpstashRateLimit(key: string, limit: number, windowMs: number, now: number): Promise<RateLimitResult | null> {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;

  try {
    const windowStart = now - windowMs;
    const member = `${now}-${crypto.randomUUID()}`;
    const redisKey = `rate-limit:${key}`;
    const response = await fetch(`${url.replace(/\/$/, "")}/pipeline`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify([
        ["ZREMRANGEBYSCORE", redisKey, 0, windowStart],
        ["ZADD", redisKey, now, member],
        ["ZCARD", redisKey],
        ["PEXPIRE", redisKey, windowMs],
      ]),
    });

    if (!response.ok) return null;
    const pipeline = (await response.json()) as Array<{ result?: unknown }>;
    const count = Number(pipeline[2]?.result ?? 0);
    return {
      allowed: count <= limit,
      limit,
      remaining: Math.max(0, limit - count),
      resetAt: now + windowMs,
      key,
    };
  } catch (error) {
    console.error("Upstash rate limit failed; falling back to in-memory limiter", error);
    return null;
  }
}

function checkMemoryRateLimit(key: string, limit: number, windowMs: number, now: number): RateLimitResult {
  cleanup(now, windowMs);

  const windowStart = now - windowMs;
  const timestamps = (buckets.get(key) ?? []).filter((timestamp) => timestamp > windowStart);
  timestamps.push(now);
  buckets.set(key, timestamps);

  const oldest = timestamps[0] ?? now;
  return {
    allowed: timestamps.length <= limit,
    limit,
    remaining: Math.max(0, limit - timestamps.length),
    resetAt: oldest + windowMs,
    key,
  };
}

export async function checkRateLimit({ action, limit, windowMs, ip }: RateLimitOptions): Promise<RateLimitResult> {
  const clientIp = ip ?? (await getClientIp());
  const now = Date.now();

  if (!clientIp) {
    return { allowed: true, limit, remaining: limit, resetAt: now + windowMs, key: `${action}:missing-ip-bypass` };
  }

  if (isTestRuntime() && clientIp === "unknown") {
    return { allowed: true, limit, remaining: limit, resetAt: now + windowMs, key: `${action}:test-bypass` };
  }

  const key = `${action}:${clientIp || "unknown"}`;
  const upstashResult = await checkUpstashRateLimit(key, limit, windowMs, now);
  if (upstashResult) return upstashResult;

  return checkMemoryRateLimit(key, limit, windowMs, now);
}

export function resetRateLimitForTests() {
  buckets.clear();
}
