import test from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";

test("demande page — renders review, ready, blocked and in-progress states in plain words", async (t) => {
  let data: any = null;

  t.mock.module("next/navigation", {
    namedExports: {
      notFound: () => { throw new Error("NOT_FOUND"); },
      redirect: (url: string) => { throw new Error(`REDIRECT ${url}`); },
      useRouter: () => ({ refresh() {}, push() {}, replace() {} }),
      usePathname: () => "/demandes/req1",
      useSearchParams: () => new URLSearchParams(),
    },
  });
  t.mock.module("@/components/AutoRefreshWhenActive", { namedExports: { AutoRefreshWhenActive: () => null } });
  t.mock.module("@/app/requests/[id]/actions", {
    namedExports: { addComment: async () => {}, retryRequest: async () => ({ ok: true }), markReadyToSend: async () => {} },
  });
  t.mock.module("@/lib/workspace-data", { namedExports: { loadRequest: async () => data, loadQueue: async () => [] } });

  const { default: DemandePage } = await import("../app/demandes/[id]/page");
  const render = async () => renderToString(await DemandePage({ params: Promise.resolve({ id: "req1" }) }));

  const version = (id: string, ordinal: number, qa_report: unknown = null) => ({
    id, ordinal, version_number: 240 + ordinal, created_at: `2026-11-03T0${ordinal}:00:00Z`,
    final_pdf_path: `req1/final/${id}.pdf`, qa_status: "failed", qa_report, poste: "Data Scientist",
  });
  const base = {
    request: { id: "req1", candidate_first_name: "Alice", title: "CV source", status: "draft_ready", instructions: "", source_file_name: "CV_Alice_Martin.pdf", created_at: "2026-11-03T00:00:00Z", updated_at: null },
    comments: [{ id: "c1", body: "Remonte la mission BNP.", created_at: "2026-11-03T01:30:00Z", metadata: { author: "Sarah" } }],
    step: 0,
    validation: null,
  };

  data = {
    ...base,
    group: "relire",
    versions: [version("v1", 1), version("v2", 2, { layout_issues: [{ code: "last_page_sparse", page: 2, used_ratio: 0.12 }] })],
  };
  const review = await render();
  assert.match(review, /À relire/);
  assert.match(review, /Marquer prêt à envoyer/);
  assert.match(review, /Télécharger l’épreuve/);
  assert.match(review, /Dernière page presque vide/);
  assert.match(review, /Sarah/);
  assert.match(review, /V<!-- -->2</);
  assert.doesNotMatch(review, /V24[0-9]|Version 24[0-9]/, "the global version sequence must not leak");
  assert.doesNotMatch(review, /Martin/, "the source file name (with the surname) must not be shown");
  assert.doesNotMatch(review, /last_page_sparse|payload|qa_report/);

  data = { ...base, request: { ...base.request, status: "ready" }, group: "pret", validation: { by: "Sarah", at: "2026-11-03T03:00:00Z" }, versions: [version("v1", 1)] };
  const ready = await render();
  assert.match(ready, /Prêt à envoyer/);
  assert.match(ready, /validé par Sarah/);
  assert.match(ready, /Télécharger le PDF/);
  assert.match(ready, /Remettre à relire/);

  data = { ...base, request: { ...base.request, status: "needs_human_review" }, group: "bloque", versions: [] };
  const blocked = await render();
  assert.match(blocked, /Le CV source est illisible/);
  assert.match(blocked, /Relancer la mise au format/);

  data = { ...base, request: { ...base.request, status: "processing" }, group: "fab", step: 2, versions: [] };
  const busy = await render();
  assert.match(busy, /Mise au format en cours/);
  assert.match(busy, /Mise au format W hub<span class="sr-only"> \(en cours\)/);
});
