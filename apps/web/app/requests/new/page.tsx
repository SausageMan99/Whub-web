import { redirect } from "next/navigation";
import { AppShell, Panel } from "@/components/AppShell";
import { Eyebrow } from "@/components/Brand";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createRequest } from "./actions";

type NewRequestPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const errorMessages: Record<string, string> = {
  file_required: "Ajoute un PDF source avant de créer la demande.",
  pdf_required: "Le fichier doit être un PDF.",
  upload_failed: "Upload Supabase refusé. Réessaie ou renvoie-moi le PDF.",
  profile_failed: "Création du profil interne impossible.",
  request_failed: "Création de la demande impossible.",
};

export default async function NewRequestPage({ searchParams }: NewRequestPageProps) {
  const params = await searchParams;
  const rawError = Array.isArray(params?.error) ? params?.error[0] : params?.error;
  const errorMessage = rawError ? errorMessages[rawError] || `Erreur : ${rawError}` : null;

  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <AppShell active="new">
      <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr]">
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <Eyebrow>Nouvelle demande</Eyebrow>
          <h1 className="mt-3 text-5xl font-black leading-[0.95] tracking-[-0.06em] sm:text-6xl">Transformer un CV en version W hub.</h1>
          <p className="mt-5 text-base leading-7 text-ink/58">
            Dépose le PDF source, ajoute les consignes utiles au contexte client, puis laisse le worker produire une version anonymisée et chartée.
          </p>

          <div className="mt-8 space-y-3">
            {[
              "Prénom uniquement côté client",
              "Coordonnées candidat supprimées",
              "Charte W hub + QA bloquante",
              "Historique de versions conservé"
            ].map((item) => (
              <div key={item} className="flex items-center gap-3 rounded-2xl border border-white/75 bg-white/62 px-4 py-3 shadow-sm backdrop-blur">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-whub/10 text-xs font-black text-whub">✓</span>
                <span className="text-sm font-bold text-ink/64">{item}</span>
              </div>
            ))}
          </div>
        </aside>

        <Panel className="p-6 sm:p-8">
          <form action={createRequest} className="space-y-6">
            {errorMessage ? (
              <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-black leading-5 text-red-700">
                {errorMessage}
              </p>
            ) : null}

            <div className="grid gap-5 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="text-sm font-black text-ink">Titre interne</span>
                <input name="title" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="CV Architecte Cloud Azure" />
              </label>
              <label className="block">
                <span className="text-sm font-black text-ink">Prénom affiché</span>
                <input name="candidate_first_name" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="Habib" />
              </label>
              <label className="block">
                <span className="text-sm font-black text-ink">Priorité</span>
                <select name="priority" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-black text-ink">
                  <option value="normal">Normal</option>
                  <option value="high">Prioritaire</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
            </div>

            <label className="block rounded-[1.75rem] border border-dashed border-whub/28 bg-whub/[0.035] p-5">
              <span className="text-sm font-black text-ink">CV source PDF</span>
              <input name="file" type="file" accept="application/pdf" required className="mt-3 w-full rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-semibold text-ink/65 file:mr-4 file:rounded-xl file:border-0 file:bg-ink file:px-4 file:py-2 file:text-sm file:font-black file:text-white" />
              <span className="mt-3 block text-xs font-semibold text-ink/45">PDF uniquement. Les coordonnées seront retirées du rendu client.</span>
            </label>

            <label className="block">
              <span className="text-sm font-black text-ink">Consignes de génération</span>
              <textarea name="instructions" rows={7} className="mt-2 w-full resize-none rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold leading-6 placeholder:text-ink/28" placeholder="Titre souhaité, stack à mettre en avant, mission client, éléments à retirer, urgence commerciale..." />
            </label>

            <div className="flex flex-col items-start justify-between gap-4 border-t border-ink/8 pt-6 sm:flex-row sm:items-center">
              <p className="max-w-md text-xs font-semibold leading-5 text-ink/42">La demande sera visible dans le dashboard. Le worker prendra ensuite le relais pour générer la version PDF W hub.</p>
              <button className="w-full rounded-2xl bg-whub px-6 py-4 font-black text-white shadow-violet transition hover:-translate-y-0.5 sm:w-auto">Créer la demande</button>
            </div>
          </form>
        </Panel>
      </div>
    </AppShell>
  );
}
