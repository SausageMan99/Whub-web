import Link from "next/link";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { StatusBadge } from "@/components/StatusBadge";

export default async function DashboardPage() {
  const supabase = await createSupabaseServerClient();
  const { data: requests } = await supabase.from("cv_requests").select("id,title,candidate_first_name,status,priority,created_at").order("created_at", { ascending: false }).limit(50);
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-whub">W hub</p>
          <h1 className="mt-2 text-3xl font-bold">Demandes CV</h1>
        </div>
        <Link className="rounded-xl bg-whub px-5 py-3 font-semibold text-white" href="/requests/new">Nouveau CV</Link>
      </div>
      <div className="mt-8 overflow-hidden rounded-2xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-black/[0.03] text-xs uppercase tracking-wide text-black/50"><tr><th className="p-4">Titre</th><th>Prénom</th><th>Statut</th><th>Priorité</th><th>Date</th><th></th></tr></thead>
          <tbody>
            {(requests ?? []).map((r) => <tr key={r.id} className="border-t border-black/5"><td className="p-4 font-medium">{r.title || "Sans titre"}</td><td>{r.candidate_first_name || "—"}</td><td><StatusBadge status={r.status} /></td><td>{r.priority}</td><td>{new Date(r.created_at).toLocaleDateString("fr-FR")}</td><td><Link className="font-semibold text-whub" href={`/requests/${r.id}`}>Ouvrir</Link></td></tr>)}
          </tbody>
        </table>
      </div>
    </main>
  );
}
