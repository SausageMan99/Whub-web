"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";

export async function createRequest(formData: FormData) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) redirect("/login");

  const admin = createSupabaseAdminClient();
  const email = user.email.toLowerCase();
  const { data: allowed, error: allowedError } = await admin
    .from("allowed_users")
    .select("email,role")
    .eq("email", email)
    .maybeSingle();

  if (allowedError || !allowed) {
    console.error("Create request blocked by whitelist", { email, allowedError });
    redirect("/login?error=not_allowed");
  }

  const file = formData.get("file") as File | null;
  if (!file || file.size === 0) redirect("/requests/new?error=file_required");
  if (file.type !== "application/pdf") redirect("/requests/new?error=pdf_required");

  const firstBytes = new Uint8Array(await file.arrayBuffer()).slice(0, 5);
  const magic = new TextDecoder().decode(firstBytes);
  if (!magic.startsWith("%PDF-")) redirect("/requests/new?error=pdf_required");

  const requestId = crypto.randomUUID();
  const safeName = file.name.replace(/[^a-zA-Z0-9_.-]/g, "_");
  const sourcePath = `${requestId}/source/${safeName || "source.pdf"}`;

  const { error: uploadError } = await admin.storage
    .from("cv-sources")
    .upload(sourcePath, file, { contentType: file.type, upsert: false });

  if (uploadError) {
    console.error("Source upload failed", uploadError);
    redirect("/requests/new?error=upload_failed");
  }

  const { error: profileError } = await admin.from("profiles").upsert({
    id: user.id,
    email,
    role: allowed.role ?? "member",
  });

  if (profileError) {
    console.error("Profile upsert failed", profileError);
    redirect("/requests/new?error=profile_failed");
  }

  const { error } = await admin.from("cv_requests").insert({
    id: requestId,
    created_by: user.id,
    title: String(formData.get("title") || "").trim(),
    candidate_first_name: String(formData.get("candidate_first_name") || "").trim(),
    source_file_path: sourcePath,
    source_file_name: file.name,
    source_file_mime: file.type,
    source_file_size: file.size,
    instructions: String(formData.get("instructions") || "").trim(),
    priority: String(formData.get("priority") || "normal"),
    status: "submitted"
  });

  if (error) {
    console.error("Request insert failed", error);
    redirect("/requests/new?error=request_failed");
  }

  redirect(`/requests/${requestId}`);
}
