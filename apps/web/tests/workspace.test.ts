import test from "node:test";
import assert from "node:assert/strict";
import {
  blockedReason,
  currentStep,
  currentValidation,
  groupFor,
  numberVersions,
  proofNotes,
  reviewLine,
  shortAgo,
  stepLine,
  guessFirstName,
} from "../lib/workspace";

test("workspace — versions are numbered per request, not by the global sequence", () => {
  const numbered = numberVersions([
    { id: "b", version_number: 247, created_at: "2026-11-03T10:00:00Z" },
    { id: "a", version_number: 246, created_at: "2026-11-03T09:00:00Z" },
  ]);
  assert.deepEqual(numbered.map((v) => [v.id, v.ordinal]), [["a", 1], ["b", 2]]);
});

test("workspace — groups requests by the action they need", () => {
  assert.equal(groupFor("submitted", false), "fab");
  assert.equal(groupFor("revision_requested", false), "fab");
  assert.equal(groupFor("draft_ready", false), "relire");
  assert.equal(groupFor("ready", false), "relire");
  assert.equal(groupFor("ready", true), "pret");
  assert.equal(groupFor("needs_human_review", false), "bloque");
  assert.equal(groupFor("qa_failed", false), "bloque");
  assert.equal(groupFor("archived", false), null);
});

test("workspace — a validation only counts for the latest version and can be cancelled", () => {
  const latest = { id: "v2", created_at: "2026-11-03T10:00:00Z" };
  const validated = [{ event_type: "human_validated", payload: { version_id: "v2", by: "Sarah" }, created_at: "2026-11-03T10:05:00Z" }];
  assert.deepEqual(currentValidation(validated, latest), { by: "Sarah", at: "2026-11-03T10:05:00Z" });

  const olderVersion = [{ event_type: "human_validated", payload: { version_id: "v1", by: "Sarah" }, created_at: "2026-11-03T10:05:00Z" }];
  assert.equal(currentValidation(olderVersion, latest), null);

  const cancelled = [...validated, { event_type: "human_validation_cancelled", payload: { version_id: "v2" }, created_at: "2026-11-03T10:06:00Z" }];
  assert.equal(currentValidation(cancelled, latest), null);
  assert.equal(currentValidation(validated, null), null);
});

test("workspace — the current step only looks at the current attempt", () => {
  const events = [
    { event_type: "worker_claimed", created_at: "2026-11-03T09:00:00Z" },
    { event_type: "extraction_done", created_at: "2026-11-03T09:01:00Z" },
    { event_type: "quality_source_profiled", created_at: "2026-11-03T09:02:00Z" },
    { event_type: "revision_requested", created_at: "2026-11-03T10:00:00Z" },
  ];
  assert.equal(currentStep("revision_requested", events), 0);
  assert.equal(currentStep("processing", [...events, { event_type: "worker_claimed", created_at: "2026-11-03T10:01:00Z" }]), 1);
  assert.equal(currentStep("processing", events.slice(0, 2)), 2);
  assert.match(stepLine(2), /Étape 3 sur 5, mise en page/);
});

test("workspace — proof notes are readable, merged and never expose raw codes", () => {
  const notes = proofNotes({
    layout_issues: [
      { code: "last_page_sparse", page: 2, message: "Dernière page trop peu remplie: 196 caractères", used_ratio: 0.122 },
      { code: "page_too_sparse", page: 2, message: "Page 2 trop peu remplie", used_ratio: 0.122 },
    ],
    quality_report: { soft_warnings: [{ code: "title_absent_from_source", stage: "final" }, { code: "something_new", stage: "final" }] },
  });
  assert.equal(notes.length, 3);
  assert.equal(notes[0].title, "Dernière page presque vide");
  assert.equal(notes[0].detail, "Remplie à 12 %.");
  assert.equal(notes[0].page, 2);
  assert.ok(notes.some((n) => n.title === "Intitulé de poste reformulé" && n.fix));
  assert.ok(notes.some((n) => n.title === "Point à vérifier"));
  for (const n of notes) assert.doesNotMatch(`${n.title} ${n.detail}`, /_|caractères/);
  assert.deepEqual(proofNotes(null), []);
});

test("workspace — short relative times", () => {
  const now = Date.parse("2026-11-03T12:00:00Z");
  assert.equal(shortAgo("2026-11-03T11:22:00Z", now), "38 min");
  assert.equal(shortAgo("2026-11-03T09:00:00Z", now), "3 h");
  assert.equal(shortAgo("2026-11-02T10:00:00Z", now), "hier");
});

test("new CV — guesses the first name from the file name", () => {
  assert.equal(guessFirstName("CV_Ines_Martin.pdf"), "Ines");
  assert.equal(guessFirstName("CV-Thibaut-Chabert.pdf"), "Thibaut");
  assert.equal(guessFirstName("cv final (1).pdf"), "");
});

