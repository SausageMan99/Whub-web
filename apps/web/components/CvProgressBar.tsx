import { getCvProgress } from "@/lib/cv-ui";

export function CvProgressBar({ status, events = [], compact = false }: { status: string; events?: string[]; compact?: boolean }) {
  const progress = getCvProgress(status, events);
  const tone = status === "failed" || status === "qa_failed" ? "bg-red-500" : status === "ready" ? "bg-emerald-500" : status === "draft_ready" ? "bg-amber-500" : "bg-whub";

  return (
    <div className={compact ? "min-w-[160px]" : "w-full"}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className={compact ? "text-xs font-black text-ink/65" : "text-sm font-black text-ink"}>{progress.label}</p>
        <p className={compact ? "text-xs font-black text-ink/40" : "text-sm font-black text-ink/45"}>{progress.percent}%</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-ink/8">
        <div className={`h-full rounded-full transition-all duration-700 ${tone}`} style={{ width: `${progress.percent}%` }} />
      </div>
      {!compact && <p className="mt-2 text-sm font-semibold text-ink/45">{progress.helper}</p>}
    </div>
  );
}
