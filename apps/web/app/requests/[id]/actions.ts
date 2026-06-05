"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";

export async function addComment(formData: FormData) {
  const body = String(formData.get("body") || "").trim();
  if (!body) return;

  const requestId = String(formData.get("request_id") || "").trim();
  if (!requestId) throw new Error("Missing request id");

  const admin = createSupabaseAdminClient();
  const { data: request, error: lookupError } = await admin
    .from("cv_requests")
    .select("id,current_version_id,status")
    .eq("id", requestId)
    .maybeSingle();

  if (lookupError || !request) throw new Error("Request not found");

  const versionId = request.current_version_id ?? null;
  const { error: commentError } = await admin.from("cv_comments").insert({
    request_id: requestId,
    version_id: versionId,
    body,
    comment_type: "revision",
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
    },
  });

  if (eventError) throw new Error("Revision event failed");

  revalidatePath(`/requests/${requestId}`);
  revalidatePath("/dashboard");
}

export async function retryRequest(formData: FormData) {
  const requestId = String(formData.get("request_id") || "").trim();
  if (!requestId) throw new Error("Missing request id");

  const admin = createSupabaseAdminClient();
  const { data: request, error: lookupError } = await admin
    .from("cv_requests")
    .select("id,status")
    .eq("id", requestId)
    .maybeSingle();

  if (lookupError || !request) throw new Error("Request not found");
  if (request.status !== "failed") throw new Error("Request is not retryable");

  const now = new Date().toISOString();
  const { data: updatedRows, error } = await admin
    .from("cv_requests")
    .update({
      status: "submitted",
      last_error: null,
      error_category: null,
      worker_locked_at: null,
      worker_locked_by: null,
      worker_attempts: 0,
      submitted_at: now,
      started_at: null,
      updated_at: now,
    })
    .eq("id", requestId)
    .in("status", ["failed"])
    .select("id");

  if (error || !updatedRows || updatedRows.length !== 1) throw new Error("Retry failed");

  const { error: eventError } = await admin.from("cv_events").insert({
    request_id: requestId,
    event_type: "retry_requested",
    payload: { previous_status: request.status },
  });

  if (eventError) throw new Error("Retry event failed");

  revalidatePath(`/requests/${requestId}`);
  revalidatePath("/dashboard");
}
