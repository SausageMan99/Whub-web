export type QaLayoutIssue = {
  code?: unknown;
  message?: unknown;
  page?: unknown;
  snippet?: unknown;
};

const WARNING_LABELS: Record<string, string> = {
  page_too_dense: "Page trop dense",
  last_page_sparse: "Dernière page trop vide",
  bad_page_break: "Saut de page à reprendre",
  skill_block_too_long: "Bloc de compétences trop long",
  skills_too_dense: "Compétences trop denses",
  experience_orphan_heading: "Titre d’expérience isolé",
  experience_section_orphan_heading: "Section d’expérience isolée",
  skill_overflow_page_created: "Compétences reportées sur une page de suite",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cleanText(value: unknown, maxLength = 180) {
  if (typeof value !== "string") return "";
  return value
    .replace(/[\r\n\t]+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim()
    .slice(0, maxLength);
}

function pageLabel(page: unknown) {
  const pageNumber = Number(page);
  return Number.isFinite(pageNumber) && pageNumber > 0 ? `Page ${pageNumber} · ` : "";
}

export function normalizeDraftWarnings(qaReport: unknown): string[] {
  if (!isRecord(qaReport) || !Array.isArray(qaReport.layout_issues)) return [];

  return qaReport.layout_issues
    .filter(isRecord)
    .map((issue: QaLayoutIssue) => {
      const code = typeof issue.code === "string" ? issue.code : "";
      const label = WARNING_LABELS[code] ?? "Point qualité à vérifier";
      const message = cleanText(issue.message) || cleanText(issue.snippet, 120);
      return `${pageLabel(issue.page)}${label}${message ? ` — ${message}` : ""}`;
    })
    .filter(Boolean);
}

export function draftReadyTitle(status: string) {
  return status === "draft_ready" ? "PDF généré en brouillon — points qualité détectés" : null;
}

export function isHardFailureStatus(status: string) {
  return status === "failed" || status === "qa_failed";
}

export function hardFailureCopy(status: string) {
  if (status === "qa_failed") {
    return {
      title: "Erreur bloquante — PDF non livrable",
      body: "Le contrôle qualité a détecté un problème qui bloque la diffusion du PDF. Relance la génération après correction ; aucun détail technique interne n’est affiché ici.",
    };
  }

  if (status === "failed") {
    return {
      title: "Erreur de génération",
      body: "La génération n’a pas pu aboutir. Relance la demande si le fichier source et les consignes sont corrects ; les détails internes restent masqués.",
    };
  }

  return null;
}
