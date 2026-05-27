export type CvStatus =
  | "submitted"
  | "processing"
  | "qa_failed"
  | "ready"
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

export function getCvProgress(status: CvStatus, eventTypes: string[] = []): CvProgress {
  const events = new Set(eventTypes);

  if (status === "ready" || events.has("ready")) {
    return {
      percent: 100,
      label: "CV prêt",
      helper: "Le PDF final a passé la QA et peut être téléchargé."
    };
  }

  if (status === "failed") {
    return {
      percent: 100,
      label: "Erreur",
      helper: "La génération a échoué. Ouvre la demande pour voir le détail."
    };
  }

  if (status === "qa_failed") {
    return {
      percent: 85,
      label: "QA à reprendre",
      helper: "Le PDF a été généré mais n’a pas passé le contrôle qualité."
    };
  }

  if (events.has("extraction_done")) {
    return {
      percent: 60,
      label: "Extraction terminée",
      helper: "Le contenu du CV source est structuré pour le rendu W hub."
    };
  }

  if (status === "processing" || events.has("worker_claimed")) {
    return {
      percent: 35,
      label: "Traitement lancé",
      helper: "Le worker W hub a pris la demande en charge."
    };
  }

  if (status === "revision_requested") {
    return {
      percent: 20,
      label: "Correction demandée",
      helper: "La demande est revenue dans la file pour une nouvelle version."
    };
  }

  if (status === "cancelled" || status === "archived") {
    return {
      percent: 0,
      label: status === "cancelled" ? "Annulé" : "Archivé",
      helper: "Cette demande n’est plus en production."
    };
  }

  return {
    percent: 15,
    label: "Demande reçue",
    helper: "Le CV est dans la file de production."
  };
}
