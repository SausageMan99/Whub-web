import Link from "next/link";
import { Eyebrow, WhubMark } from "@/components/Brand";

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-porcelain text-ink">
      <div className="pointer-events-none absolute -right-32 -top-32 h-[32rem] w-[32rem] rounded-full bg-whub/18 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-18rem] left-[-10rem] h-[38rem] w-[38rem] rounded-full bg-lilac blur-3xl" />
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between">
          <WhubMark />
          <Link className="rounded-full border border-ink/10 bg-white/70 px-5 py-2.5 text-sm font-bold text-ink shadow-soft backdrop-blur hover:border-whub/30" href="/login">
            Connexion
          </Link>
        </header>

        <section className="grid flex-1 items-center gap-12 py-16 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <Eyebrow>Portail interne W hub</Eyebrow>
            <h1 className="mt-5 max-w-4xl text-6xl font-black leading-[0.92] tracking-[-0.07em] text-ink sm:text-7xl lg:text-8xl">
              CV chartés,
              <span className="block text-whub">propres et prêts client.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-ink/62">
              Un flux simple pour déposer un CV consultant, donner les consignes métier, générer une version W hub anonymisée et suivre les corrections sans perdre l’historique.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link className="rounded-2xl bg-whub px-6 py-4 text-center font-black text-white shadow-violet transition hover:-translate-y-0.5" href="/dashboard">
                Ouvrir le dashboard
              </Link>
              <Link className="rounded-2xl border border-ink/10 bg-white/75 px-6 py-4 text-center font-black text-ink shadow-soft backdrop-blur transition hover:-translate-y-0.5 hover:border-whub/25" href="/requests/new">
                Créer une demande
              </Link>
            </div>
          </div>

          <div className="relative">
            <div className="absolute -inset-6 rounded-[3rem] bg-gradient-to-br from-whub/20 via-white/20 to-lilac blur-2xl" />
            <div className="relative overflow-hidden rounded-[2.5rem] border border-white/70 bg-white/78 p-5 shadow-soft backdrop-blur-xl">
              <div className="rounded-[2rem] bg-graphite p-6 text-white">
                <div className="flex items-center justify-between border-b border-white/10 pb-5">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.28em] text-white/45">Pipeline</p>
                    <h2 className="mt-2 text-2xl font-black tracking-[-0.04em]">CV Architecte Cloud</h2>
                  </div>
                  <span className="rounded-full bg-whub px-3 py-1 text-xs font-black">QA</span>
                </div>
                <div className="mt-6 space-y-4">
                  {[
                    ["01", "Upload CV", "PDF source sécurisé"],
                    ["02", "Anonymisation", "Prénom seul, aucun contact"],
                    ["03", "Charte W hub", "Violet, Poppins, watermark"],
                    ["04", "Validation", "Version finale traçable"]
                  ].map(([step, title, desc]) => (
                    <div key={step} className="flex gap-4 rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-sm font-black text-whub">{step}</span>
                      <div>
                        <p className="font-black">{title}</p>
                        <p className="mt-1 text-sm text-white/52">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
