"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { checkRateLimit } from "@/lib/rate-limit";
import { cvJobProducer, CVJobData } from "@/lib/queue";
import type { CreateRequestResult } from "@/app/requests/new/actions";

const PORTAL_ORIGIN = "web_portal";

const ALLOWED_REVISION_CATEGORIES = new Set([
  "layout_sparse_page",
  "missing_content",
  "fidelity_issue",
  "skills_classification",
  "contact_leak",
  "other",
]);

function normalizeRevisionCategory(value: FormDataEntryValue | null): string {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) return "other";
  return ALLOWED_REVISION_CATEGORIES.has(raw) ? raw : "other";
}

export async function addComment(formData: FormData) {
  const rateLimit = await checkRateLimit({
    action: "comment",
    limit: 20,
    windowMs: 60_000,
  });
  if (!rateLimit.allowed) throw new Error("rate_limited");

  const body = String(formData.get("body") || "").trim();
  if (!body) return;

  const requestId = String(formData.get("request_id") || "").trim();
  if (!requestId) throw new Error("Missing request id");

  const category = normalizeRevisionCategory(formData.get("category"));
  const metadata: Record<string, unknown> = { category };

  const admin = createSupabaseAdminClient();
  const { data: request, error: lookupError } = await admin
    .from("cv_requests")
    .select("id,current_version_id,status")
    .eq("id", requestId)
    .maybeSingle();

  if (lookupError || !request) throw new Error("Request not found");

  const versionId = request.current_version_id ?? null;
  const cvComments = admin.from("cv_comments");

  if (typeof cvComments.select === "function") {
    const duplicateCutoff = new Date(Date.now() - 10_000).toISOString();
    let duplicateQuery = cvComments
      .select("id")
      .eq("request_id", requestId)
      .eq("comment_type", "revision")
      .eq("resolved", false)
      .eq("body", body)
      .gte("created_at", duplicateCutoff);
    duplicateQuery = versionId
      ? duplicateQuery.eq("version_id", versionId)
      : duplicateQuery.is("version_id", null);

    const { data: duplicate } = await duplicateQuery.maybeSingle();
    if (duplicate) {
      revalidatePath(`/requests/${requestId}`);
      revalidatePath("/dashboard");
      return;
    }
  }

  const { error: commentError } = await admin.from("cv_comments").insert({
    request_id: requestId,
    version_id: versionId,
    body,
    comment_type: "revision",
    metadata,
  });
  if (commentError) throw new Error("Revision comment failed");

  const now = new Date().toISOString();
  const { error: requestError } = await admin
    .from("cv_requests")
    .update({
      status: "revision_requested",
      worker_locked_at: null,
      worker_locked_by: null,
      updated_at: now,
    })
    .eq("id", requestId);
  if (requestError) throw new Error("Revision request update failed");

  const { data: currentVersion, error: versionLookupError } = versionId
    ? await admin
        .from("cv_versions")
        .select("id,version_number,qa_status")
        .eq("id", versionId)
        .maybeSingle()
    : { data: null, error: null };

  if (versionLookupError) throw new Error("Version lookup failed");

  const { error: eventError } = await admin.from("cv_events").insert({
    request_id: requestId,
    event_type: "revision_requested",
    payload: {
      source_reused: true,
      version_id: versionId,
      version_number: currentVersion?.version_number ?? null,
      qa_status: currentVersion?.qa_status ?? null,
      from_status: request.status,
      feedback_category: category,
    },
  });

  if (eventError) throw new Error("Revision event failed");

  revalidatePath(`/requests/${requestId}`);
  revalidatePath("/dashboard");
}

export async function retryRequest(formData: FormData): Promise<CreateRequestResult> {
  const rateLimit = await checkRateLimit({
    action: "retry",
    limit: 10,
    windowMs: 60_000,
  });
  if (!rateLimit.allowed) throw new Error("rate_limited");

  const requestId = String(formData.get("request_id") || "").trim();
  if (!requestId) throw new Error("Missing request id");

  const admin = createSupabaseAdminClient();
  const { data: request, error: lookupError } = await admin
    .from("cv_requests")
    .select("id,status")
    .eq("id", requestId)
    .maybeSingle();

  if (lookupError || !request) throw new Error("Request not found");
  if (!["failed", "dead_letter", "needs_human_review"].includes(request.status)) {
    throw new Error("Request is not retryable");
  }

  // Use the unlock_job RPC to reset the request
  const { data: unlockedRequest, error: unlockError } = await admin.rpc("unlock_job", {
    p_request_id: requestId,
  });

  if (unlockError || !unlockedRequest) throw new Error("Failed to unlock request");

  // Enqueue to BullMQ for queue-based worker processing
  let enqueueError: string | undefined;
  try {
    const { data: requestData } = await admin
      .from("cv_requests")
      .select(
        "id,candidate_first_name,instructions,priority,source_file_path,source_file_name,source_file_mime,source_file_size,created_by,submitted_at",
      )
      .eq("id", requestId)
      .maybeSingle();

    if (requestData) {
      const jobData: CVJobData = {
        requestId: requestData.id,
        candidateFirstName: requestData.candidate_first_name,
        instructions: requestData.instructions || "",
        priority: (requestData.priority as "urgent" | "high" | "normal") || "normal",
        sourceFilePath: requestData.source_file_path,
        sourceFileName: requestData.source_file_name,
        sourceFileMime: requestData.source_file_mime,
        sourceFileSize: requestData.source_file_size,
        createdBy: requestData.created_by || PORTAL_ORIGIN,
        submittedAt: requestData.submitted_at || new Date().toISOString(),
        enqueuedAt: new Date().toISOString(),
        attempt: 0,
      };
      await cvJobProducer.enqueue(jobData);
    }
  } catch (queueError) {
    enqueueError = queueError instanceof Error ? queueError.message : String(queueError ?? "queue enqueue failed");
    console.error("Failed to enqueue retry job to BullMQ", { requestId, error: queueError });
  }

  // The unlock_job RPC already logs the event, but we can add a retry_requested event too
  const { error: eventError } = await admin.from("cv_events").insert({
    request_id: requestId,
    event_type: "retry_requested",
    payload: {
      previous_status: request.status,
      ...(enqueueError ? { enqueue_error: enqueueError } : {}),
    },
  });

  if (eventError) throw new Error("Retry event failed");

  revalidatePath(`/requests/${requestId}`);
  revalidatePath("/dashboard");
  if (enqueueError) {
    console.warn("BullMQ retry enqueue unavailable; unlocked request remains submitted for polling worker fallback", {
      requestId,
      enqueueError,
    });
  }
  return { ok: true, requestId };
}
