"use server";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { expectedAccessCodeFromEmail, isValidAccessCodeForEmail, normalizeEmail } from "@/lib/access-code";

type AuthUserSummary = {
  id: string;
  email?: string;
};

async function findAuthUserByEmail(admin: ReturnType<typeof createSupabaseAdminClient>, email: string): Promise<AuthUserSummary | null> {
  let page = 1;
  while (page <= 10) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 100 });
    if (error) throw error;
    const user = data.users.find((item) => item.email?.toLowerCase() === email);
    if (user) return { id: user.id, email: user.email };
    if (data.users.length < 100) return null;
    page += 1;
  }
  return null;
}

async function ensurePasswordUser(admin: ReturnType<typeof createSupabaseAdminClient>, email: string, password: string) {
  const existingUser = await findAuthUserByEmail(admin, email);

  if (existingUser) {
    const { error } = await admin.auth.admin.updateUserById(existingUser.id, {
      password,
      email_confirm: true,
      user_metadata: { whub_access_code_login: true }
    });
    if (error) throw error;
    return;
  }

  const { error } = await admin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
    user_metadata: { whub_access_code_login: true }
  });
  if (error) throw error;
}

export async function login(formData: FormData) {
  const email = normalizeEmail(formData.get("email"));
  const accessCode = String(formData.get("access_code") || "").trim();

  if (!email) redirect("/login?error=missing_email");
  if (!accessCode) redirect("/login?error=missing_code");

  const admin = createSupabaseAdminClient();
  const { data: allowed, error: allowedError } = await admin
    .from("allowed_users")
    .select("email")
    .eq("email", email)
    .maybeSingle();

  if (allowedError) {
    console.error("Whitelist check failed", allowedError);
    redirect("/login?error=config");
  }

  if (!allowed) redirect("/login?error=not_allowed");
  if (!isValidAccessCodeForEmail(email, accessCode)) redirect("/login?error=bad_code");

  const password = expectedAccessCodeFromEmail(email);

  try {
    await ensurePasswordUser(admin, email, password);
  } catch (error) {
    console.error("Access-code user provisioning failed", error);
    redirect("/login?error=config");
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword({
    email,
    password
  });

  if (error) {
    console.error("Access-code sign-in failed", error);
    redirect(`/login?error=${encodeURIComponent(error.code || error.name || "auth")}`);
  }

  redirect("/dashboard");
}
