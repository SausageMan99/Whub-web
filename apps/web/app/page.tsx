import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center px-6">
      <p className="mb-4 text-sm font-semibold uppercase tracking-[0.3em] text-whub">W hub</p>
      <h1 className="text-5xl font-bold tracking-tight text-ink">CV Factory</h1>
      <p className="mt-5 max-w-2xl text-lg text-black/70">Portail interne pour générer des CV W hub anonymisés, chartés et vérifiés.</p>
      <div className="mt-8 flex gap-3">
        <Link className="rounded-xl bg-whub px-5 py-3 font-semibold text-white" href="/dashboard">Ouvrir le dashboard</Link>
        <Link className="rounded-xl border border-black/10 bg-white px-5 py-3 font-semibold" href="/login">Connexion</Link>
      </div>
    </main>
  );
}
