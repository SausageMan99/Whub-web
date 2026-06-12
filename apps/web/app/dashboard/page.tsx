import Link from "next/link";
import { AppShell, Panel } from "@/components/AppShell";
import { Eyebrow } from "@/components/Brand";
import { createSupabaseAdminClient } from "@/lib/supabase/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { CvProgressBar } from "@/components/CvProgressBar";
import { buildContentPreservingBadgeIndex, type CvEvent } from "@/lib/content-preserving-diagnostics";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const admin = createSupabaseAdminClient();

  const { data: requests } = await admin
    .from("cv_requests")
    .select("id,title,candidate_first_name,status,priority,created_at")
    .order("created_at", { ascending: false })
    .limit(50);

  const items = requests ?? [];
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
  const ready = items.filter((r) => r.status === "ready").length;
  const inProgress = items.filter((r) => ["submitted", "processing", "revision_requested"].includes(r.status)).length;
  const urgent = items.filter((r) => r.priority === "urgent").length;

  return (
    <AppShell active="dashboard">
      <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div>
          <Eyebrow>Dashboard</Eyebrow>
          <h1 className="mt-3 text-5xl font-black tracking-[-0.06em] sm:text-6xl">Demandes CV</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-ink/58">
            Suivi des CV candidats à transformer en profils W hub anonymisés, chartés et prêts à envoyer aux clients.
          </p>
        </div>
        <Link className="inline-flex items-center justify-center rounded-2xl bg-whub px-6 py-4 font-black text-white shadow-violet transition hover:-translate-y-0.5" href="/requests/new">
          + Nouveau CV
        </Link>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {[
          ["Total demandes", items.length, "Base de travail"],
          ["En cours", inProgress, "À traiter / relancer"],
          ["Prêts", ready, "Validés côté QA"]
        ].map(([label, value, helper]) => (
          <Panel key={label as string} className="p-6">
            <p className="text-sm font-black text-ink/45">{label}</p>
            <p className="mt-3 text-5xl font-black tracking-[-0.06em] text-ink">{value}</p>
            <p className="mt-2 text-sm font-semibold text-ink/42">{helper}</p>
          </Panel>
        ))}
      </div>

      {urgent > 0 && (
        <div className="mt-5 rounded-2xl border border-whub/15 bg-whub/8 px-5 py-4 text-sm font-bold text-whub">
          {urgent} demande{urgent > 1 ? "s" : ""} urgente{urgent > 1 ? "s" : ""} à prioriser.
        </div>
      )}

      <Panel className="mt-8 overflow-hidden">
        <div className="flex items-center justify-between border-b border-ink/6 px-6 py-5">
          <div>
            <h2 className="text-lg font-black tracking-[-0.02em]">File de production</h2>
            <p className="mt-1 text-sm text-ink/45">Les 50 dernières demandes créées.</p>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-whub/10 text-2xl font-black text-whub">W</div>
            <h3 className="mt-5 text-2xl font-black tracking-[-0.04em]">Aucune demande pour l’instant</h3>
            <p className="mt-2 text-sm text-ink/52">Dépose un premier CV pour lancer la chaîne W hub.</p>
            <Link className="mt-6 inline-flex rounded-2xl bg-ink px-5 py-3 font-black text-white" href="/requests/new">Créer une demande</Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-ink/[0.025] text-[11px] uppercase tracking-[0.24em] text-ink/38">
                <tr>
                  <th className="px-6 py-4 font-black">Mission</th>
                  <th className="px-4 py-4 font-black">Prénom</th>
                  <th className="px-4 py-4 font-black">Statut</th>
                  <th className="px-4 py-4 font-black">Avancement</th>
                  <th className="px-4 py-4 font-black">Priorité</th>
                  <th className="px-4 py-4 font-black">Date</th>
                  <th className="px-6 py-4"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const cpBadge = cpBadges[r.id];
                  const cpBadgeClass = cpBadge?.tone === 'warning'
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-emerald-200 bg-emerald-50 text-emerald-800';
                  return (
                  <tr key={r.id} className="border-t border-ink/6 transition hover:bg-whub/[0.025]">
                    <td className="px-6 py-5">
                      <p className="font-black text-ink">{r.title || "Sans titre"}</p>
                      <p className="mt-1 text-xs font-semibold text-ink/38">ID {r.id.slice(0, 8)}</p>
                      {cpBadge?.present && cpBadge.label && (
                        <span className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-[11px] font-black uppercase tracking-[0.12em] ${cpBadgeClass}`}>
                          {cpBadge.label}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-5 font-bold text-ink/70">{r.candidate_first_name || "—"}</td>
                    <td className="px-4 py-5"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-5"><CvProgressBar status={r.status} compact /></td>
                    <td className="px-4 py-5"><span className="rounded-full bg-ink/[0.04] px-3 py-1 text-xs font-black uppercase text-ink/55">{r.priority}</span></td>
                    <td className="px-4 py-5 font-semibold text-ink/45">{new Date(r.created_at).toLocaleDateString("fr-FR")}</td>
                    <td className="px-6 py-5 text-right"><Link className="font-black text-whub" href={`/requests/${r.id}`}>Ouvrir</Link></td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
