import { createSupabaseServerClient } from "@/lib/supabase/server";
import { StatusBadge } from "@/components/StatusBadge";
import { addComment } from "./actions";

export default async function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createSupabaseServerClient();
  const { data: request } = await supabase.from("cv_requests").select("*").eq("id", id).single();
  const { data: versions } = await supabase.from("cv_versions").select("*").eq("request_id", id).order("version_number", { ascending: false });
  const { data: comments } = await supabase.from("cv_comments").select("*").eq("request_id", id).order("created_at", { ascending: true });
  if (!request) return <main className="p-10">Demande introuvable.</main>;
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-start justify-between gap-6"><div><h1 className="text-3xl font-bold">{request.title || "Demande CV"}</h1><p className="mt-2 text-black/60">Prénom: {request.candidate_first_name || "—"}</p></div><StatusBadge status={request.status} /></div>
      <section className="mt-8 rounded-2xl bg-white p-6 shadow-sm"><h2 className="font-bold">Consignes</h2><p className="mt-3 whitespace-pre-wrap text-sm text-black/70">{request.instructions || "Aucune consigne."}</p></section>
      <section className="mt-6 rounded-2xl bg-white p-6 shadow-sm"><h2 className="font-bold">Versions</h2><div className="mt-4 space-y-3">{(versions ?? []).map(v => <div key={v.id} className="flex items-center justify-between rounded-xl border border-black/10 p-4"><span>V{v.version_number} — QA {v.qa_status}</span><span className="text-sm text-black/50">{v.final_pdf_path || "PDF non disponible"}</span></div>)}{!versions?.length && <p className="text-sm text-black/50">Aucune version générée pour l’instant.</p>}</div></section>
      <section className="mt-6 rounded-2xl bg-white p-6 shadow-sm"><h2 className="font-bold">Commentaires / modifications</h2><div className="mt-4 space-y-3">{(comments ?? []).map(c => <p key={c.id} className="rounded-xl bg-black/[0.03] p-3 text-sm">{c.body}</p>)}</div><form action={addComment} className="mt-5 space-y-3"><input type="hidden" name="request_id" value={id} /><textarea name="body" rows={4} className="w-full rounded-lg border border-black/10 px-3 py-2" placeholder="Demande de modification pour V2/V3..." /><button className="rounded-lg bg-whub px-4 py-2 font-semibold text-white">Demander une modification</button></form></section>
    </main>
  );
}
