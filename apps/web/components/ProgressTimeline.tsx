import { getCvProgress } from "@/lib/cv-ui";

const baseSteps = [
  { key: "received", label: "CV reçu" },
  { key: "extracted", label: "Texte extrait" },
  { key: "generated", label: "Version W hub" },
  { key: "qa", label: "Contrôle qualité" },
  { key: "ready", label: "PDF prêt" },
];

export function ProgressTimeline({ status, events = [] }: { status: string; events?: string[] }) {
  const progress = getCvProgress(status, events);
  const activeIndex = status === "ready" || status === "draft_ready" || events.includes("ready") || events.includes("draft_ready")
    ? 4
    : status === "qa_failed" || events.some((event) => ["layout_variant_selected", "quality_source_profiled"].includes(event))
      ? 3
      : events.includes("extraction_done")
        ? 2
        : events.includes("worker_claimed") || status === "processing"
          ? 1
          : 0;

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-5">
        {baseSteps.map((step, index) => {
          const done = index <= activeIndex;
          return (
            <div key={step.key} className="flex items-center gap-3 sm:block">
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-black ${done ? "bg-whub text-white" : "bg-ink/6 text-ink/34"}`}>
                {index + 1}
              </span>
              <p className={`text-sm font-semibold ${done ? "text-ink" : "text-ink/38"}`}>{step.label}</p>
            </div>
          );
        })}
      </div>
      <div className="mt-5">
        <div className="h-1.5 overflow-hidden rounded-full bg-ink/8">
          <div className="h-full rounded-full bg-whub transition-all duration-700" style={{ width: `${progress.percent}%` }} />
        </div>
        <p className="mt-3 text-sm font-medium text-ink/48">{progress.helper}</p>
      </div>
    </div>
  );
}
