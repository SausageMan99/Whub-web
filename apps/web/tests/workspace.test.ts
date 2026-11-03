import test from "node:test";
import assert from "node:assert/strict";
import {
  currentStep,
  currentValidation,
  groupFor,
  numberVersions,
  proofNotes,
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
