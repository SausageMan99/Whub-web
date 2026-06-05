import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { buildCvDownloadFilename } from "@/lib/cv-ui";

export async function GET(_: Request, { params }: { params: Promise<{ id: string; versionId: string }> }) {
  const { id, versionId } = await params;
  const admin = createSupabaseAdminClient();

  const { data: version, error } = await admin
    .from("cv_versions")
    .select("id,request_id,version_number,final_pdf_path")
    .eq("id", versionId)
    .eq("request_id", id)
    .maybeSingle();

  if (error || !version?.final_pdf_path) {
    console.error("Download version lookup failed", { id, versionId, error });
    return new Response("PDF non disponible", { status: 404 });
  }

  const { data: request } = await admin
    .from("cv_requests")
    .select("candidate_first_name,title,source_file_name")
    .eq("id", id)
    .maybeSingle();

  const downloadName = buildCvDownloadFilename(
    request?.candidate_first_name || request?.title || request?.source_file_name,
    version.version_number
  );

  const { data: signed, error: signedError } = await admin.storage
    .from("cv-finals")
    .createSignedUrl(version.final_pdf_path, 60 * 5, {
      download: downloadName
    });

  if (signedError || !signed?.signedUrl) {
    console.error("Download signed URL failed", { id, versionId, signedError });
    return new Response("Impossible de générer le lien sécurisé", { status: 500 });
  }

  return Response.redirect(signed.signedUrl);
}