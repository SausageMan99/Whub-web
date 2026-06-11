import { getCvStatusLabel } from "@/lib/cv-ui";

const styles: Record<string, string> = {
  submitted: "bg-amber-100 text-amber-800 ring-amber-200",
  processing: "bg-whub/10 text-whub ring-whub/15",
  qa_failed: "bg-orange-100 text-orange-800 ring-orange-200",
  ready: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  draft_ready: "bg-amber-100 text-amber-800 ring-amber-200",
  revision_requested: "bg-blue-100 text-blue-800 ring-blue-200",
  failed: "bg-red-100 text-red-800 ring-red-200",
  dead_letter: "bg-red-200 text-red-900 ring-red-300",
  needs_human_review: "bg-blue-100 text-blue-800 ring-blue-200",
  cancelled: "bg-stone-100 text-stone-600 ring-stone-200",
  archived: "bg-stone-100 text-stone-500 ring-stone-200"
};

export function StatusBadge({ status, events = [] }: { status: string; events?: string[] }) {
  return <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-black ring-1 ${styles[status] ?? "bg-whub/10 text-whub ring-whub/15"}`}>{getCvStatusLabel(status, events)}</span>;
}
