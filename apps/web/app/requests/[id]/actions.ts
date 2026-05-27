"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";

async function requireAllowedUser() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) throw new Error("Not authenticated");

  const admin = createSupabaseAdminClient();
  const { data: allowed, error } = await admin
    .from("allowed_users")
    .select("email,role")
    .eq("email", user.email.toLowerCase())
    .maybeSingle();

  if (error || !allowed) throw new Error("Not allowed");
  return { admin, user, role: allowed.role ?? "member" };
}

export async function addComment(formData: FormData) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) throw new Error("Not authenticated");
  const requestId = String(formData.get("request_id"));
  const body = String(formData.get("body") || "").trim();
  if (!body) return;
  await supabase.from("cv_comments").insert({ request_id: requestId, author_id: user.id, body, comment_type: "revision" });
  await supabase.from("cv_requests").update({ status: "revision_requested", updated_at: new Date().toISOString() }).eq("id", requestId);
  revalidatePath(`/requests/${requestId}`);
}

export async function retryRequest(formData: FormData) {
  const requestId = String(formData.get("request_id") || "").trim();
  if (!requestId) throw new Error("Missing request id");

  const { admin, user, role } = await requireAllowedUser();
  const { data: request, error: lookupError } = await admin
    .from("cv_requests")
    .select("id,status,created_by")
    .eq("id", requestId)
    .maybeSingle();

  if (lookupError || !request) throw new Error("Request not found");
  if (!["failed", "qa_failed"].includes(request.status)) throw new Error("Request is not retryable");
  if (request.created_by !== user.id && role !== "admin") throw new Error("Forbidden");

  const now = new Date().toISOString();
  const { data: updatedRows, error } = await admin
    .from("cv_requests")
    .update({
      status: "submitted",
      last_error: null,
      worker_locked_at: null,
      worker_locked_by: null,
      worker_attempts: 0,
      submitted_at: now,
      started_at: null,
      updated_at: now,
    })
    .eq("id", requestId)
    .in("status", ["failed", "qa_failed"])
    .select("id");

  if (error || !updatedRows || updatedRows.length !== 1) throw new Error("Retry failed");

  const { error: eventError } = await admin.from("cv_events").insert({
    request_id: requestId,
    actor_id: user.id,
    actor_type: "user",
    event_type: "retry_requested",
    payload: { previous_status: "failed_or_qa_failed" },
  });

  if (eventError) throw new Error("Retry event failed");

  revalidatePath(`/requests/${requestId}`);
  revalidatePath("/dashboard");
}
