import { AppShell, Panel } from "@/components/AppShell";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { AutoRefreshWhenActive } from "@/components/AutoRefreshWhenActive";
import { RevisionComposer } from "@/components/RevisionComposer";
import { ProgressTimeline } from "@/components/ProgressTimeline";
import { retryRequest } from "./actions";
import {
  draftReadyTitle,
  hardFailureCopy,
  isHardFailureStatus,
  normalizeDraftWarnings,
  normalizeQualitySummary,
  safeRetryCopy,
} from "@/lib/request-detail-ui";
import { extractContentPreservingDiagnostics, type CvEvent } from "@/lib/content-preserving-diagnostics";
import { ContentPreservingStatus } from "@/components/content-preserving-status";

export const dynamic = "force-dynamic";

export default async function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const admin = createSupabaseAdminClient();

  const { data: request } = await admin.from("cv_requests").select("*").eq("id", id).single();
  const { data: versions } = await admin.from("cv_versions").select("*").eq("request_id", id).order("version_number", { ascending: false });
  const { data: comments } = await admin.from("cv_comments").select("*").eq("request_id", id).order("created_at", { ascending: true });
  const { data: events } = await admin
    .from("cv_events")
    .select("event_type, metadata, created_at")
    .eq("request_id", id)
    .order("created_at", { ascending: true });

  if (!request) {
    return (
      <AppShell active="detail">
        <Panel className="p-10 text-center">
          <h1 className="text-3xl font-semibold tracking-[-0.04em]">Demande introuvable</h1>
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
  const cpDiagnostics = extractContentPreservingDiagnostics((events ?? []) as CvEvent[]);
  const displayName = request.candidate_first_name || request.title || "Demande CV";
  const currentVersion = latestVersion;

  async function retryRequestAction(formData: FormData) {
    "use server";
    await retryRequest(formData);
  }

  return (
    <AppShell active="detail">
      <AutoRefreshWhenActive status={request.status} />

      <header className="reveal-up grid gap-5 lg:grid-cols-[1fr_auto] lg:items-start">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.30em] text-whub/70">Demande CV</p>
          <h1 className="mt-3 text-4xl font-semibold leading-[1.02] tracking-[-0.055em] sm:text-6xl">{displayName}</h1>
          <p className="mt-3 max-w-2xl text-sm font-medium leading-6 text-ink/48">
            {request.source_file_name || "CV source"} · demande créée pour une version client W hub.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 lg:justify-end">
          <StatusBadge status={request.status} events={eventTypes} />
          {retryBlock && (
            <form action={retryRequestAction}>
              <input type="hidden" name="request_id" value={id} />
              <button className="rounded-2xl bg-ink px-4 py-2.5 text-sm font-black text-white transition hover:-translate-y-0.5">
                {retryBlock.label}
              </button>
            </form>
          )}
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-6">
          <Panel className="reveal-up reveal-delay-1 p-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-[-0.03em]">Suivi de génération</h2>
                <p className="mt-1 text-sm font-medium text-ink/42">Actualisation automatique pendant la production du CV.</p>
              </div>
              <StatusBadge status={request.status} events={eventTypes} />
            </div>
            <div className="mt-6">
              <ProgressTimeline status={request.status} events={eventTypes} />
            </div>
          </Panel>

          <Panel className="reveal-up reveal-delay-2 p-6">
            <h2 className="text-xl font-semibold tracking-[-0.03em]">Consigne initiale</h2>
            <p className="mt-4 whitespace-pre-wrap rounded-2xl bg-mist/70 p-4 text-sm font-medium leading-6 text-ink/62">{request.instructions || "Aucune consigne."}</p>
            <div className="mt-4 rounded-2xl border border-ink/8 bg-white p-4">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-ink/32">Fichier source</p>
              <p className="mt-1 truncate text-sm font-semibold text-ink">{request.source_file_name || "CV source"}</p>
              <p className="mt-1 text-xs font-medium text-ink/40">même source pour V2/V3.</p>
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel className="reveal-up reveal-delay-1 p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-whub/70">Version actuelle</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">
                  {currentVersion ? `Version ${currentVersion.version_number}` : "Aucune version générée"}
                </h2>
                <p className="mt-2 text-sm font-medium leading-6 text-ink/48">
                  {currentVersion ? "Le PDF généré apparaît ici dès qu’une version est disponible." : "La version client sera ajoutée ici après génération."}
                </p>
              </div>
              {currentVersion?.qa_status && <span className="rounded-full bg-whub/8 px-3 py-1.5 text-xs font-black uppercase text-whub">QA {currentVersion.qa_status}</span>}
            </div>

            {draftTitle && (
              <div className="mt-5 rounded-2xl border border-amber-200/80 bg-amber-50/80 p-4">
                <p className="text-sm font-semibold text-amber-900">{draftTitle}</p>
                <p className="mt-1 text-sm font-medium text-ink/55">Le PDF est sûr à relire. La correction ci-dessous créera la prochaine version.</p>
                {draftWarnings.length ? (
                  <ul className="mt-3 space-y-2">
                    {draftWarnings.map((warning, index) => (
                      <li key={`${warning}-${index}`} className="rounded-xl bg-white/75 px-3 py-2 text-sm font-medium leading-6 text-ink/70">{warning}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}

            {hardFailure && (
              <div className="mt-5 rounded-2xl border border-red-200/80 bg-red-50/80 p-4">
                <p className="text-sm font-semibold text-red-900">{hardFailure.title}</p>
                <p className="mt-1 text-sm font-medium leading-6 text-ink/60">{hardFailure.body}</p>
                {hardFailure.action && (
                  <form action={hardFailure.action.href ?? retryRequestAction} className="mt-4">
                    <input type="hidden" name="request_id" value={id} />
                    <button type="submit" className="rounded-2xl bg-ink px-4 py-2.5 text-sm font-black text-white">
                      {hardFailure.action.label}
                    </button>
                  </form>
                )}
              </div>
            )}

            <div className="mt-5 space-y-3">
              {(versions ?? []).map((v) => (
                <div key={v.id} className="rounded-2xl border border-ink/8 bg-white p-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="font-semibold">Version {v.version_number}</p>
                    <span className="rounded-full bg-ink/[0.04] px-3 py-1 text-xs font-black uppercase text-ink/45">QA {v.qa_status}</span>
                  </div>
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="truncate text-xs font-medium text-ink/42">PDF W hub généré</p>
                    {v.final_pdf_path && canDownloadGeneratedPdf ? (
                      <a className="inline-flex shrink-0 items-center justify-center rounded-xl bg-whub px-4 py-2.5 text-xs font-black text-white transition duration-200 hover:-translate-y-0.5 hover:shadow-violet" href={`/requests/${id}/download/${v.id}`}>
                        {request.status === "draft_ready" ? "Télécharger le brouillon" : "Télécharger le PDF"}
                      </a>
                    ) : v.final_pdf_path ? (
                      <span className="inline-flex shrink-0 items-center justify-center rounded-xl bg-red-50 px-4 py-2 text-xs font-black text-red-800">PDF bloqué</span>
                    ) : null}
                  </div>
                </div>
              ))}
              {!versions?.length && <p className="rounded-2xl bg-mist/70 p-4 text-sm font-medium text-ink/45">Aucune version générée pour l’instant.</p>}
            </div>
          </Panel>

          <Panel className="reveal-up reveal-delay-2 p-6">
            <h2 className="text-xl font-semibold tracking-[-0.03em]">Commentaires / modifications</h2>
            <div className="mt-5 space-y-3">
              {(comments ?? []).map((c) => (
                <p key={c.id} className="rounded-2xl bg-mist/70 p-4 text-sm font-medium leading-6 text-ink/64">{c.body}</p>
              ))}
              {!comments?.length && <p className="text-sm font-medium text-ink/42">Aucun commentaire pour le moment.</p>}
            </div>
            <RevisionComposer requestId={id} nextVersionNumber={nextVersionNumber} category="other" />
          </Panel>
        </div>
      </div>

      {(qualitySummary || cpDiagnostics.present) && (
        <Panel className="reveal-up reveal-delay-3 mt-6 p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.24em] text-ink/35">Qualité CV</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">{qualitySummary?.sourceProfileLabel || "Diagnostics internes"}</h2>
              <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-ink/48">Synthèse redacted : aucun contact candidat ni extrait source brut n’est affiché.</p>
            </div>
            {qualitySummary && (
              <div className="shrink-0 rounded-2xl bg-whub/8 px-5 py-3 text-right">
                <p className="text-xs font-black uppercase text-whub/70">Score global</p>
                <p className="text-2xl font-black text-whub">{qualitySummary.scores.overall}/100</p>
              </div>
            )}
          </div>
          {qualitySummary && (
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl bg-mist/70 p-4"><p className="text-xs font-black uppercase text-ink/35">Extraction</p><p className="mt-1 text-xl font-semibold">{qualitySummary.scores.extraction}/100</p></div>
              <div className="rounded-2xl bg-mist/70 p-4"><p className="text-xs font-black uppercase text-ink/35">Fidélité</p><p className="mt-1 text-xl font-semibold">{qualitySummary.scores.fidelity}/100</p></div>
              <div className="rounded-2xl bg-mist/70 p-4"><p className="text-xs font-black uppercase text-ink/35">Mise en page</p><p className="mt-1 text-xl font-semibold">{qualitySummary.scores.layout}/100</p></div>
            </div>
          )}
          {qualitySummary?.metrics.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {qualitySummary.metrics.map((metric) => (
                <span key={metric} className="rounded-full bg-ink/[0.04] px-3 py-1 text-xs font-semibold text-ink/48">{metric}</span>
              ))}
            </div>
          ) : null}
          {qualitySummary?.warnings.length ? (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
              <p className="font-semibold text-ink">Points qualité détectés</p>
              <ul className="mt-2 space-y-1 text-sm font-medium text-ink/65">
                {qualitySummary.warnings.map((warning) => <li key={warning}>· {warning}</li>)}
              </ul>
            </div>
          ) : null}
          <div className="mt-5">
            <ContentPreservingStatus diagnostics={cpDiagnostics} />
          </div>
        </Panel>
      )}
    </AppShell>
  );
}