test("workspace — blocking defects come first, in French, with a correction to propose", () => {
  const notes = proofNotes({
    layout_issues: [{ code: "skills_too_dense", page: 1 }],
    quality_report: {
      hard_blockers: [
        { code: "truncated_text", stage: "qa", content_loss: false, count: 1 },
        { code: "heading_orphaned_at_page_bottom", stage: "qa", page: 2, content_loss: false },
      ],
      soft_warnings: [
        { code: "future_end_date", stage: "qa" },
        { code: "page_underfilled", stage: "qa", page: 2, fill: 0.52 },
        { code: "last_page_nearly_empty", stage: "qa", page: 3, fill: 0.2 },
        { code: "content_language_not_french", stage: "qa" },
      ],
    },
  });
  assert.deepEqual(notes.slice(0, 2).map((n) => [n.title, n.blocking]), [["Titre seul en bas de page", true], ["Phrase coupée", true]]);
  assert.ok(notes.slice(2).every((n) => !n.blocking));
  assert.match(notes[0].detail, /à corriger avant l’envoi/);
  assert.equal(notes[1].fix?.label, "Reprendre le texte complet");
  assert.ok(notes.some((n) => n.title === "Page peu remplie" && n.detail === "Remplie à 52 %." && n.fix));
  assert.ok(notes.some((n) => n.title === "Dernière page presque vide" && n.page === 3));
  assert.ok(notes.some((n) => n.title === "Date dans le futur"));
  assert.ok(notes.some((n) => n.title === "CV en anglais" && n.fix?.text.includes("français")));
  for (const n of notes) assert.doesNotMatch(`${n.title} ${n.detail}`, /_|Point à vérifier/);
});

test("workspace — every QA code of the worker has a French note", () => {
  const codes = [
    "content_missing_from_pdf", "text_overflow", "truncated_text", "page_nearly_empty", "heading_orphaned_at_page_bottom",
    "placeholder_printed", "page_furniture_printed", "page_underfilled", "last_page_nearly_empty", "short_continuation",
    "first_page_without_experience", "truncated_in_source", "future_end_date", "content_language_not_french",
    "description_too_short", "company_field_sentence", "broken_ligature", "experience_order_unverified",
    "prompt_source_truncated", "certification_kept_unverified", "skills_cleanup", "pagination_revision_applied",
    "pagination_revision_not_possible",
  ];
  for (const code of codes) {
    const [note] = proofNotes({ quality_report: { soft_warnings: [{ code, stage: "qa" }] } });
    assert.notEqual(note.title, "Point à vérifier", code);
  }
  // qa_failed is an engine code, not a point for the reviewer.
  assert.deepEqual(proofNotes({ quality_report: { hard_blockers: [{ code: "qa_failed", stage: "qa" }] } }), []);
});

test("workspace — a pagination request that cannot be applied says why", () => {
  const message = "Impossible de passer sous 2 pages sans retirer de contenu : le texte remplit réellement les pages (100 % / 79 %).";
  const notes = proofNotes({
    revision_pagination: { goal: "fewer_pages", improved: false, message },
    quality_report: { soft_warnings: [{ code: "pagination_revision_not_possible", stage: "layout", previous_pages: 2, new_pages: 2 }] },
  });
  assert.equal(notes[0].title, "Mise en page déjà au plus juste");
  assert.equal(notes[0].detail, message);
  assert.equal(notes[0].fix?.label, "Raccourcir le CV");
  const applied = proofNotes({ quality_report: { soft_warnings: [{ code: "pagination_revision_applied", stage: "layout", previous_pages: 6, new_pages: 3 }] } });
  assert.match(applied[0].detail, /6 page\(s\) avant, 3 maintenant/);
});

test("workspace — review table line counts defects to fix apart", () => {
  assert.equal(reviewLine(2, 0, 0), "Version 2, aucun point signalé");
  assert.equal(reviewLine(1, 3, 0), "Version 1, 3 points à vérifier");
  assert.equal(reviewLine(3, 3, 1), "Version 3, 1 défaut à corriger, 2 points à vérifier");
  assert.equal(reviewLine(1, 2, 2), "Version 1, 2 défauts à corriger");
});

test("workspace — lost content gets its own blocked reason", () => {
  const lost = blockedReason("qa_failed", { quality_report: { hard_blockers: [{ code: "content_missing_from_pdf", content_loss: true }] } });
  assert.equal(lost.title, "Du contenu manque dans le PDF");
  assert.equal(lost.action, null);
  assert.equal(blockedReason("qa_failed").title, "Le contrôle a bloqué le PDF");
  assert.equal(blockedReason("qa_failed", { quality_report: { hard_blockers: [{ code: "truncated_text" }] } }).title, "Le contrôle a bloqué le PDF");
});
