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
  source_fidelity_soft_warning: "Fidélité source à confirmer",
  extraction_low_confidence: "Extraction peu fiable",
};

const SOURCE_PROFILE_LABELS: Record<string, string> = {
  normal: "CV standard",
  senior_long: "CV senior long",
  ats: "CV ATS / jobboard",
  scanned: "Extraction faible",
  two_column: "CV en colonnes",
  graphic: "CV graphique",
  risky: "CV risqué",
  unknown: "Profil source inconnu",
};

export type QualitySummary = {
  sourceProfileLabel: string;
  scores: { extraction: number; fidelity: number; layout: number; overall: number };
  metrics: string[];
  warnings: string[];
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

function clampScore(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export function normalizeQualitySummary(qaReport: unknown): QualitySummary | null {
  if (!isRecord(qaReport)) return null;
  const quality = isRecord(qaReport.quality_report) ? qaReport.quality_report : null;
  if (!quality) return null;

  const scores = isRecord(quality.scores) ? quality.scores : {};
  const metrics = isRecord(quality.metrics) ? quality.metrics : {};
  const sourceProfile = typeof quality.source_profile === "string" ? quality.source_profile : "unknown";
  const sourceProfileLabel =
    SOURCE_PROFILE_LABELS[sourceProfile] ?? SOURCE_PROFILE_LABELS.unknown;

  const metricLabels: string[] = [];
  if (Number.isFinite(Number(metrics.pages))) {
    metricLabels.push(`${Number(metrics.pages)} pages`);
  }
  if (Number.isFinite(Number(metrics.attempts_count))) {
    metricLabels.push(`${Number(metrics.attempts_count)} variantes testées`);
  }
  if (Number.isFinite(Number(metrics.total_duration_seconds))) {
    metricLabels.push(`${Number(metrics.total_duration_seconds)}s`);
  }

  const warnings: string[] = [];
  if (Array.isArray(quality.soft_warnings)) {
    for (const item of quality.soft_warnings) {
      if (!isRecord(item)) continue;
      const code = typeof item.code === "string" ? item.code : "";
      const label = WARNING_LABELS[code] ?? "Point qualité à vérifier";
      const page = Number(item.page);
      const prefix = Number.isFinite(page) && page > 0 ? `Page ${page} · ` : "";
      warnings.push(`${prefix}${label}`);
    }
  }

  return {
    sourceProfileLabel,
    scores: {
      extraction: clampScore(scores.extraction),
      fidelity: clampScore(scores.fidelity),
      layout: clampScore(scores.layout),
      overall: clampScore(scores.overall),
    },
    metrics: metricLabels,
    warnings,
  };
}

export function draftReadyTitle(status: string) {
  return status === "draft_ready" ? "Brouillon prêt — points qualité détectés" : null;
}

export function isHardFailureStatus(status: string) {
  return status === "failed" || status === "qa_failed" || status === "dead_letter";
}

export function hardFailureCopy(status: string) {
  if (status === "failed" || status === "dead_letter") {
    return {
      title: "À corriger — génération impossible",
      body: "La génération n'a pas pu aboutir. Vérifie le PDF source et la consigne avant de relancer ; aucun détail interne n'est affiché ici.",
      action: { label: "Relancer la génération", href: undefined },
    };
  }

  if (status === "qa_failed") {
    return {
      title: "Contrôle qualité — PDF non livrable",
      body: "Le PDF est généré, mais un blocage qualité empêche la livraison. Corrige la source ou la consigne puis relance ou ajoute une correction ci-dessous.",
      action: { label: "Relancer la génération", href: undefined },
    };
  }

  if (status === "needs_human_review") {
    return {
      title: "Validation humaine requise",
      body: "Le CV source est trop difficile à interpréter automatiquement. Une vérification humaine est requise avant de relancer la génération ; aucun PDF n'a été produit.",
      action: { label: "Relancer après vérification", href: undefined },
    };
  }

  return null;
}

export function safeRetryCopy(status: string, candidateName?: string | null) {
  if (status === "failed" || status === "dead_letter") {
    return { label: "Relancer la génération" };
  }

  const first = (candidateName ?? "").split(" ")[0]?.trim();
  if (status === "qa_failed") {
    return {
      label: first ? `Relancer ${first}` : "Relancer la génération",
      hint: first
        ? `La prochaine version pour ${first} repart depuis le même CV source et la même consigne.`
        : "La prochaine version repart depuis le même CV source et la même consigne.",
    };
  }

  if (status === "needs_human_review") {
    return {
      label: first ? `Vérifier le CV de ${first} puis relancer` : "Vérifier le CV puis relancer",
      hint: first
        ? `Le CV source de ${first} doit être relu ou remplacé par un PDF plus lisible avant de relancer. La prochaine version repartira alors depuis la même source.`
        : "Le CV source doit être relu ou remplacé par un PDF plus lisible avant de relancer. La prochaine version repartira alors depuis la même source.",
    };
  }

  return null;
}
