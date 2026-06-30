import { AppShell } from "@/components/AppShell";
import NewRequestForm from "./NewRequestForm";

type NewRequestPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function NewRequestPage({ searchParams }: NewRequestPageProps) {
  const params = await searchParams;
  const rawError = Array.isArray(params?.error) ? params?.error[0] : params?.error;

  return (
    <AppShell active="new">
      <section className="mx-auto max-w-3xl py-8 sm:py-14">
        <div className="reveal-up mb-8 text-center">
          <p className="text-xs font-black uppercase tracking-[0.30em] text-whub/70">W hub CV Factory</p>
          <h1 className="mt-4 text-4xl font-semibold leading-[1.02] tracking-[-0.055em] text-ink sm:text-6xl">
            Dépose un CV. Ajoute une consigne. Récupère une version client.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base font-medium leading-7 text-ink/52">
            Un flux simple pour transformer un CV source en PDF W hub anonymisé, prêt à relire et à envoyer.
          </p>
        </div>

        <div className="reveal-up reveal-delay-1">
          <NewRequestForm initialError={rawError ?? null} />
        </div>

        <p className="reveal-up reveal-delay-2 mt-5 text-center text-xs font-semibold text-ink/40">
          Coordonnées retirées · Prénom uniquement · Même chaîne de génération que Telegram
        </p>
      </section>
    </AppShell>
  );
}
