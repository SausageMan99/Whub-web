import { login } from "./actions";
import { Eyebrow, WhubMark } from "@/components/Brand";

type LoginPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const errorMessages: Record<string, string> = {
  missing_email: "Entre une adresse email valide.",
  missing_code: "Entre ton code d’accès.",
  bad_code: "Code d’accès incorrect pour cette adresse email.",
  not_allowed: "Cette adresse n’est pas encore whitelistée dans Supabase.",
  config: "Configuration Supabase incomplète. Connexion impossible.",
  auth: "Supabase a refusé la connexion.",
  auth_callback: "Session invalide ou expirée. Reconnecte-toi.",
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const sent = params?.sent === "1";
  const rawError = Array.isArray(params?.error) ? params?.error[0] : params?.error;
  const errorMessage = rawError ? errorMessages[rawError] || `Erreur Supabase : ${rawError}` : null;

  return (
    <main className="relative min-h-screen overflow-hidden bg-porcelain text-ink">
      <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-whub/16 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-16rem] left-[-12rem] h-[34rem] w-[34rem] rounded-full bg-lilac blur-3xl" />

      <div className="relative mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-5 py-8 sm:px-8 lg:grid-cols-[0.9fr_1.1fr]">
        <section className="hidden lg:block">
          <WhubMark />
          <Eyebrow>Accès whitelisté</Eyebrow>
          <h1 className="mt-5 max-w-xl text-6xl font-black leading-[0.94] tracking-[-0.065em]">
            Un accès propre pour produire vite, sans exposer les consultants.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-ink/60">
            Connexion par code interne, stockage privé Supabase et demandes suivies côté W hub.
          </p>
        </section>

        <section className="mx-auto w-full max-w-md rounded-[2.25rem] border border-white/75 bg-white/82 p-6 shadow-soft backdrop-blur-xl sm:p-8">
          <div className="lg:hidden">
            <WhubMark />
          </div>
          <div className="mt-10 lg:mt-0">
            <p className="text-xs font-black uppercase tracking-[0.28em] text-whub">Connexion sécurisée</p>
            <h2 className="mt-4 text-4xl font-black tracking-[-0.055em]">W hub CV Factory</h2>
            <p className="mt-3 text-sm leading-6 text-ink/55">Entre ton email autorisé et ton code d’accès : première lettre du prénom + nom de famille, en minuscules. Exemple : cdubosq.</p>
          </div>

          <form action={login} className="mt-8 space-y-5">
            <label className="block">
              <span className="text-sm font-black text-ink">Email W hub</span>
              <input name="email" type="email" required className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="prenom@whub.fr" />
            </label>
            <label className="block">
              <span className="text-sm font-black text-ink">Code d’accès</span>
              <input name="access_code" type="text" required autoCapitalize="none" autoCorrect="off" className="mt-2 w-full rounded-2xl border border-ink/10 bg-porcelain/70 px-4 py-3.5 text-sm font-semibold placeholder:text-ink/28" placeholder="cdubosq" />
            </label>
            <button className="w-full rounded-2xl bg-whub px-5 py-4 font-black text-white shadow-violet transition hover:-translate-y-0.5">
              Se connecter
            </button>
          </form>

          {sent ? (
            <p className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-black leading-5 text-emerald-700">
              Connexion validée.
            </p>
          ) : null}

          {errorMessage ? (
            <p className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-black leading-5 text-red-700">
              {errorMessage}
            </p>
          ) : null}

          <p className="mt-6 rounded-2xl bg-whub/7 px-4 py-3 text-xs font-semibold leading-5 text-whub">
            Accès réservé aux utilisateurs whitelistés. Le code est le format interne : première lettre du prénom + nom de famille.
          </p>
        </section>
      </div>
    </main>
  );
}
