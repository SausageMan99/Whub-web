"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";

export type CreateRequestResult =
  | { ok: true; requestId: string }
  | { ok: false; error: "profile_failed" | "request_failed" };

function logCreateRequestFailure(stage: string, requestId: string | null, error?: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "unknown");
  const code = typeof error === "object" && error !== null && "code" in error ? String((error as { code?: unknown }).code) : undefined;
  console.error("createRequest failed", {
    stage,
    requestId,
    message,
    code,
  });
}

async function assertUser(admin: ReturnType<typeof createSupabaseAdminClient>, email: string) {
  const { data: allowed, error } = await admin
    .from("allowed_users")
    .select("email,role")
    .eq("email", email)
    .maybeSingle();
  if (error) throw new Error("config");
  if (!allowed) throw new Error("not_allowed");
  return allowed.role ?? "member";
}

export async function prepareUpload({ fileName, fileType }: { fileName: string; fileType: string }) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) redirect("/login");

  const admin = createSupabaseAdminClient();
  const email = user.email.toLowerCase();
  await assertUser(admin, email);

  const requestId = crypto.randomUUID();
  const safeName = fileName.replace(/[^a-zA-Z0-9_.-]/g, "_");
  const sourcePath = `${requestId}/source/${safeName || "source.pdf"}`;

  const { data, error } = await admin.storage
    .from("cv-sources")
    .createSignedUploadUrl(sourcePath);

  if (error) {
    console.error("Signed upload URL failed", error);
    redirect("/requests/new?error=upload_failed");
  }

  return { requestId, sourcePath, signedUrl: data.signedUrl };
}

export async function createRequest(formData: FormData): Promise<CreateRequestResult> {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) redirect("/login");

  let requestId: string | null = null;

  try {
    const admin = createSupabaseAdminClient();
    const email = user.email.toLowerCase();
    const role = await assertUser(admin, email);

    requestId = String(formData.get("request_id") || "");
    const sourcePath = String(formData.get("source_path") || "");
    const fileName = String(formData.get("source_file_name") || "");
    const fileSize = Number(formData.get("source_file_size") || 0);
    const fileMime = String(formData.get("source_file_mime") || "application/pdf");

    if (!requestId || !sourcePath) {
      logCreateRequestFailure("missing_upload_metadata", requestId || null);
      return { ok: false, error: "request_failed" };
    }

    const { error: profileError } = await admin.from("profiles").upsert({
      id: user.id,
      email,
      role,
    });

    if (profileError) {
      logCreateRequestFailure("profile_upsert", requestId, profileError);
      return { ok: false, error: "profile_failed" };
    }

    const { error } = await admin.from("cv_requests").insert({
      id: requestId,
      created_by: user.id,
      title: String(formData.get("title") || "").trim(),
      candidate_first_name: String(formData.get("candidate_first_name") || "").trim(),
      source_file_path: sourcePath,
      source_file_name: fileName,
      source_file_mime: fileMime,
      source_file_size: fileSize,
      instructions: String(formData.get("instructions") || "").trim(),
      priority: String(formData.get("priority") || "normal"),
      status: "submitted",
    });

    if (error) {
      logCreateRequestFailure("cv_requests_insert", requestId, error);
      return { ok: false, error: "request_failed" };
    }

    return { ok: true, requestId };
  } catch (error) {
    logCreateRequestFailure("unexpected_exception", requestId || null, error);
    return { ok: false, error: "request_failed" };
  }
}
