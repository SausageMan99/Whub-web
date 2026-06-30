import Link from "next/link";
import { AppShell, Panel } from "@/components/AppShell";
import { Eyebrow } from "@/components/Brand";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { CvProgressBar } from "@/components/CvProgressBar";
import { buildContentPreservingBadgeIndex, type CvEvent } from "@/lib/content-preserving-diagnostics";

export const dynamic = "force-dynamic";

type RequestRow = {
  id: string;
  title: string | null;
  candidate_first_name: string | null;
  source_file_name?: string | null;
  status: string;
  priority: string | null;
  created_at: string;
};

export default async function DashboardPage() {
  const admin = createSupabaseAdminClient();

  const { data: requests } = await admin
    .from("cv_requests")
    .select("id,title,candidate_first_name,source_file_name,status,priority,created_at")
    .order("created_at", { ascending: false })
    .limit(50);

  const items = (requests ?? []) as RequestRow[];
  const requestIds = items.map((request) => request.id);
  const { data: contentPreservingEvents } = requestIds.length > 0
    ? await admin
        .from("cv_events")
        .select("request_id,event_type,metadata,created_at")
        .in("request_id", requestIds)
        .like("event_type", "content_preserving_%")
        .order("created_at", { ascending: false })
    : { data: [] };
  const cpBadges = buildContentPreservingBadgeIndex((contentPreservingEvents ?? []) as CvEvent[]);
  const ready = items.filter((r) => ["ready", "draft_ready"].includes(r.status)).length;
  const inProgress = items.filter((r) => ["submitted", "processing", "revision_requested"].includes(r.status)).length;
  const urgent = items.filter((r) => r.priority === "urgent" || r.priority === "high").length;

  return (
    <AppShell active="dashboard">
      <div className="reveal-up flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div>
          <Eyebrow>Production</Eyebrow>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.055em] sm:text-6xl">File de production CV</h1>
          <p className="mt-4 max-w-2xl text-base font-medium leading-7 text-ink/52">
            Les demandes W hub en cours, prêtes ou à relire. Une inbox simple pour suivre la génération sans ouvrir un CRM.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-full border border-ink/8 bg-white px-3 py-1.5 text-xs font-semibold text-ink/52">{items.length} demandes</span>
            <span className="rounded-full border border-ink/8 bg-white px-3 py-1.5 text-xs font-semibold text-ink/52">{inProgress} en cours</span>
            <span className="rounded-full border border-ink/8 bg-white px-3 py-1.5 text-xs font-semibold text-ink/52">{ready} prêtes / brouillons</span>
            {urgent > 0 && <span className="rounded-full border border-whub/12 bg-whub/8 px-3 py-1.5 text-xs font-black text-whub">{urgent} prioritaires</span>}
          </div>
        </div>
        <Link className="inline-flex items-center justify-center rounded-2xl bg-whub px-5 py-3.5 text-sm font-black text-white shadow-violet transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_46px_rgba(112,1,245,0.28)]" href="/requests/new">
          Nouveau CV
        </Link>
      </div>

      <Panel className="reveal-up reveal-delay-1 mt-8 overflow-hidden">
        <div className="flex items-center justify-between border-b border-ink/8 px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-base font-semibold tracking-[-0.02em]">Demandes récentes</h2>
            <p className="mt-1 text-sm text-ink/42">Les 50 dernières créations.</p>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-whub/10 text-xl font-semibold text-whub">+</div>
            <h3 className="mt-5 text-2xl font-semibold tracking-[-0.04em]">Aucune demande pour l’instant</h3>
            <p className="mt-2 text-sm text-ink/50">Dépose un premier CV pour lancer la chaîne W hub.</p>
            <Link className="mt-6 inline-flex rounded-2xl bg-ink px-5 py-3 text-sm font-black text-white" href="/requests/new">Créer une demande</Link>
          </div>
        ) : (
          <div className="divide-y divide-ink/8">
            {items.map((r) => {
              const cpBadge = cpBadges[r.id];
              const cpBadgeClass = cpBadge?.tone === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-800'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800';
              const title = r.candidate_first_name || r.title || "Demande CV";
              const priority = r.priority === "urgent" || r.priority === "high" ? r.priority : null;
              return (
                <Link key={r.id} href={`/requests/${r.id}`} className="group grid gap-4 px-5 py-5 transition duration-200 hover:bg-mist/60 motion-safe:hover:translate-x-1 sm:grid-cols-[1fr_190px_160px_auto] sm:items-center sm:px-6">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-base font-semibold text-ink">{title}</p>
                      {priority && <span className="rounded-full bg-whub/8 px-2.5 py-1 text-[11px] font-black uppercase text-whub">{priority}</span>}
                    </div>
                    <p className="mt-1 truncate text-sm font-medium text-ink/42">{r.source_file_name || r.title || "CV source"}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink/30">ID {r.id.slice(0, 8)}</span>
                      {cpBadge?.present && cpBadge.label && (
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.10em] ${cpBadgeClass}`}>
                          {cpBadge.label}
                        </span>
                      )}
                    </div>
                  </div>
                  <StatusBadge status={r.status} />
                  <CvProgressBar status={r.status} compact />
                  <div className="flex items-center justify-between gap-4 sm:block sm:text-right">
                    <p className="text-sm font-medium text-ink/42">{new Date(r.created_at).toLocaleDateString("fr-FR")}</p>
                    <p className="mt-0 text-sm font-black text-whub transition duration-200 group-hover:translate-x-0.5 sm:mt-2">Ouvrir</p>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
