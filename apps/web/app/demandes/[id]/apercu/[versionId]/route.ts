import { createSupabaseAdminClient } from "@/lib/supabase/admin";

// Sert le PDF d'une version depuis le même domaine, pour l'aperçu dans la page.
// Le téléchargement reste sur /requests/[id]/download/[versionId].
export async function GET(_: Request, { params }: { params: Promise<{ id: string; versionId: string }> }) {
  const { id, versionId } = await params;
  const admin = createSupabaseAdminClient();

  const { data: version, error } = await admin
    .from("cv_versions")
    .select("id,final_pdf_path")
    .eq("id", versionId)
    .eq("request_id", id)
    .maybeSingle();
  if (error || !version?.final_pdf_path) return new Response("PDF non disponible", { status: 404 });

  const { data: file, error: downloadError } = await admin.storage.from("cv-finals").download(version.final_pdf_path);
  if (downloadError || !file) return new Response("PDF non disponible", { status: 404 });

  return new Response(file, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
      "Cache-Control": "private, max-age=300",
      "X-Robots-Tag": "noindex",
    },
  });
}
