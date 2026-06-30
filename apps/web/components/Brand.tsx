import Image from "next/image";
import Link from "next/link";

export function WhubMark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="group inline-flex items-center gap-3" aria-label="W hub CV Factory">
      <span className="flex h-10 w-[7.4rem] items-center justify-center rounded-2xl border border-ink/8 bg-white px-3 transition group-hover:border-whub/20">
        <Image src="/brand/whub-logo.png" alt="W hub" width={1051} height={398} priority className="h-auto w-full object-contain" />
      </span>
      {!compact && (
        <span className="hidden leading-none sm:block">
          <span className="block text-[11px] font-black uppercase tracking-[0.24em] text-ink">CV Factory</span>
          <span className="mt-1 block text-xs font-medium text-ink/42">Portail interne</span>
        </span>
      )}
    </Link>
  );
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-black uppercase tracking-[0.30em] text-whub/72">{children}</p>;
}
