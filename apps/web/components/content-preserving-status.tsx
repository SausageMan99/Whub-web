import type { ContentPreservingDiagnostics } from "@/lib/content-preserving-diagnostics";

type Props = {
  diagnostics: ContentPreservingDiagnostics;
};

const VARIANT_LABELS: Record<NonNullable<ContentPreservingDiagnostics['variant']>, string> = {
  natural: 'naturelle',
  compact: 'compacte',
  sidebar_heavy: 'latérale renforcée',
  experience_first: 'expériences d’abord',
  deterministic_content_preserving: 'préservée',
};

const FALLBACK_LABELS: Record<NonNullable<ContentPreservingDiagnostics['fallbackCategory']>, string> = {
  provider_unavailable: 'Fournisseur indisponible',
  invalid_response: 'Réponse invalide',
  validation_failed: 'Validation échouée',
  unknown: 'Erreur inconnue',
};

export function ContentPreservingStatus({ diagnostics }: Props) {
  if (!diagnostics.present) return null;

  const {
    variant,
    density,
    missingBlocksCount,
    usedFallback,
    fallbackCategory,
    durationMs,
    score,
  } = diagnostics;

  const badgeLabel = variant === 'deterministic_content_preserving' ? 'Mise en page préservée' : 'Diagnostic mise en page';

  return (
    <div className="rounded-2xl border border-ink/8 bg-white p-6">
      <p className="text-xs font-black uppercase tracking-[0.28em] text-ink/60">{badgeLabel}</p>

      <div className="mt-4 space-y-2 text-sm font-semibold leading-6 text-ink/75">
        {variant && <p>Variante: {VARIANT_LABELS[variant]}</p>}
        {density && <p>Densité: {density}</p>}
        {typeof missingBlocksCount === 'number' && (
          <p>
            Blocs manquants:{' '}
            {Math.max(0, Math.floor(missingBlocksCount))}
          </p>
        )}
        {usedFallback && fallbackCategory && (
          <p>
            Repli automatique utilisé ({FALLBACK_LABELS[fallbackCategory]})
          </p>
        )}
        {typeof score === 'number' && (
          <p>
            Score:{' '}
            {Math.max(0, Math.min(1, score)).toFixed(2)}
            /1
          </p>
        )}
        {typeof durationMs === 'number' && (
          <p>Génération: {(Math.max(0, durationMs) / 1000).toFixed(1)}s</p>
        )}
      </div>
    </div>
  );
}
