export function normalizeEmail(value: FormDataEntryValue | string | null | undefined) {
  return String(value ?? "").trim().toLowerCase();
}

export function normalizeAccessCode(value: FormDataEntryValue | string | null | undefined) {
  return String(value ?? "").trim().toLowerCase();
}

export function expectedAccessCodeFromEmail(email: string) {
  const normalizedEmail = normalizeEmail(email);
  const [localPart] = normalizedEmail.split("@");
  return localPart.replace(/[^a-z0-9]/g, "");
}

export function isValidAccessCodeForEmail(email: string, code: string) {
  const expected = expectedAccessCodeFromEmail(email);
  return Boolean(expected) && normalizeAccessCode(code) === expected;
}
