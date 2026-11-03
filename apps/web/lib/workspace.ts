// Logique de l'écran de travail « Demandes » : regroupement par action,
// étape de mise au format, validation humaine et points à vérifier.
// Fonctions pures, sans accès Supabase, pour rester testables.

export type QueueGroup = "relire" | "fab" | "bloque" | "pret";

export type WorkspaceEvent = {
  request_id?: string | null;
  event_type?: string | null;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type WorkspaceVersion = {
  id: string;
  request_id?: string | null;
  version_number?: number | null;
  created_at?: string | null;
  final_pdf_path?: string | null;
  qa_status?: string | null;
  qa_report?: unknown;
};

export const GROUPS: { key: QueueGroup; label: string }[] = [
  { key: "relire", label: "À relire" },
  { key: "fab", label: "En cours de mise au format" },
  { key: "bloque", label: "Bloqués" },
  { key: "pret", label: "Prêts à envoyer" },
];

export const STATE_LABEL: Record<QueueGroup, string> = {
  relire: "À relire",
  fab: "Mise au format",
  bloque: "Bloqué",
  pret: "Prêt à envoyer",
};

export const STEPS = [
  "PDF reçu",
  "Lecture du CV source",
  "Mise au format W hub",
  "Contrôle de fidélité",
  "Épreuve prête à relire",
];

const STEP_SHORT = ["réception", "lecture du CV", "mise en page", "contrôle de fidélité", "finition"];

const IN_PROGRESS = new Set(["submitted", "processing", "revision_requested"]);
const BLOCKED = new Set(["failed", "dead_letter", "needs_human_review", "qa_failed"]);
const REVIEWABLE = new Set(["ready", "draft_ready"]);

export const VALIDATED_EVENT = "human_validated";
export const VALIDATION_CANCELLED_EVENT = "human_validation_cancelled";

function time(value: string | null | undefined) {
  const t = value ? Date.parse(value) : NaN;
  return Number.isFinite(t) ? t : 0;
}

/** Les versions triées de la plus ancienne à la plus récente, numérotées 1, 2, 3 pour cette demande.
 *  `version_number` vient d'une séquence globale à toutes les demandes : il ne doit pas être affiché. */
export function numberVersions<T extends WorkspaceVersion>(versions: T[]): (T & { ordinal: number })[] {
  return [...versions]
    .sort((a, b) => time(a.created_at) - time(b.created_at) || (a.version_number ?? 0) - (b.version_number ?? 0))
    .map((version, index) => ({ ...version, ordinal: index + 1 }));
}

/** La validation humaine la plus récente, si elle porte sur la dernière version et n'a pas été annulée. */
export function currentValidation(events: WorkspaceEvent[], latestVersion: WorkspaceVersion | null | undefined) {
  if (!latestVersion) return null;
  const relevant = events
    .filter((e) => e.event_type === VALIDATED_EVENT || e.event_type === VALIDATION_CANCELLED_EVENT)
    .sort((a, b) => time(a.created_at) - time(b.created_at));
  const last = relevant.at(-1);
  if (!last || last.event_type !== VALIDATED_EVENT) return null;
  const versionId = typeof last.payload?.version_id === "string" ? last.payload.version_id : null;
  if (versionId && versionId !== latestVersion.id) return null;
  if (!versionId && time(last.created_at) < time(latestVersion.created_at)) return null;
  const by = typeof last.payload?.by === "string" && last.payload.by.trim() ? last.payload.by.trim() : null;
  return { by, at: last.created_at ?? null };
}

export function groupFor(status: string, validated: boolean): QueueGroup | null {
  if (IN_PROGRESS.has(status)) return "fab";
  if (BLOCKED.has(status)) return "bloque";
  if (REVIEWABLE.has(status)) return validated ? "pret" : "relire";
  return null; // annulé, archivé : hors de la file
}

const RESTART_EVENTS = new Set(["revision_requested", "retry_requested", "unlocked"]);

/** Étape en cours (0 à 4), en ne regardant que les événements de la tentative en cours. */
export function currentStep(status: string, events: WorkspaceEvent[]) {
  const sorted = [...events].sort((a, b) => time(a.created_at) - time(b.created_at));
  let start = 0;
  sorted.forEach((e, i) => {
    if (RESTART_EVENTS.has(e.event_type ?? "")) start = i + 1;
  });
  const types = new Set(sorted.slice(start).map((e) => e.event_type));
  if (types.has("layout_variant_selected") || types.has("quality_source_profiled")) return 3;
  if (types.has("extraction_done")) return 2;
  if (types.has("worker_claimed") || status === "processing") return 1;
  return 0;
}

export function stepLine(step: number) {
  return `Étape ${step + 1} sur 5, ${STEP_SHORT[step] ?? STEP_SHORT[0]}`;
}

export function blockedReason(status: string) {
  if (status === "needs_human_review") {
    return {
      title: "Le CV source est illisible",
      body: "Le texte du PDF n’a pas pu être lu de façon fiable, même par reconnaissance de caractères. Demande au candidat un PDF exporté depuis Word ou Google Docs, puis crée une nouvelle demande. Tu peux aussi relancer si le PDF a été vérifié.",
      action: "Relancer la mise au format",
    };
  }
  if (status === "qa_failed") {
    return {
      title: "Le contrôle a bloqué le PDF",
      body: "Le CV a été produit mais il contient un problème bloquant, par exemple une coordonnée du candidat. Il n’est pas téléchargeable. Décris la correction à faire ci-dessous : une nouvelle version repartira du même CV source.",
      action: null,
    };
  }
  return {
    title: "La mise au format a échoué",
    body: "Aucun CV n’a pu être produit après plusieurs essais. Vérifie que le PDF source s’ouvre normalement, puis relance.",
    action: "Relancer la mise au format",
  };
}

// ---------- points à vérifier ----------

export type ProofNote = {
  key: string;
  title: string;
  detail: string;
  page: number | null;
  fix?: { label: string; text: string };
};

type NoteCopy = { title: string; detail: string; fix?: { label: string; text: string } };

const ONE_PAGE_FIX = { label: "Tout faire tenir sur moins de pages", text: "Fais tenir le CV sur moins de pages, sans retirer de contenu." };
const BALANCE_FIX = { label: "Rééquilibrer les pages", text: "Rééquilibre la mise en page entre les pages, sans retirer de contenu." };
const SOURCE_FIX = { label: "Revenir au texte du CV source", text: "Reprends exactement le texte du CV source pour ce passage, sans reformuler." };

const NOTE_COPY: Record<string, NoteCopy> = {
  last_page_sparse: { title: "Dernière page presque vide", detail: "Elle contient très peu de texte.", fix: ONE_PAGE_FIX },
  page_too_sparse: { title: "Page presque vide", detail: "Elle contient très peu de texte.", fix: ONE_PAGE_FIX },
  page_too_dense: { title: "Page très chargée", detail: "Le texte est serré et peut être difficile à lire.", fix: BALANCE_FIX },
  page_dense_but_acceptable: { title: "Page chargée", detail: "Lisible, mais dense." },
  page_balance_unbalanced: { title: "Pages déséquilibrées", detail: "Une page est bien plus remplie que l’autre.", fix: BALANCE_FIX },
  continuation_tail_page: { title: "Petite page de suite", detail: "Quelques lignes débordent sur une page de plus.", fix: ONE_PAGE_FIX },
  bad_page_break: { title: "Coupure de page à reprendre", detail: "Un bloc est coupé entre deux pages.", fix: BALANCE_FIX },
  experience_orphan_heading: { title: "Titre d’expérience isolé", detail: "Le titre est en bas de page, son contenu sur la suivante.", fix: BALANCE_FIX },
  experience_section_orphan_heading: { title: "Titre de section isolé", detail: "Le titre est en bas de page, son contenu sur la suivante.", fix: BALANCE_FIX },
  skill_block_too_long: { title: "Bloc de compétences très long", detail: "Toutes les compétences viennent du CV source." },
  skills_too_dense: { title: "Compétences très denses", detail: "Toutes les compétences viennent du CV source.", fix: { label: "Garder les compétences principales", text: "Garde seulement les compétences les plus liées au poste visé." } },
  too_many_skill_items: { title: "Beaucoup de compétences", detail: "Toutes viennent du CV source.", fix: { label: "Garder les compétences principales", text: "Garde seulement les compétences les plus liées au poste visé." } },
  skill_overflow_page_created: { title: "Compétences sur une page de suite", detail: "Une partie des compétences passe sur une page de plus.", fix: BALANCE_FIX },
  duplicate_skill_items: { title: "Compétences en double", detail: "Une même compétence apparaît plusieurs fois.", fix: { label: "Retirer les doublons", text: "Retire les compétences en double." } },
  autres_dominates_skills: { title: "Catégorie « Autres » trop large", detail: "Beaucoup de compétences n’ont pas trouvé de catégorie.", fix: { label: "Mieux classer les compétences", text: "Classe les compétences de la catégorie « Autres » dans des catégories plus précises." } },
  title_absent_from_source: { title: "Intitulé de poste reformulé", detail: "L’intitulé ne figure pas tel quel dans le CV source.", fix: { label: "Reprendre l’intitulé source", text: "Garde l’intitulé de poste exact du CV source." } },
  experience_role_fact_absent_from_source: { title: "Poste reformulé dans une expérience", detail: "Un intitulé de poste ne figure pas tel quel dans le CV source.", fix: SOURCE_FIX },
  experience_date_absent_from_source: { title: "Date à vérifier", detail: "Une date d’expérience ne figure pas telle quelle dans le CV source.", fix: SOURCE_FIX },
  experience_content_rewritten_or_absent_from_source: { title: "Mission reformulée", detail: "Une description de mission s’écarte du texte du CV source.", fix: SOURCE_FIX },
  company_highlight_absent_from_source: { title: "Entreprise à vérifier", detail: "Un nom d’entreprise ne figure pas tel quel dans le CV source.", fix: SOURCE_FIX },
  pdf_fact_absent_from_source: { title: "Information à vérifier", detail: "Une information du CV W hub ne se retrouve pas dans le CV source.", fix: SOURCE_FIX },
  json_fact_missing_from_pdf: { title: "Information non reprise", detail: "Une information lue dans le CV source n’apparaît pas dans le PDF.", fix: { label: "Réintégrer l’information", text: "Réintègre toutes les informations du CV source, sans en retirer." } },
  source_coverage_missing_experience_item: { title: "Expérience manquante ?", detail: "Une expérience du CV source semble absente.", fix: { label: "Réintégrer l’expérience", text: "Vérifie que toutes les expériences du CV source sont reprises." } },
  source_coverage_missing_section: { title: "Section manquante ?", detail: "Une section du CV source semble absente.", fix: { label: "Réintégrer la section", text: "Vérifie que toutes les sections du CV source sont reprises." } },
  source_experience_location_missing_from_pdf: { title: "Lieu d’expérience absent", detail: "Un lieu indiqué dans le CV source n’est pas repris." },
  experience_misclassified_as_formation: { title: "Expérience classée en formation", detail: "Un élément semble rangé dans la mauvaise section.", fix: { label: "Reclasser", text: "Range dans Expériences les éléments qui sont des expériences professionnelles." } },
  empty_formation_stub: { title: "Formation vide", detail: "Une formation n’a pas de contenu." },
  empty_experience_date_stub: { title: "Expérience sans date", detail: "Une expérience n’a pas de date." },
  experience_header_without_body: { title: "Expérience sans description", detail: "Un intitulé n’a pas de contenu dessous." },
  full_name_display: { title: "Nom de famille visible ?", detail: "Le nom complet du candidat semble affiché.", fix: { label: "Garder le prénom seul", text: "Retire le nom de famille du candidat, garde seulement le prénom." } },
  candidate_identity_term_exposed: { title: "Élément d’identité visible ?", detail: "Un élément qui identifie le candidat semble affiché.", fix: { label: "Retirer l’élément", text: "Retire tout élément qui identifie le candidat en dehors du prénom." } },
  numbered_placeholder_repetition: { title: "Texte répété", detail: "Un passage semble répété ou incomplet." },
  revision_added_pages: { title: "La correction a ajouté une page", detail: "Le CV est plus long que la version précédente.", fix: ONE_PAGE_FIX },
  source_fidelity_soft_warning: { title: "Fidélité à confirmer", detail: "Un passage s’écarte légèrement du CV source." },
  extraction_low_confidence: { title: "Lecture du CV source incertaine", detail: "Le texte source était difficile à lire : relis l’épreuve avec attention." },
};

const SAME_NOTE: Record<string, string> = { page_too_sparse: "last_page_sparse" };

function pageOf(item: Record<string, unknown>) {
  const n = Number(item.page);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Points à vérifier lisibles, sans code interne ni extrait brut du CV source. */
export function proofNotes(qaReport: unknown): ProofNote[] {
  if (!isRecord(qaReport)) return [];
  const quality = isRecord(qaReport.quality_report) ? qaReport.quality_report : {};
  const raw = [
    ...(Array.isArray(qaReport.layout_issues) ? qaReport.layout_issues : []),
    ...(Array.isArray(quality.soft_warnings) ? quality.soft_warnings : []),
    ...(Array.isArray(qaReport.content_integrity_issues) ? qaReport.content_integrity_issues : []),
  ].filter(isRecord);

  const seen = new Set<string>();
  const notes: ProofNote[] = [];
  for (const item of raw) {
    const code = typeof item.code === "string" ? item.code : "";
    const page = pageOf(item);
    const canonical = SAME_NOTE[code] ?? code;
    const key = `${canonical}:${page ?? ""}`;
    // Un même code sans page doublonne souvent le même code avec page.
    if (seen.has(key) || (page === null && [...seen].some((k) => k.startsWith(`${canonical}:`)))) continue;
    seen.add(key);
    const copy = NOTE_COPY[canonical] ?? { title: "Point à vérifier", detail: "Le contrôle a relevé un détail à relire." };
    let detail = copy.detail;
    const ratio = Number(item.used_ratio);
    if (Number.isFinite(ratio) && ratio > 0 && ratio < 1 && /vide/i.test(copy.title)) {
      detail = `Remplie à ${Math.round(ratio * 100)} %.`;
    }
    notes.push({ key, title: copy.title, detail, page, fix: copy.fix });
  }
  return notes.sort((a, b) => (a.page ?? 99) - (b.page ?? 99));
}

/** Devine un prénom à partir du nom de fichier (« CV_Ines_Martin.pdf » → « Ines »). */
export function guessFirstName(fileName: string) {
  const words = fileName.replace(/\.pdf$/i, "").split(/[\s_\-.()]+/);
  return words.find((w) => /^[A-ZÀ-Ý][a-zà-ÿ]{2,}$/.test(w) && !/^(Cv|Curriculum|Vitae|Resume|Final|Version)$/i.test(w)) ?? "";
}

// ---------- dates ----------

export function shortAgo(iso: string | null | undefined, now = Date.now()) {
  const t = time(iso);
  if (!t) return "";
  const m = Math.round((now - t) / 60000);
  if (m < 1) return "maint.";
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h`;
  const d = Math.round(h / 24);
  if (d === 1) return "hier";
  if (d < 7) return `${d} j`;
  return new Date(t).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

export function longAgo(iso: string | null | undefined, now = Date.now()) {
  const t = time(iso);
  if (!t) return "";
  const m = Math.round((now - t) / 60000);
  if (m < 1) return "à l’instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `il y a ${h} h`;
  const d = Math.round(h / 24);
  if (d === 1) return "hier";
  if (d < 7) return `il y a ${d} jours`;
  return `le ${new Date(t).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;
}
