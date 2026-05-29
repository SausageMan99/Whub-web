export type CvIntentionKey = "standard" | "short_client" | "highlight_stack" | "recent_experience" | "senior_target";

export const guidedCvIntentions: { key: CvIntentionKey; label: string; instruction: string }[] = [
  {
    key: "standard",
    label: "CV standard W hub",
    instruction: "CV standard W hub : conserver fidèlement le contenu source, sans synthèse ni reformulation, et améliorer uniquement la mise en page W hub.",
  },
  {
    key: "short_client",
    label: "CV court client",
    instruction: "CV court client : privilégier une synthèse plus concise, sans supprimer de fait important.",
  },
  {
    key: "highlight_stack",
    label: "Mettre en avant la stack",
    instruction: "Mettre en avant la stack technique uniquement quand elle est présente dans le CV source, sans inventer ni reformuler les expériences.",
  },
  {
    key: "recent_experience",
    label: "Mettre en avant l'expérience récente",
    instruction: "Mettre en avant l'expérience récente par la mise en page et l'ordre source, sans détailler ni réécrire les missions au-delà du CV fourni.",
  },
  {
    key: "senior_target",
    label: "Profil senior / mission cible",
    instruction: "Profil senior / mission cible : valoriser lisiblement par la mise en page les éléments source existants (leadership, architecture, autonomie), sans ajout ni reformulation.",
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
