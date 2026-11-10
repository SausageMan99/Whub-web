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

/** Codes bloquants qui signifient une perte de contenu (worker : src/qa_defects.py). */
const CONTENT_LOSS_CODES = new Set(["content_missing_from_pdf"]);

function hardBlockers(qaReport: unknown): Record<string, unknown>[] {
  if (!isRecord(qaReport)) return [];
  const quality = isRecord(qaReport.quality_report) ? qaReport.quality_report : {};
  return (Array.isArray(quality.hard_blockers) ? quality.hard_blockers : []).filter(isRecord);
}

export function blockedReason(status: string, qaReport?: unknown) {
  if (status === "needs_human_review") {
    return {
      title: "Le CV source est illisible",
      body: "Le texte du PDF n’a pas pu être lu de façon fiable, même par reconnaissance de caractères. Demande au candidat un PDF exporté depuis Word ou Google Docs, puis crée une nouvelle demande. Tu peux aussi relancer si le PDF a été vérifié.",
      action: "Relancer la mise au format",
    };
  }
  if (status === "qa_failed" && hardBlockers(qaReport).some((b) => CONTENT_LOSS_CODES.has(String(b.code)) || b.content_loss === true)) {
    return {
      title: "Du contenu manque dans le PDF",
      body: "Le CV a été produit mais une partie du contenu repris du CV source n’apparaît pas dans le PDF, même après plusieurs mises en page. Il n’est pas téléchargeable. Vérifie la liste des points ci-dessous, puis demande une nouvelle version (par exemple en raccourcissant la section concernée).",
      action: null,
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

/** Ligne de la table de relecture sous le prénom, pour une demande à relire. */
export function reviewLine(versionCount: number, notesCount: number, blockingCount = 0) {
  const version = `Version ${versionCount || 1}`;
  if (!notesCount) return `${version}, aucun point signalé`;
  const others = notesCount - blockingCount;
  const parts = [
    blockingCount ? `${blockingCount} défaut${blockingCount > 1 ? "s" : ""} à corriger` : "",
    others ? `${others} point${others > 1 ? "s" : ""} à vérifier` : "",
  ].filter(Boolean);
  return `${version}, ${parts.join(", ")}`;
}

// ---------- points à vérifier ----------

export type ProofNote = {
  key: string;
  title: string;
  detail: string;
  page: number | null;
  fix?: { label: string; text: string };
  /** Défaut bloquant resté après les réessais automatiques : à corriger avant l’envoi. */
  blocking?: boolean;
};

type NoteCopy = { title: string; detail: string; fix?: { label: string; text: string } };

const ONE_PAGE_FIX = { label: "Tout faire tenir sur moins de pages", text: "Fais tenir le CV sur moins de pages, sans retirer de contenu." };
const BALANCE_FIX = { label: "Rééquilibrer les pages", text: "Rééquilibre la mise en page entre les pages, sans retirer de contenu." };
const SOURCE_FIX = { label: "Revenir au texte du CV source", text: "Reprends exactement le texte du CV source pour ce passage, sans reformuler." };
const FULL_TEXT_FIX = { label: "Reprendre le texte complet", text: "Reprends en entier les phrases coupées, à partir du CV source, sans reformuler." };
const SHORTEN_FIX = { label: "Raccourcir le CV", text: "Raccourcis les missions les plus anciennes pour faire tenir le CV sur moins de pages." };

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
  // Contrôle du PDF rendu (lot 4). Bloquants : restés après les réessais automatiques.
  content_missing_from_pdf: { title: "Contenu absent du PDF", detail: "Une partie du contenu (certifications, langues, compétences…) n’apparaît pas dans le PDF.", fix: { label: "Réintégrer le contenu", text: "Réintègre dans le PDF tout le contenu du CV source, sans en retirer." } },
  text_overflow: { title: "Texte hors de la page", detail: "Du texte dépasse de la zone imprimable et peut être coupé.", fix: BALANCE_FIX },
  truncated_text: { title: "Phrase coupée", detail: "Une puce ou une phrase s’arrête au milieu, alors que le CV source la donne en entier.", fix: FULL_TEXT_FIX },
  page_nearly_empty: { title: "Page presque vide au milieu du CV", detail: "Une page est à moitié blanche alors que le CV continue.", fix: BALANCE_FIX },
  heading_orphaned_at_page_bottom: { title: "Titre seul en bas de page", detail: "Le titre est en bas de page, son contenu sur la suivante.", fix: BALANCE_FIX },
  placeholder_printed: { title: "« Non spécifié » imprimé", detail: "Une valeur vide (« Non spécifié », « N/A », « () ») apparaît dans le CV.", fix: { label: "Retirer les valeurs vides", text: "Retire les mentions « Non spécifié », « N/A » et les parenthèses vides." } },
  page_furniture_printed: { title: "En-tête du CV source repris", detail: "Un en-tête ou pied de page du CV source (numéro de page, nom du fichier) est resté dans le texte.", fix: { label: "Retirer l’en-tête", text: "Retire les en-têtes et pieds de page du CV source repris dans le texte." } },
  // Avertissements : à vérifier par le relecteur.
  page_underfilled: { title: "Page peu remplie", detail: "La page n’est remplie qu’en partie alors que le CV continue.", fix: BALANCE_FIX },
  last_page_nearly_empty: { title: "Dernière page presque vide", detail: "Elle contient très peu de texte.", fix: ONE_PAGE_FIX },
  short_continuation: { title: "Suite très courte", detail: "Une ou deux lignes d’une expérience passent seules sur la page suivante.", fix: BALANCE_FIX },
  first_page_without_experience: { title: "Aucune expérience en page 1", detail: "La première page ne montre que le profil et les compétences.", fix: { label: "Remonter les expériences", text: "Remonte la première expérience sur la page 1, sans retirer de contenu." } },
  truncated_in_source: { title: "Phrase coupée dans le CV source", detail: "Le CV source s’arrête déjà au milieu de cette phrase : à compléter avec le candidat si besoin." },
  future_end_date: { title: "Date dans le futur", detail: "Une date de fin est postérieure à aujourd’hui : à confirmer avec le candidat." },
  content_language_not_french: { title: "CV en anglais", detail: "Le contenu est en anglais sous des titres français : à valider avec le client.", fix: { label: "Traduire en français", text: "Traduis le contenu du CV en français, sans rien retirer." } },
  description_too_short: { title: "Description très courte", detail: "Le paragraphe de présentation tient en quelques mots.", fix: { label: "Reprendre la description", text: "Reprends la description du profil telle qu’elle figure dans le CV source." } },
  company_field_sentence: { title: "Entreprise à vérifier", detail: "Le nom d’entreprise contient une phrase entière.", fix: { label: "Garder le nom seul", text: "Garde seulement le nom de l’entreprise sur la ligne du poste." } },
  broken_ligature: { title: "Mot mal découpé", detail: "Un mot semble coupé (lettres manquantes).", fix: SOURCE_FIX },
  experience_order_unverified: { title: "Ordre des expériences à vérifier", detail: "Une date illisible empêche de vérifier l’ordre chronologique." },
  prompt_source_truncated: { title: "Fin du CV source à vérifier", detail: "Le CV source était très long : vérifie que les dernières expériences sont bien reprises." },
  certification_kept_unverified: { title: "Certification à vérifier", detail: "Un élément de la section Certifications est repris tel quel." },
  skills_cleanup: { title: "Compétences rangées", detail: "Des éléments ont été déplacés ou retirés de la section Compétences (doublons, langues, formations)." },
  pagination_revision_applied: { title: "Mise en page reprise", detail: "La demande de mise en page a été appliquée, sans retirer de contenu." },
  pagination_revision_not_possible: { title: "Mise en page déjà au plus juste", detail: "Le contenu remplit réellement les pages : il faudrait en retirer pour gagner une page.", fix: SHORTEN_FIX },
};

const SAME_NOTE: Record<string, string> = { page_too_sparse: "last_page_sparse", last_page_nearly_empty: "last_page_sparse" };

/** Codes internes au moteur, sans intérêt pour le relecteur. */
const HIDDEN_CODES = new Set(["qa_failed"]);

function pageOf(item: Record<string, unknown>) {
  const n = Number(item.page);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Points à vérifier lisibles, sans code interne ni extrait brut du CV source.
 *  Les défauts bloquants (quality_report.hard_blockers) viennent en tête, marqués `blocking`. */
export function proofNotes(qaReport: unknown): ProofNote[] {
  if (!isRecord(qaReport)) return [];
  const quality = isRecord(qaReport.quality_report) ? qaReport.quality_report : {};
  const blockers = hardBlockers(qaReport);
  const raw = [
    ...blockers,
    ...(Array.isArray(qaReport.layout_issues) ? qaReport.layout_issues : []),
    ...(Array.isArray(quality.soft_warnings) ? quality.soft_warnings : []),
    ...(Array.isArray(qaReport.content_integrity_issues) ? qaReport.content_integrity_issues : []),
  ].filter(isRecord);
  const revision = isRecord(qaReport.revision_pagination) ? qaReport.revision_pagination : null;

  const seen = new Set<string>();
  const notes: ProofNote[] = [];
  for (const item of raw) {
    const code = typeof item.code === "string" ? item.code : "";
    if (HIDDEN_CODES.has(code)) continue;
    const blocking = blockers.includes(item);
    const page = pageOf(item);
    const canonical = SAME_NOTE[code] ?? code;
    const key = `${canonical}:${page ?? ""}`;
    // Un même code sans page doublonne souvent le même code avec page.
    if (seen.has(key) || (page === null && [...seen].some((k) => k.startsWith(`${canonical}:`)))) continue;
    seen.add(key);
    const copy = NOTE_COPY[canonical] ?? { title: "Point à vérifier", detail: "Le contrôle a relevé un détail à relire." };
    let detail = copy.detail;
    const ratio = Number(item.used_ratio ?? item.fill);
    if (Number.isFinite(ratio) && ratio > 0 && ratio < 1 && /vide|remplie/i.test(copy.title)) {
      detail = `Remplie à ${Math.round(ratio * 100)} %.`;
    }
    if (canonical.startsWith("pagination_revision_") && revision && typeof revision.message === "string" && revision.message.trim()) {
      detail = revision.message.trim();
    } else if (canonical.startsWith("pagination_revision_") && Number(item.previous_pages) > 0 && Number(item.new_pages) > 0) {
      detail = `${detail} ${item.previous_pages} page(s) avant, ${item.new_pages} maintenant.`;
    }
    if (blocking) detail = `${detail} Resté après les réessais automatiques : à corriger avant l’envoi.`;
    notes.push({ key, title: copy.title, detail, page, fix: copy.fix, ...(blocking ? { blocking: true } : {}) });
  }
  return notes.sort((a, b) => Number(Boolean(b.blocking)) - Number(Boolean(a.blocking)) || (a.page ?? 99) - (b.page ?? 99));
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
