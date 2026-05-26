const labels: Record<string, string> = {
  submitted: "En attente",
  processing: "En génération",
  qa_failed: "QA échouée",
  ready: "Prêt",
  revision_requested: "Correction demandée",
  failed: "Erreur",
  cancelled: "Annulé",
  archived: "Archivé"
};

export function StatusBadge({ status }: { status: string }) {
  return <span className="rounded-full bg-whub/10 px-3 py-1 text-xs font-semibold text-whub">{labels[status] ?? status}</span>;
}
