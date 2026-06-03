export type CvStatus =
  | "submitted"
  | "processing"
  | "qa_failed"
  | "ready"
  | "draft_ready"
  | "revision_requested"
  | "failed"
  | "cancelled"
  | "archived"
  | string;

export type CvProgress = {
  percent: number;
  label: string;
  helper: string;
};

function stripDiacritics(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

export function buildCvDownloadFilename(candidateName: string | null | undefined, versionNumber: number | null | undefined) {
  const version = Number.isFinite(Number(versionNumber)) ? Number(versionNumber) : 1;
  const cleanName = stripDiacritics(candidateName ?? "")
    .replace(/\bCV\b/gi, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");

  const base = cleanName || "CV";
  return `${base}-W-hub-v${version}.pdf`;
}

export function getCvStatusLabel(status: CvStatus, eventTypes: string[] = []) {
  const events = new Set(eventTypes);

  if (status === "ready" || events.has("ready")) return "Prêt à télécharger";
  if (status === "draft_ready") return "Brouillon prêt";
  if (status === "qa_failed") return "Contrôle qualité";
  if (status === "failed" || status === "revision_requested") return "À corriger";
  if (events.has("extraction_done")) return "Mise au format W hub";
  if (status === "processing" || events.has("worker_claimed")) return "Analyse du CV";
  if (status === "submitted") return "En attente";
  if (status === "cancelled") return "Annulé";
  if (status === "archived") return "Archivé";
  return "En attente";
}

export function getCvProgress(status: CvStatus, eventTypes: string[] = []): CvProgress {
  const events = new Set(eventTypes);
  const label = getCvStatusLabel(status, eventTypes);

  if (status === "ready" || events.has("ready")) {
    return {
      percent: 100,
      label,
      helper: "Le PDF final a passé la QA et peut être téléchargé."
    };
  }

  if (status === "draft_ready") {
    return {
      percent: 100,
      label,
      helper: "Le PDF peut être téléchargé pour relecture, avec des points qualité à corriger avant envoi client."
    };
  }

  if (status === "failed") {
    return {
      percent: 100,
      label,
      helper: "La génération n’a pas pu aboutir. Corrige la source ou la consigne avant de relancer."
    };
  }

  if (status === "qa_failed") {
    return {
      percent: 85,
      label,
      helper: "Le PDF a été généré mais un blocage de qualité empêche encore la livraison."
    };
  }

  if (events.has("extraction_done")) {
    return {
      percent: 60,
      label,
      helper: "Le contenu du CV source est structuré et prêt pour le contrôle qualité."
    };
  }

  if (status === "processing" || events.has("worker_claimed")) {
    return {
      percent: 35,
      label,
      helper: "Le worker W hub analyse le CV source et prépare la structuration."
    };
  }

  if (status === "revision_requested") {
    return {
      percent: 20,
      label,
      helper: "Une correction a été demandée pour lancer la prochaine version."
    };
  }

  if (status === "cancelled" || status === "archived") {
    return {
      percent: 0,
      label,
      helper: "Cette demande n’est plus en production."
    };
  }

  return {
    percent: 15,
    label,
    helper: "Le CV source attend sa prise en charge."
  };
}
