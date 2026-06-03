import { redirect } from "next/navigation";
import { AppShell, Panel } from "@/components/AppShell";
import { Eyebrow } from "@/components/Brand";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import NewRequestForm from "./NewRequestForm";

type NewRequestPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function NewRequestPage({ searchParams }: NewRequestPageProps) {
  const params = await searchParams;
  const rawError = Array.isArray(params?.error) ? params?.error[0] : params?.error;

  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <AppShell active="new">
      <div className="grid gap-8 lg:grid-cols-[0.95fr_1.05fr]">
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <Eyebrow>Nouvelle demande</Eyebrow>
          <h1 className="mt-3 text-5xl font-black leading-[0.95] tracking-[-0.06em] sm:text-6xl">Un seul flux: CV source + message libre.</h1>
          <p className="mt-5 text-base leading-7 text-ink/58">
            Même logique que Telegram Hermes: tu déposes un PDF source, tu ajoutes une consigne, et le worker repart sur le même workflow W hub.
          </p>

          <div className="mt-8 space-y-3">
            {[
              "Fidélité au CV source",
              "Coordonnées retirées",
              "Prénom uniquement côté client",
              "Redirection vers le statut"
            ].map((item) => (
              <div key={item} className="flex items-center gap-3 rounded-2xl border border-white/75 bg-white/62 px-4 py-3 shadow-sm backdrop-blur">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-whub/10 text-xs font-black text-whub">✓</span>
                <span className="text-sm font-bold text-ink/64">{item}</span>
              </div>
            ))}
          </div>

          <div className="mt-8 rounded-[1.75rem] border border-whub/12 bg-white/70 p-5 shadow-soft">
            <p className="text-xs font-black uppercase tracking-[0.32em] text-whub/70">Consigne utile</p>
            <p className="mt-3 text-sm font-semibold leading-6 text-ink/58">
              N’écris une exception que si elle est explicite: mission cible, stack à mettre en avant, ou version plus courte autorisée.
            </p>
          </div>
        </aside>

        <Panel className="p-6 sm:p-8">
          <NewRequestForm initialError={rawError ?? null} />
        </Panel>
      </div>
    </AppShell>
  );
}
