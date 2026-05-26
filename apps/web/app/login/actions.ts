"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function login(formData: FormData) {
  const email = String(formData.get("email") || "").trim().toLowerCase();
  const supabase = await createSupabaseServerClient();
  const { data: allowed } = await supabase.from("allowed_users").select("email").eq("email", email).maybeSingle();
  if (!allowed) redirect("/login?error=not_allowed");
  await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: `${process.env.NEXT_PUBLIC_APP_URL}/dashboard` } });
  redirect("/login?sent=1");
}
