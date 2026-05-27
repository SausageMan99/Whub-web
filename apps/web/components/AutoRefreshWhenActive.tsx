"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const ACTIVE_STATUSES = new Set(["submitted", "processing", "revision_requested"]);

export function AutoRefreshWhenActive({ status }: { status: string }) {
  const router = useRouter();

  useEffect(() => {
    if (!ACTIVE_STATUSES.has(status)) return;
    const timer = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [router, status]);

  return null;
}
