"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseServerClient } from "@/lib/supabase/server";

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
