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
  assert.match(draftHtml, /Brouillon prêt — points qualité détectés/);
  assert.match(draftHtml, /Télécharger le brouillon/);
  assert.match(draftHtml, /Page 2 · Page trop dense — Page 2 anormalement dense/);
  assert.match(draftHtml, /Correction post-génération/);
  assert.match(draftHtml, /Créer V/);

  const readyHtml = await render('ready');
  assert.match(readyHtml, /Prêt à télécharger/);
  assert.match(readyHtml, /Télécharger/);
  assert.match(readyHtml, /Créer V/);
  assert.match(readyHtml, /même source pour V2\/V3/);
  assert.doesNotMatch(readyHtml, /Brouillon prêt/);
  assert.doesNotMatch(readyHtml, /PDF bloqué/);

  const failedHtml = await render('failed');
  assert.match(failedHtml, /À corriger — génération impossible/);
  assert.match(failedHtml, /Relancer la génération/);

  const qaFailedHtml = await render('qa_failed');
  assert.match(qaFailedHtml, /Contrôle qualité — PDF non livrable/);
  assert.doesNotMatch(qaFailedHtml, /Relancer la génération/);
  assert.match(qaFailedHtml, /PDF bloqué/);
  assert.doesNotMatch(qaFailedHtml, /Télécharger le brouillon/);
});
