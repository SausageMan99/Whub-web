"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function createRequest(formData: FormData) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const file = formData.get("file") as File;
  const requestId = crypto.randomUUID();
  const safeName = file.name.replace(/[^a-zA-Z0-9_.-]/g, "_");
  const sourcePath = `${requestId}/source/${safeName}`;
  await supabase.storage.from("cv-sources").upload(sourcePath, file, { contentType: file.type, upsert: false });

  await supabase.from("profiles").upsert({ id: user.id, email: user.email, role: "member" });
  const { error } = await supabase.from("cv_requests").insert({
    id: requestId,
    created_by: user.id,
    title: String(formData.get("title") || ""),
    candidate_first_name: String(formData.get("candidate_first_name") || ""),
    source_file_path: sourcePath,
    source_file_name: file.name,
    source_file_mime: file.type,
    source_file_size: file.size,
    instructions: String(formData.get("instructions") || ""),
    priority: String(formData.get("priority") || "normal"),
    status: "submitted"
  });
  if (error) throw new Error(error.message);
  redirect(`/requests/${requestId}`);
}
