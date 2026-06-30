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
    <main className="paper-texture min-h-screen bg-porcelain text-ink">
      <header className="sticky top-0 z-20 border-b border-ink/8 bg-white/82 backdrop-blur-xl supports-[backdrop-filter]:bg-white/72">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <WhubMark />
          <nav className="flex items-center gap-1 rounded-full border border-ink/8 bg-white/84 p-1 shadow-[0_10px_30px_rgba(20,17,24,0.05)]">
            {nav.map((item) => (
              <Link
                key={item.key}
                href={item.href}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition duration-200 motion-safe:hover:-translate-y-0.5 ${
                  active === item.key ? "bg-whub text-white shadow-violet" : "text-ink/56 hover:bg-mist hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">{children}</div>
    </main>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`premium-card rounded-[1.75rem] ${className}`}>{children}</section>;
}
