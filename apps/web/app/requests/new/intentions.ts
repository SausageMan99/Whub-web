export type CvIntentionKey = "standard" | "short_client" | "highlight_stack" | "recent_experience" | "senior_target";

export const guidedCvIntentions: { key: CvIntentionKey; label: string; instruction: string }[] = [
  {
    key: "standard",
    label: "CV W hub fidèle — mise en page uniquement",
    instruction: "CV W hub fidèle — mise en page uniquement : conserver tout le contenu métier source sans reformulation, synthèse, condensation ni omission. Retirer seulement les coordonnées, nom de famille, adresse et liens personnels.",
  },
  {
    key: "short_client",
    label: "Exception : CV court client (autorise une synthèse)",
    instruction: "Exception CV court client : l'utilisateur autorise explicitement une version courte/synthétique. Condenser seulement si nécessaire, sans inventer de fait ni supprimer de fait métier important.",
  },
  {
    key: "highlight_stack",
    label: "Mettre en avant la stack",
    instruction: "Mettre en avant la stack technique uniquement par la mise en page quand elle est présente dans le CV source, sans inventer, reformuler, synthétiser, condenser ni omettre les expériences.",
  },
  {
    key: "recent_experience",
    label: "Mettre en avant l'expérience récente",
    instruction: "Mettre en avant l'expérience récente par la mise en page et l'ordre source, sans réécrire, synthétiser, condenser ni omettre les missions du CV fourni.",
  },
  {
    key: "senior_target",
    label: "Profil senior / mission cible",
    instruction: "Profil senior / mission cible : valoriser lisiblement par la mise en page les éléments source existants (leadership, architecture, autonomie), sans ajout, reformulation, synthèse, condensation ni omission métier.",
  },
];

const instructionsByKey = new Map(guidedCvIntentions.map((item) => [item.key, item.instruction]));

export function buildGuidedInstructions(selected: string[], freeText: string): string {
  const guided = selected
    .map((key) => instructionsByKey.get(key as CvIntentionKey))
    .filter((instruction): instruction is string => Boolean(instruction));
  const cleanedFreeText = freeText.trim();

  if (!guided.length) return cleanedFreeText;

  const parts = [`Intentions guidées W hub :\n${guided.map((item) => `- ${item}`).join("\n")}`];
  if (cleanedFreeText) parts.push(`Consignes libres :\n${cleanedFreeText}`);
  return parts.join("\n\n");
}
