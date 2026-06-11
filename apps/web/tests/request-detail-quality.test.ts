import test from 'node:test';
import assert from 'node:assert/strict';
import { renderToString } from 'react-dom/server';

test('request detail page — surfaces a redacted quality summary on ready/draft', async (t) => {
  let request: any = null;
  let versions: any[] = [];
  const comments: any[] = [];
  const events: any[] = [];

  t.mock.module('next/navigation', {
    namedExports: { redirect: (url: string) => { throw new Error(`REDIRECT ${url}`); } },
  });
  t.mock.module('@/components/AutoRefreshWhenActive', {
    namedExports: { AutoRefreshWhenActive: () => null },
  });
  t.mock.module('@/app/requests/[id]/actions', {
    namedExports: { addComment: async () => {}, retryRequest: async () => {} },
  });
  t.mock.module('@/lib/supabase/admin', {
    namedExports: {
      createSupabaseAdminClient: () => ({
        from(table: string) {
          return {
            select() {
              return {
                eq() {
                  if (table === 'cv_requests') return { single: async () => ({ data: request, error: null }) };
                  if (table === 'cv_versions') return { order: async () => ({ data: versions, error: null }) };
                  if (table === 'cv_comments') return { order: async () => ({ data: comments, error: null }) };
                  if (table === 'cv_events') return { order: async () => ({ data: events, error: null }) };
                  return { single: async () => ({ data: null, error: null }) };
                },
              };
            },
          };
        },
      }),
    },
  });

  const { default: RequestDetailPage } = await import('../app/requests/[id]/page');

  request = {
    id: 'req-quality',
    status: 'ready',
    title: 'CV Alice',
    candidate_first_name: 'Alice',
    priority: 'normal',
    instructions: '',
    source_file_name: 'alice.pdf',
    source_file_mime: 'application/pdf',
  };
  versions = [
    {
      id: 'v1',
      version_number: 1,
      final_pdf_path: 'req-quality/final/v1.pdf',
      qa_status: 'passed',
      qa_report: {
        quality_report: {
          source_profile: 'senior_long',
          scores: { extraction: 88, fidelity: 92, layout: 76, overall: 76 },
          hard_blockers: [],
          soft_warnings: [{ code: 'last_page_sparse', stage: 'layout', page: 4 }],
          metrics: { pages: 4, attempts_count: 2, total_duration_seconds: 31.2 },
        },
      },
    },
  ];

  const element = await RequestDetailPage({ params: Promise.resolve({ id: 'req-quality' }) });
  const html = renderToString(element);

  // The summary section must be present, with safe business labels.
  assert.match(html, /Qualité CV/);
  assert.match(html, /CV senior long/);
  assert.match(html, /Score global/);
  // React renderToString inserts a <!-- --> between adjacent text nodes,
  // so the score is emitted as e.g. "76<!-- -->/100" in the HTML stream.
  assert.match(html, /76<!-- -->\/100/);
  assert.match(html, /4 pages/);
  assert.match(html, /Dernière page trop vide/);
  // It must never include raw source text or contact values.
  assert.doesNotMatch(html, /test@example\.com/);
  assert.doesNotMatch(html, /payload|stack|json|trace/i);
});
