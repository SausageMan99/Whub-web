import { AppShell, Panel } from "@/components/AppShell";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { CvProgressBar } from "@/components/CvProgressBar";
import { AutoRefreshWhenActive } from "@/components/AutoRefreshWhenActive";
import { addComment, retryRequest } from "./actions";
import {
  draftReadyTitle,
  hardFailureCopy,
  isHardFailureStatus,
  normalizeDraftWarnings,
  normalizeQualitySummary,
  safeRetryCopy,
} from "@/lib/request-detail-ui";

export const dynamic = "force-dynamic";

export default async function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const admin = createSupabaseAdminClient();

  const { data: request } = await admin.from("cv_requests").select("*").eq("id", id).single();
  const { data: versions } = await admin.from("cv_versions").select("*").eq("request_id", id).order("version_number", { ascending: false });
  const { data: comments } = await admin.from("cv_comments").select("*").eq("request_id", id).order("created_at", { ascending: true });
  const { data: events } = await admin.from("cv_events").select("event_type,created_at").eq("request_id", id).order("created_at", { ascending: true });

  if (!request) {
    return (
      <AppShell active="detail">
        <Panel className="p-10 text-center">
          <h1 className="text-3xl font-black tracking-[-0.04em]">Demande introuvable</h1>
          <p className="mt-2 text-ink/50">Cette demande n’existe pas ou n’est pas accessible.</p>
        </Panel>
      </AppShell>
    );
  }

  const eventTypes = (events ?? []).map((event) => event.event_type);
  const latestVersion = versions?.[0] ?? null;
  const nextVersionNumber = (latestVersion?.version_number ?? 0) + 1;
  const draftTitle = draftReadyTitle(request.status);
  const draftWarnings = draftTitle ? normalizeDraftWarnings(latestVersion?.qa_report) : [];
  const hardFailure = hardFailureCopy(request.status);
  const retryBlock = safeRetryCopy(request.status, request.candidate_first_name);
  const canDownloadGeneratedPdf = !isHardFailureStatus(request.status);
  const qualitySummary = normalizeQualitySummary(latestVersion?.qa_report);

  async function retryRequestAction(formData: FormData) {
    "use server";
    await retryRequest(formData);
  }

  return (
    <AppShell active="detail">
      <AutoRefreshWhenActive status={request.status} />
      <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.34em] text-whub">Demande CV</p>
          <h1 className="mt-3 max-w-4xl text-5xl font-black leading-[0.98] tracking-[-0.06em]">{request.title || "Demande CV"}</h1>
          <p className="mt-4 text-base font-semibold text-ink/50">Prénom candidat : <span className="text-ink">{request.candidate_first_name || "—"}</span></p>
        </div>
        <div className="flex flex-col items-start gap-3">
          <StatusBadge status={request.status} events={eventTypes} />
          {retryBlock && (
            <form action={retryRequestAction}>
              <input type="hidden" name="request_id" value={id} />
              <button className="rounded-2xl bg-ink px-5 py-3 text-sm font-black text-white shadow-sm transition hover:-translate-y-0.5">
                {retryBlock.label}
              </button>
            </form>
          )}
        </div>
      </div>

      <Panel className="mt-8 p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-xl font-black tracking-[-0.03em]">Avancement</h2>
            <p className="mt-1 text-sm font-semibold text-ink/42">Actualisation automatique toutes les 5 secondes pendant la génération.</p>
          </div>
          <StatusBadge status={request.status} events={eventTypes} />
        </div>
        <div className="mt-5">
          <CvProgressBar status={request.status} events={eventTypes} />
        </div>
      </Panel>

      {draftTitle && (
        <Panel className="mt-6 border-amber-200/80 bg-amber-50/80 p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs font-black uppercase tracking-[0.28em] text-amber-700">Brouillon téléchargeable</p>
              <h2 className="mt-2 text-2xl font-black tracking-[-0.04em] text-ink">{draftTitle}</h2>
              <p className="mt-2 text-sm font-semibold leading-6 text-ink/60">
                Le PDF est sûr à relire, et la correction ci-dessous recrée la prochaine version sans réuploader le CV source.
              </p>
            </div>
            {latestVersion?.final_pdf_path && canDownloadGeneratedPdf && (
              <a className="inline-flex shrink-0 items-center justify-center rounded-2xl bg-ink px-5 py-3 text-sm font-black text-white shadow-sm transition hover:-translate-y-0.5" href={`/requests/${id}/download/${latestVersion.id}`}>
                Télécharger le brouillon
              </a>
            )}
          </div>
          <div className="mt-5 rounded-2xl border border-amber-200 bg-white/75 p-4">
            <h3 className="font-black text-ink">Points qualité détectés</h3>
            {draftWarnings.length ? (
              <ul className="mt-3 space-y-2">
                {draftWarnings.map((warning, index) => (
                  <li key={`${warning}-${index}`} className="rounded-xl bg-amber-50 px-3 py-2 text-sm font-semibold leading-6 text-ink/70">{warning}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm font-semibold text-ink/50">Un point qualité de mise en page a été détecté. Indique la correction souhaitée ci-dessous.</p>
            )}
          </div>
          {retryBlock && (
            <p className="text-xs font-semibold text-ink/50">{retryBlock.hint}</p>
          )}
          <form action={addComment} className="mt-5 space-y-3 border-t border-amber-200 pt-5">
            <input type="hidden" name="request_id" value={id} />
            <label className="block text-sm font-black text-ink" htmlFor="draft-feedback">Correction post-génération — crée V{nextVersionNumber}</label>
            <textarea id="draft-feedback" name="body" rows={4} className="w-full resize-none rounded-2xl border border-amber-200 bg-white/80 px-4 py-3 text-sm font-semibold leading-6 placeholder:text-ink/28" placeholder={`Ex. V${nextVersionNumber} : aérer la page 2, garder toutes les expériences, réduire seulement le bloc compétences...`} />
            <button className="rounded-2xl bg-whub px-5 py-3 font-black text-white shadow-violet">Créer V{nextVersionNumber}</button>
          </form>
        </Panel>
      )}

      {hardFailure && (
        <Panel className="mt-6 border-red-200/80 bg-red-50/80 p-6">
          <p className="text-xs font-black uppercase tracking-[0.28em] text-red-700">Sortie bloquée</p>
          <h2 className="mt-2 text-2xl font-black tracking-[-0.04em] text-ink">{hardFailure.title}</h2>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-ink/60">{hardFailure.body}</p>
          {hardFailure.action && (
            <form action={hardFailure.action.href ?? retryRequestAction} className="mt-5">
              <input type="hidden" name="request_id" value={id} />
              <button
                type="submit"
                className="rounded-2xl bg-ink px-5 py-3 text-sm font-black text-white shadow-sm transition hover:-translate-y-0.5"
              >
                {hardFailure.action.label}
              </button>
            </form>
          )}
        </Panel>
      )}

      {qualitySummary && (
        <Panel className="mt-6 p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.28em] text-whub">Qualité CV</p>
              <h2 className="mt-2 text-2xl font-black tracking-[-0.04em] text-ink">{qualitySummary.sourceProfileLabel}</h2>
              <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-ink/50">Synthèse automatique redacted : aucun contact candidat ni extrait source n'est affiché.</p>
            </div>
            <div className="shrink-0 rounded-2xl bg-whub/10 px-6 py-4 text-right">
              <p className="text-xs font-black uppercase text-whub/70">Score global</p>
              <p className="text-3xl font-black text-whub">{qualitySummary.scores.overall}/100</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-porcelain/70 p-4">
              <p className="text-xs font-black uppercase text-ink/40">Extraction</p>
              <p className="mt-1 text-xl font-black">{qualitySummary.scores.extraction}/100</p>
            </div>
            <div className="rounded-2xl bg-porcelain/70 p-4">
              <p className="text-xs font-black uppercase text-ink/40">Fidélité</p>
              <p className="mt-1 text-xl font-black">{qualitySummary.scores.fidelity}/100</p>
            </div>
            <div className="rounded-2xl bg-porcelain/70 p-4">
              <p className="text-xs font-black uppercase text-ink/40">Mise en page</p>
              <p className="mt-1 text-xl font-black">{qualitySummary.scores.layout}/100</p>
            </div>
          </div>
          {qualitySummary.metrics.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {qualitySummary.metrics.map((metric) => (
                <span key={metric} className="rounded-full bg-ink/[0.04] px-3 py-1 text-xs font-black text-ink/50">{metric}</span>
              ))}
            </div>
          )}
          {qualitySummary.warnings.length > 0 && (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
              <p className="font-black text-ink">Points qualité détectés</p>
              <ul className="mt-2 space-y-1 text-sm font-semibold text-ink/65">
                {qualitySummary.warnings.map((warning) => (
                  <li key={warning}>· {warning}</li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-6">
          <Panel className="p-6">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-xl font-black tracking-[-0.03em]">Consignes</h2>
              <span className="rounded-full bg-ink/[0.04] px-3 py-1 text-xs font-black uppercase text-ink/45">{request.priority}</span>
            </div>
            <p className="mt-4 whitespace-pre-wrap rounded-2xl bg-porcelain/70 p-4 text-sm font-medium leading-6 text-ink/64">{request.instructions || "Aucune consigne."}</p>
          </Panel>

          <Panel className="p-6">
            <h2 className="text-xl font-black tracking-[-0.03em]">Fichier source</h2>
            <div className="mt-4 rounded-2xl border border-ink/8 bg-white p-4">
              <p className="font-black text-ink">{request.source_file_name || "CV source"}</p>
              <p className="mt-1 text-sm font-semibold text-ink/42">Stockage privé Supabase · {request.source_file_mime || "PDF"} · même source pour V2/V3</p>
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel className="p-6">
            <h2 className="text-xl font-black tracking-[-0.03em]">Versions générées</h2>
            <div className="mt-5 space-y-3">
              {(versions ?? []).map((v) => (
                <div key={v.id} className="rounded-2xl border border-ink/8 bg-white p-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="font-black">Version {v.version_number}</p>
                    <span className="rounded-full bg-whub/10 px-3 py-1 text-xs font-black uppercase text-whub">QA {v.qa_status}</span>
                  </div>
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="break-all text-xs font-semibold text-ink/42">{v.final_pdf_path || "PDF non disponible"}</p>
                    {v.final_pdf_path && canDownloadGeneratedPdf ? (
                      <a className="inline-flex shrink-0 items-center justify-center rounded-xl bg-ink px-4 py-2 text-xs font-black text-white" href={`/requests/${id}/download/${v.id}`}>
                        Télécharger
                      </a>
                    ) : v.final_pdf_path ? (
                      <span className="inline-flex shrink-0 items-center justify-center rounded-xl bg-red-100 px-4 py-2 text-xs font-black text-red-800">PDF bloqué</span>
                    ) : null}
                  </div>
                </div>
              ))}
              {!versions?.length && <p className="rounded-2xl bg-porcelain/70 p-4 text-sm font-semibold text-ink/45">Aucune version générée pour l’instant.</p>}
            </div>
          </Panel>

          <Panel className="p-6">
            <h2 className="text-xl font-black tracking-[-0.03em]">Commentaires / modifications</h2>
            <div className="mt-5 space-y-3">
              {(comments ?? []).map((c) => (
                <p key={c.id} className="rounded-2xl bg-porcelain/70 p-4 text-sm font-semibold leading-6 text-ink/64">{c.body}</p>
              ))}
              {!comments?.length && <p className="text-sm font-semibold text-ink/42">Aucun commentaire pour le moment.</p>}
            </div>
            <form action={addComment} className="mt-5 space-y-3 border-t border-ink/8 pt-5">
              <input type="hidden" name="request_id" value={id} />
              <textarea name="body" rows={4} className="w-full resize-none rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3 text-sm font-semibold leading-6 placeholder:text-ink/28" placeholder={`Demande de correction pour V${nextVersionNumber}...`} />
              <button className="rounded-2xl bg-whub px-5 py-3 font-black text-white shadow-violet">Créer V{nextVersionNumber}</button>
            </form>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
