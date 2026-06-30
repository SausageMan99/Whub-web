import { getCvStatusLabel } from "@/lib/cv-ui";

const styles: Record<string, string> = {
  submitted: "bg-ink/[0.045] text-ink/62 ring-ink/8",
  processing: "bg-whub/10 text-whub ring-whub/14",
  qa_failed: "bg-orange-50 text-orange-800 ring-orange-200/70",
  ready: "bg-emerald-50 text-emerald-800 ring-emerald-200/80",
  draft_ready: "bg-amber-50 text-amber-800 ring-amber-200/80",
  revision_requested: "bg-blue-50 text-blue-800 ring-blue-200/80",
  failed: "bg-red-50 text-red-800 ring-red-200/80",
  dead_letter: "bg-red-50 text-red-900 ring-red-200/80",
  needs_human_review: "bg-blue-50 text-blue-800 ring-blue-200/80",
  cancelled: "bg-stone-50 text-stone-600 ring-stone-200/80",
  archived: "bg-stone-50 text-stone-500 ring-stone-200/80"
};

export function StatusBadge({ status, events = [] }: { status: string; events?: string[] }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-black ring-1 ${styles[status] ?? "bg-whub/10 text-whub ring-whub/14"}`}>
      <span className="status-dot" aria-hidden="true" />
      {getCvStatusLabel(status, events)}
    </span>
  );
}
