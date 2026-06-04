import { createSupabaseAdminClient } from "@/lib/supabase/admin";

export function normalizeEmail(value: FormDataEntryValue | string | null | undefined) {
  return String(value ?? "").trim().toLowerCase();
}

export function normalizeAccessCode(value: FormDataEntryValue | string | null | undefined) {
  return String(value ?? "").trim().toLowerCase();
}

/**
 * Verify an access code against the bcrypt hash stored in allowed_users.
 * Looks up the stored hash for the normalized email, then uses the Postgres
 * verify_bcrypt RPC to compare the plaintext code with pgcrypto's crypt().
 *
 * This replaces the old deterministic expectedAccessCodeFromEmail() which
 * derived the code from the email local part — a security vulnerability.
 */
export async function verifyAccessCode(email: string, code: string): Promise<boolean> {
  const normalizedEmail = normalizeEmail(email);
  const normalizedCode = normalizeAccessCode(code);

  if (!normalizedEmail || !normalizedCode) {
    return false;
  }

  try {
    const admin = createSupabaseAdminClient();
    const { data: allowedUser, error: allowedUserError } = await admin
      .from("allowed_users")
      .select("access_code_hash")
      .eq("email", normalizedEmail)
      .maybeSingle();

    if (allowedUserError) {
      console.error("verifyAccessCode hash lookup failed", allowedUserError);
      return false;
    }

    const passwordHash = allowedUser?.access_code_hash;
    if (!passwordHash) {
      return false;
    }

    const { data, error } = await admin.rpc("verify_bcrypt", {
      plain_text: normalizedCode,
      password_hash: passwordHash,
    });

    if (error) {
      console.error("verifyAccessCode RPC failed", error);
      return false;
    }

    return data === true;
  } catch (err) {
    console.error("verifyAccessCode threw", err);
    return false;
  }
}

/**
 * Generate a new random access code, bcrypt-hash it into the database,
 * and return the plaintext code (which must be shown to an admin/user once).
 *
 * Returns null on failure.
 */
export async function rotateAccessCode(email: string): Promise<string | null> {
  const normalizedEmail = normalizeEmail(email);

  if (!normalizedEmail) {
    return null;
  }

  try {
    const admin = createSupabaseAdminClient();
    const { data, error } = await admin.rpc("rotate_access_code", {
      email: normalizedEmail,
    });

    if (error) {
      console.error("rotateAccessCode RPC failed", error);
      return null;
    }

    return data ?? null;
  } catch (err) {
    console.error("rotateAccessCode threw", err);
    return null;
  }
}