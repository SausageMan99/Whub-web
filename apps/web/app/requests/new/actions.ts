"use server";

import { redirect } from "next/navigation";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { checkRateLimit } from "@/lib/rate-limit";
import { cvJobProducer, CVJobData } from "@/lib/queue";

export type CreateRequestResult =
  | { ok: true; requestId: string }
  | { ok: false; error: "request_failed" | "candidate_first_name_required" | "queue_unavailable"; queueError?: string };

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

const PORTAL_ORIGIN = "web_portal";

function buildDefaultTitle(_fileName: string) {
  return "CV source";
}

const PORTAL_WORKFLOW = "telegram_whub_cv_generation";
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const PDF_MAGIC_HEADER = Buffer.from("%PDF-");

async function hasPdfMagicHeader(file: File) {
  const header = Buffer.from(await file.slice(0, PDF_MAGIC_HEADER.length).arrayBuffer());
  return header.equals(PDF_MAGIC_HEADER);
}

export async function prepareUpload({ file, fileName, fileType }: { file: File; fileName: string; fileType: string }) {
  const rateLimit = await checkRateLimit({ action: "upload", limit: 10, windowMs: 60_000 });
  if (!rateLimit.allowed) redirect("/requests/new?error=rate_limited");

  if (file.size > MAX_UPLOAD_BYTES) redirect("/requests/new?error=file_too_large");
  if (fileType !== "application/pdf" || file.type !== "application/pdf" || !(await hasPdfMagicHeader(file))) {
    redirect("/requests/new?error=pdf_required");
  }

  const admin = createSupabaseAdminClient();

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
  let requestId: string | null = null;

  try {
    const admin = createSupabaseAdminClient();

    requestId = String(formData.get("request_id") || "");
    const sourcePath = String(formData.get("source_path") || "");
    const fileName = String(formData.get("source_file_name") || "");
    const fileSize = Number(formData.get("source_file_size") || 0);
    const fileMime = String(formData.get("source_file_mime") || "application/pdf");
    const title = String(formData.get("title") || "").trim() || buildDefaultTitle(fileName);
    const candidateFirstName = String(formData.get("candidate_first_name") || "").trim();
    const priority = String(formData.get("priority") || "normal").trim() || "normal";
    const instructions = String(formData.get("instructions") || "").trim();

    if (!requestId || !sourcePath) {
      logCreateRequestFailure("missing_upload_metadata", requestId || null);
      return { ok: false, error: "request_failed" };
    }

    if (!candidateFirstName) {
      logCreateRequestFailure("missing_candidate_first_name", requestId || null);
      return { ok: false, error: "candidate_first_name_required" };
    }

    const { error } = await admin.from("cv_requests").insert({
      id: requestId,
      title,
      candidate_first_name: candidateFirstName,
      origin: PORTAL_ORIGIN,
      workflow: PORTAL_WORKFLOW,
      source_file_path: sourcePath,
      source_file_name: fileName,
      source_file_mime: fileMime,
      source_file_size: fileSize,
      instructions,
      priority,
      status: "submitted",
    });

    if (error) {
      logCreateRequestFailure("cv_requests_insert", requestId, error);
      return { ok: false, error: "request_failed" };
    }

    // Enqueue to BullMQ for queue-based worker processing
    try {
      const jobData: CVJobData = {
        requestId,
        candidateFirstName: candidateFirstName || null,
        instructions,
        priority: (priority as "urgent" | "high" | "normal") || "normal",
        sourceFilePath: sourcePath,
        sourceFileName: fileName,
        sourceFileMime: fileMime,
        sourceFileSize: fileSize,
        createdBy: PORTAL_ORIGIN,
        submittedAt: new Date().toISOString(),
        enqueuedAt: new Date().toISOString(),
        attempt: 0,
      };
      await cvJobProducer.enqueue(jobData);
    } catch (queueError) {
      console.warn("BullMQ enqueue unavailable; request remains submitted for polling worker fallback", { requestId, error: queueError });
    }

    return { ok: true, requestId };
  } catch (error) {
    logCreateRequestFailure("unexpected_exception", requestId || null, error);
    return { ok: false, error: "request_failed" };
  }
}
