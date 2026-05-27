import Link from "next/link";
import { WhubMark } from "./Brand";

export function AppShell({
  children,
  active = "dashboard"
}: {
  children: React.ReactNode;
  active?: "dashboard" | "new" | "detail";
}) {
  const nav = [
    { href: "/dashboard", label: "Demandes", key: "dashboard" },
    { href: "/requests/new", label: "Nouveau CV", key: "new" }
  ];

  return (
    <main className="relative min-h-screen overflow-hidden bg-porcelain text-ink">
      <div className="pointer-events-none absolute -right-28 -top-28 h-96 w-96 rounded-full bg-whub/14 blur-3xl" />
      <div className="pointer-events-none absolute left-[-12rem] top-1/3 h-[34rem] w-[34rem] rounded-full bg-lilac/55 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-18rem] right-1/4 h-[32rem] w-[32rem] rounded-full bg-whub/8 blur-3xl" />

      <header className="sticky top-0 z-20 border-b border-white/70 bg-porcelain/78 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <WhubMark />
          <nav className="flex items-center gap-2 rounded-full border border-white/70 bg-white/65 p-1 shadow-soft">
            {nav.map((item) => (
              <Link
                key={item.key}
                href={item.href}
                className={`rounded-full px-4 py-2 text-sm font-bold transition ${
                  active === item.key ? "bg-ink text-white shadow-sm" : "text-ink/55 hover:bg-white hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-10">{children}</div>
    </main>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-[2rem] border border-white/75 bg-white/78 shadow-soft backdrop-blur-xl ${className}`}>{children}</section>;
}
