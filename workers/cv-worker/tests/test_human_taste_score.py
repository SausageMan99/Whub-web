import tempfile
import unittest
from pathlib import Path

import fitz

from src.qa import collect_page_layout_metrics, find_layout_issues, score_human_taste


class HumanTasteScoreTest(unittest.TestCase):
    def write_pdf(self, draw):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "taste.pdf"
        doc = fitz.open()
        draw(doc)
        doc.save(path)
        doc.close()
        self.addCleanup(tmp.cleanup)
        return path

    def add_page(self, doc):
        return doc.new_page(width=595, height=842)

    def score_pdf(self, pdf_path):
        doc = fitz.open(pdf_path)
        self.addCleanup(doc.close)
        metrics = collect_page_layout_metrics(doc)
        issues = find_layout_issues(doc)
        return score_human_taste(metrics, issues), issues

    def test_balanced_medium_pdf_gets_good_score_with_page_level_evidence(self):
        def draw(doc):
            for page_index in range(3):
                page = self.add_page(doc)
                page.insert_text((54, 70), "Expériences professionnelles", fontsize=12)
                for i in range(24):
                    page.insert_text(
                        (54, 105 + i * 19),
                        f"Page {page_index + 1} ligne {i:02d} contenu professionnel lisible et équilibré",
                        fontsize=9,
                    )

        score, issues = self.score_pdf(self.write_pdf(draw))

        self.assertEqual(issues, [])
        self.assertEqual(score["verdict"], "good")
        self.assertGreaterEqual(score["score"], 86)
        self.assertEqual(len(score["page_metrics"]), 3)
        self.assertNotIn("blocks", score["page_metrics"][0])
        self.assertNotIn("text", score["page_metrics"][0])

    def test_sparse_continuation_tail_is_penalized_actionably(self):
        def draw(doc):
            page1 = self.add_page(doc)
            for i in range(30):
                page1.insert_text((54, 70 + i * 18), f"Mission longue ligne {i:02d} avec contenu utile", fontsize=9)
            page2 = self.add_page(doc)
            page2.insert_text((54, 90), "Missions (suite)", fontsize=10)
            page2.insert_textbox(
                fitz.Rect(67, 120, 535, 230),
                "• Finalisation des ateliers.\n• Transmission des livrables.",
                fontsize=8,
            )
            page3 = self.add_page(doc)
            for i in range(24):
                page3.insert_text((54, 75 + i * 18), f"Expérience suivante ligne {i:02d} suffisamment remplie", fontsize=9)

        score, issues = self.score_pdf(self.write_pdf(draw))
        codes = {issue["code"] for issue in issues}
        penalty_codes = {penalty["code"] for penalty in score["penalties"]}

        self.assertIn("page_too_sparse", codes)
        self.assertIn("continuation_tail_page", penalty_codes)
        self.assertLess(score["score"], 70)
        self.assertEqual(score["verdict"], "poor")

    def test_two_page_sparse_final_experience_is_not_scored_good(self):
        def draw(doc):
            page1 = self.add_page(doc)
            for i in range(31):
                page1.insert_text((54, 70 + i * 18), f"Mission principale ligne {i:02d} avec contenu professionnel utile", fontsize=9)
            page2 = self.add_page(doc)
            page2.insert_text((54, 90), "Octobre 2012 - Octobre 2015", fontsize=9)
            page2.insert_text((54, 120), "Apprenti ingénieur Méthodes/Bureau d’Etudes / SI LESAFFRE", fontsize=10)
            page2.insert_textbox(
                fitz.Rect(67, 155, 535, 245),
                "• Assistance suivi de chantier, gestion de projet industriel, étude et mise en place d’une GED.\n"
                "• Pilotage ponctuel de l’analyse AMDEC maintenance.",
                fontsize=8,
            )

        score, issues = self.score_pdf(self.write_pdf(draw))
        codes = {issue["code"] for issue in issues}
        penalty_codes = {penalty["code"] for penalty in score["penalties"]}

        self.assertIn("last_page_sparse", codes)
        self.assertIn("page_too_sparse", codes)
        self.assertIn("last_page_sparse", penalty_codes)
        self.assertIn("page_too_sparse", penalty_codes)
        self.assertNotEqual(score["verdict"], "good")
        self.assertLess(score["score"], 86)

    def test_dense_page_and_orphan_heading_drive_poor_score(self):
        def draw(doc):
            page1 = self.add_page(doc)
            for i in range(62):
                page1.insert_text((54, 45 + i * 12), f"Ligne dense {i:02d} détails projet contexte livrables environnement", fontsize=8)
            page2 = self.add_page(doc)
            page2.insert_text((54, 710), "2024 - Aujourd’hui", fontsize=9)
            page2.insert_text((54, 732), "ARCHITECTE CLOUD CHEZ CLIENT", fontsize=11)
            page3 = self.add_page(doc)
            page3.insert_text((54, 90), "Missions clés", fontsize=10)
            page3.insert_text((54, 115), "Architecture cible et accompagnement des équipes.", fontsize=9)

        score, issues = self.score_pdf(self.write_pdf(draw))
        codes = {issue["code"] for issue in issues}
        penalty_codes = {penalty["code"] for penalty in score["penalties"]}

        self.assertIn("page_too_dense", codes)
        self.assertIn("experience_orphan_heading", codes)
        self.assertIn("bad_page_break", codes)
        self.assertIn("page_too_dense", penalty_codes)
        self.assertIn("experience_orphan_heading", penalty_codes)
        self.assertEqual(score["verdict"], "poor")
        self.assertLess(score["score"], 70)


if __name__ == "__main__":
    unittest.main()
