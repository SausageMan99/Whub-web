import test from 'node:test';
import assert from 'node:assert/strict';
import { renderToString } from 'react-dom/server';

test('request detail page — renders draft_ready, completed and hard failure states', async (t) => {
  let request: any = null;
  let versions: any[] = [];
  const comments: any[] = [];
  const events: any[] = [];

  t.mock.module('next/navigation', {
    namedExports: {
      redirect: (url: string) => {
        throw new Error(`REDIRECT ${url}`);
      },
    },
  });

  t.mock.module('@/components/AutoRefreshWhenActive', {
    namedExports: {
      AutoRefreshWhenActive: () => null,
    },
  });

  t.mock.module('@/app/requests/[id]/actions', {
    namedExports: {
      addComment: async () => {},
      retryRequest: async () => {},
    },
  });

  t.mock.module('@/lib/supabase/server', {
    namedExports: {
      createSupabaseServerClient: async () => ({
        auth: {
          getUser: async () => ({ data: { user: { id: 'u1', email: 'test@whub.fr' } } }),
        },
        from(table: string) {
          return {
            select() {
              return {
                eq() {
                  if (table === 'cv_requests') {
                    return { single: async () => ({ data: request, error: null }) };
                  }
                  if (table === 'cv_versions') {
                    return { order: async () => ({ data: versions, error: null }) };
                  }
                  if (table === 'cv_comments') {
                    return { order: async () => ({ data: comments, error: null }) };
                  }
                  if (table === 'cv_events') {
                    return { order: async () => ({ data: events, error: null }) };
                  }
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

  async function render(status: string, qaReport: any = null) {
    request = {
      id: 'req1',
      status,
      title: 'CV Alice',
      candidate_first_name: 'Alice',
      priority: 'normal',
      instructions: 'CV standard W hub',
      source_file_name: 'alice.pdf',
      source_file_mime: 'application/pdf',
    };
    versions = [
      {
        id: 'v1',
        version_number: 1,
        final_pdf_path: 'req1/final/v1.pdf',
        qa_status: status === 'draft_ready' ? 'draft' : status === 'ready' ? 'passed' : 'failed',
        qa_report: qaReport,
      },
    ];

    const element = await RequestDetailPage({ params: Promise.resolve({ id: 'req1' }) });
    return renderToString(element);
  }

  const draftHtml = await render('draft_ready', {
    layout_issues: [{ code: 'page_too_dense', page: 2, message: 'Page 2 anormalement dense' }],
  });
  assert.match(draftHtml, /PDF généré en brouillon — points qualité détectés/);
  assert.match(draftHtml, /Télécharger le brouillon/);
  assert.match(draftHtml, /Page 2 · Page trop dense — Page 2 anormalement dense/);
  assert.match(draftHtml, /Que veux-tu modifier \?/);

  const readyHtml = await render('ready');
  assert.match(readyHtml, /CV prêt/);
  assert.match(readyHtml, /Télécharger/);
  assert.doesNotMatch(readyHtml, /PDF généré en brouillon/);
  assert.doesNotMatch(readyHtml, /PDF bloqué/);

  const failedHtml = await render('qa_failed');
  assert.match(failedHtml, /Erreur bloquante — PDF non livrable/);
  assert.match(failedHtml, /Relancer la génération/);
  assert.match(failedHtml, /PDF bloqué/);
  assert.doesNotMatch(failedHtml, /Télécharger le brouillon/);
});
