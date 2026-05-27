import Image from "next/image";
import Link from "next/link";

export function WhubMark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="group inline-flex items-center gap-3" aria-label="W hub CV Factory">
      <span className="relative flex h-12 w-[8.4rem] items-center justify-center overflow-hidden rounded-2xl border border-white/70 bg-white/82 px-3 shadow-soft backdrop-blur-xl transition group-hover:-translate-y-0.5">
        <Image src="/brand/whub-logo.png" alt="W hub" width={1051} height={398} priority className="h-auto w-full object-contain" />
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block text-[11px] font-black uppercase tracking-[0.24em] text-whub">CV Factory</span>
          <span className="mt-1 block text-xs font-semibold text-ink/42">Portail interne</span>
        </span>
      )}
    </Link>
  );
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-black uppercase tracking-[0.34em] text-whub">{children}</p>;
}
