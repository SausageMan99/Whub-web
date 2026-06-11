import test from 'node:test';
import assert from 'node:assert/strict';
import {
  draftReadyTitle,
  hardFailureCopy,
  isHardFailureStatus,
  normalizeDraftWarnings,
  normalizeQualitySummary,
  safeRetryCopy,
} from "../lib/request-detail-ui";

test("request detail UI — draftReadyTitle stays clear for draft_ready", () => {
  assert.equal(draftReadyTitle("draft_ready"), "Brouillon prêt — points qualité détectés");
  assert.equal(draftReadyTitle("completed"), null);
  assert.equal(draftReadyTitle("ready"), null);
});

test("request detail UI — hard failure copy stays safe without technical details", () => {
  const failed = hardFailureCopy("failed");
  assert.equal(failed?.title, "À corriger — génération impossible");
  assert.match(failed?.body ?? "", /PDF source/);
  assert.doesNotMatch(failed?.body ?? "", /payload|stack|json|trace/i);

  const qa = hardFailureCopy("qa_failed");
  assert.equal(qa?.title, "Contrôle qualité — PDF non livrable");
  assert.match(qa?.body ?? "", /source|consigne/);
  assert.doesNotMatch(qa?.body ?? "", /payload|stack|json|trace/i);
});

test('request detail UI — formats draft layout warnings without internal noise', () => {
  const warnings = normalizeDraftWarnings({
    layout_issues: [
      {
        code: 'page_too_dense',
        page: 2,
        message: 'Page 2 anormalement dense: 3200 caractères, 44 blocs',
      },
      {
        code: 'skill_block_too_long',
        page: 1,
        snippet: 'Cloud / DevOps AWS Azure Docker Kubernetes Terraform Helm',
      },
    ],
  });

  assert.deepEqual(warnings, [
    'Page 2 · Page trop dense — Page 2 anormalement dense: 3200 caractères, 44 blocs',
    'Page 1 · Bloc de compétences trop long — Cloud / DevOps AWS Azure Docker Kubernetes Terraform Helm',
  ]);
  assert.doesNotMatch(warnings.join(' '), /payload|stack|json|trace/i);
});

test('request detail UI — returns empty warnings when qa_report is absent or malformed', () => {
  assert.deepEqual(normalizeDraftWarnings(null), []);
  assert.deepEqual(normalizeDraftWarnings({ layout_issues: 'not-an-array' }), []);
});

test('request detail UI — completed status has no draft or failure copy', () => {
  assert.equal(draftReadyTitle('ready'), null);
  assert.equal(hardFailureCopy('ready'), null);
  assert.equal(isHardFailureStatus('ready'), false);
});

test("request detail UI — safe retry copy uses business wording only", () => {
  assert.deepEqual(safeRetryCopy("ready"), null);
  assert.deepEqual(safeRetryCopy("failed"), { label: "Relancer la génération" });
  assert.deepEqual(safeRetryCopy("dead_letter"), { label: "Relancer la génération" });
  assert.deepEqual(safeRetryCopy("qa_failed", "Alice"), {
    label: "Relancer Alice",
    hint: "La prochaine version pour Alice repart depuis le même CV source et la même consigne.",
  });
  assert.deepEqual(safeRetryCopy("qa_failed"), {
    label: "Relancer la génération",
    hint: "La prochaine version repart depuis le même CV source et la même consigne.",
  });
});

test("request detail UI — needs_human_review is its own category (not hard failure)", () => {
  // It is a recoverable, instructional status. It must NOT be classified as a
  // hard failure (which would block PDF download) and must NOT be a draft
  // brouillon (no PDF was produced).
  assert.equal(isHardFailureStatus("needs_human_review"), false);
  assert.equal(draftReadyTitle("needs_human_review"), null);

  // Hard failure copy returns a structured block explaining the manual check.
  const humanReview = hardFailureCopy("needs_human_review");
  assert.equal(humanReview?.title, "Validation humaine requise");
  assert.match(humanReview?.body ?? "", /humain|humaine|validation|relire/i);
  assert.doesNotMatch(humanReview?.body ?? "", /payload|stack|json|trace/i);

  // Retry copy uses instructional wording rather than "relancer".
  const retry = safeRetryCopy("needs_human_review", "Alice");
  assert.match(retry?.label ?? "", /Vérifier|validation|relire/i);
  assert.match(retry?.hint ?? "", /Alice/);
});

test("request detail UI — needs_human_review still exposes a retry action", () => {
  const retry = safeRetryCopy("needs_human_review", "Alice");
  assert.ok(retry?.label, "label must be set");
  assert.ok(retry?.hint, "hint must be set");
});

test("request detail UI — normalizeQualitySummary exposes safe labels only", () => {
  const qaReport = {
    quality_report: {
      source_profile: "senior_long",
      scores: { extraction: 88, fidelity: 82, layout: 76, overall: 76 },
      hard_blockers: [],
      soft_warnings: [
        { code: "last_page_sparse", stage: "layout", page: 4 },
        { code: "source_fidelity_soft_warning", stage: "fidelity" },
      ],
      metrics: { pages: 4, attempts_count: 2, total_duration_seconds: 31.2 },
    },
  };

  const summary = normalizeQualitySummary(qaReport);

  assert.equal(summary?.sourceProfileLabel, "CV senior long");
  assert.equal(summary?.scores.overall, 76);
  assert.deepEqual(summary?.metrics, ["4 pages", "2 variantes testées", "31.2s"]);
  assert.equal(summary?.warnings.length, 2);
});

test("request detail UI — normalizeQualitySummary returns null on missing block", () => {
  assert.equal(normalizeQualitySummary(null), null);
  assert.equal(normalizeQualitySummary({}), null);
  assert.equal(normalizeQualitySummary({ quality_report: "nope" }), null);
});

test("request detail UI — normalizeQualitySummary never leaks raw contact values", () => {
  const qaReport = {
    quality_report: {
      source_profile: "ats",
      scores: { overall: 80 },
      hard_blockers: [
        { code: "contact_leak", stage: "structuring", detail: "test@example.com" },
      ],
      soft_warnings: [],
      metrics: {},
    },
  };

  // The contract is "safe labels only": raw contact strings must not
  // survive the normalization pass.
  const summary = normalizeQualitySummary(qaReport);
  const repr = JSON.stringify(summary);
  assert.equal(repr.includes("test@example.com"), false);
});

test("request detail UI — normalizeQualitySummary covers all known source profiles", () => {
  const profiles = [
    "normal",
    "senior_long",
    "ats",
    "scanned",
    "two_column",
    "graphic",
    "risky",
    "unknown",
  ];
  for (const profile of profiles) {
    const summary = normalizeQualitySummary({
      quality_report: {
        source_profile: profile,
        scores: { overall: 50 },
        hard_blockers: [],
        soft_warnings: [],
        metrics: {},
      },
    });
    assert.ok(summary?.sourceProfileLabel, `${profile} should map to a label`);
  }
});
