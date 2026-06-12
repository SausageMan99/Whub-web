export type ContentPreservingDiagnostics = {
  present: boolean;
  variant?: 'natural' | 'compact' | 'sidebar_heavy' | 'experience_first' | 'deterministic_content_preserving';
  density?: 'comfortable' | 'normal' | 'compact';
  missingBlocksCount?: number;
  usedFallback?: boolean;
  fallbackCategory?: 'provider_unavailable' | 'invalid_response' | 'validation_failed' | 'unknown';
  providerName?: string;
  durationMs?: number;
  score?: number;
};

export type CvEvent = {
  request_id?: string | null;
  event_type?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type CompactContentPreservingBadge = {
  present: boolean;
  label?: string;
  tone?: 'ok' | 'warning' | 'muted';
};

const VARIANT_KEYS = [
  'natural',
  'compact',
  'sidebar_heavy',
  'experience_first',
  'deterministic_content_preserving',
] as const;

const DENSITY_KEYS = ['comfortable', 'normal', 'compact'] as const;

const FALLBACK_CATEGORIES = [
  'provider_unavailable',
  'invalid_response',
  'validation_failed',
] as const;

const VARIANT_LABELS: Record<NonNullable<ContentPreservingDiagnostics['variant']>, string> = {
  natural: 'naturelle',
  compact: 'compacte',
  sidebar_heavy: 'latérale',
  experience_first: 'expériences',
  deterministic_content_preserving: 'préservée',
};

const DETAIL_VARIANT_LABELS: Record<NonNullable<ContentPreservingDiagnostics['variant']>, string> = {
  natural: 'naturelle',
  compact: 'compacte',
  sidebar_heavy: 'latérale renforcée',
  experience_first: 'expériences d’abord',
  deterministic_content_preserving: 'préservée',
};

function getString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  return value.trim() || undefined;
}

function getNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return undefined;
}

export function extractContentPreservingDiagnostics(events: CvEvent[]): ContentPreservingDiagnostics {
  const contentPreservingEvents = events
    .filter((event) => typeof event.event_type === 'string' && event.event_type.startsWith('content_preserving_'))
    .sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return bTime - aTime;
    });

  const latest = contentPreservingEvents[0];
  if (!latest || !latest.metadata) {
    return { present: false };
  }

  const metadata = latest.metadata;
  const variantRaw = getString(metadata.chosen_strategy ?? metadata.strategy);
  const variant = VARIANT_KEYS.find((key) => variantRaw === key) as ContentPreservingDiagnostics['variant'] | undefined;
  const densityRaw = getString(metadata.chosen_density ?? metadata.variant_density ?? metadata.density);
  const density = DENSITY_KEYS.find((key) => densityRaw === key) as ContentPreservingDiagnostics['density'] | undefined;
  const missingBlocksCount = getNumber(metadata.missing_required_blocks_count);
  const providerName = getString(metadata.provider_name);
  const durationMs = getNumber(metadata.duration_ms);
  const score = getNumber(metadata.variant_score);

  const usedFallbackRaw = metadata.used_fallback;
  const usedFallback = usedFallbackRaw === true || usedFallbackRaw === 'true' || usedFallbackRaw === 1;

  let fallbackCategory = undefined as ContentPreservingDiagnostics['fallbackCategory'] | undefined;
  if (usedFallback) {
    const rawCategory = getString(metadata.fallback_category);
    fallbackCategory = FALLBACK_CATEGORIES.find((key) => rawCategory === key) ?? 'unknown';
  }

  if (!variant) {
    return { present: false };
  }

  return {
    present: true,
    variant,
    density,
    missingBlocksCount,
    usedFallback,
    fallbackCategory,
    providerName,
    durationMs,
    score,
  };
}

export function formatCompactContentPreservingBadge(d: ContentPreservingDiagnostics): CompactContentPreservingBadge {
  if (!d.present || !d.variant) return { present: false };

  if (d.usedFallback) {
    return { present: true, label: 'CP · repli auto', tone: 'warning' };
  }

  const missing = typeof d.missingBlocksCount === 'number' ? Math.max(0, Math.floor(d.missingBlocksCount)) : 0;
  if (missing > 0) {
    const suffix = missing === 1 ? '1 bloc manquant' : `${missing} blocs manquants`;
    return { present: true, label: `CP · ${VARIANT_LABELS[d.variant]} · ${suffix}`, tone: 'warning' };
  }

  return { present: true, label: `CP · ${VARIANT_LABELS[d.variant]} · OK`, tone: 'ok' };
}

export function buildContentPreservingBadgeIndex(events: CvEvent[]): Record<string, CompactContentPreservingBadge> {
  const byRequest = new Map<string, CvEvent[]>();
  for (const event of events) {
    if (!event.request_id) continue;
    if (typeof event.event_type !== 'string' || !event.event_type.startsWith('content_preserving_')) continue;
    const list = byRequest.get(event.request_id) ?? [];
    list.push(event);
    byRequest.set(event.request_id, list);
  }

  const result: Record<string, CompactContentPreservingBadge> = {};
  for (const [requestId, requestEvents] of byRequest.entries()) {
    const diagnostics = extractContentPreservingDiagnostics(requestEvents);
    const badge = formatCompactContentPreservingBadge(diagnostics);
    if (badge.present) {
      result[requestId] = badge;
    }
  }
  return result;
}

export function formatDiagnosticForUser(d: ContentPreservingDiagnostics): string[] {
  if (!d.present) return [];
  const lines: string[] = [];

  if (d.variant === 'deterministic_content_preserving') {
    lines.push('Mise en page préservée');
  } else {
    lines.push('Diagnostic mise en page');
  }

  if (d.variant) {
    lines.push(`Variante: ${DETAIL_VARIANT_LABELS[d.variant]}`);
  }

  if (d.density) {
    lines.push(`Densité: ${d.density}`);
  }

  if (typeof d.missingBlocksCount === 'number') {
    const n = Math.max(0, Math.floor(d.missingBlocksCount));
    if (n === 1) {
      lines.push('Bloc manquant: 1');
    } else {
      lines.push(`Blocs manquants: ${n}`);
    }
  }

  if (d.usedFallback) {
    const fallbackLabels: Record<NonNullable<ContentPreservingDiagnostics['fallbackCategory']>, string> = {
      provider_unavailable: 'Fournisseur indisponible',
      invalid_response: 'Réponse invalide',
      validation_failed: 'Validation échouée',
      unknown: 'Erreur inconnue',
    };
    lines.push(`Repli automatique utilisé (${fallbackLabels[d.fallbackCategory ?? 'unknown']})`);
  }

  if (typeof d.score === 'number') {
    const score = Math.max(0, Math.min(1, d.score));
    lines.push(`Score: ${score.toFixed(2)}/1`);
  }

  if (typeof d.durationMs === 'number') {
    const durationMs = Math.max(0, d.durationMs);
    const seconds = durationMs / 1000;
    lines.push(`Génération: ${seconds.toFixed(1)}s`);
  }

  return lines;
}
