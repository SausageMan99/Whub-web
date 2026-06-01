import tempfile
import unittest
from pathlib import Path

import fitz

from src.qa import find_layout_issues, run_qa, QAError


class QALayoutTest(unittest.TestCase):
    def write_pdf(self, draw):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / 'layout.pdf'
        doc = fitz.open()
        draw(doc)
        doc.save(path)
        doc.close()
        self.addCleanup(tmp.cleanup)
        return path

    def add_page(self, doc):
        return doc.new_page(width=595, height=842)

    def issue_codes(self, pdf_path):
        doc = fitz.open(pdf_path)
        self.addCleanup(doc.close)
        return [issue['code'] for issue in find_layout_issues(doc)]

    def test_detects_dense_skill_block_and_skill_continuation_page(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 130), 'Compétences techniques', fontsize=13)
            dense = '; '.join(f'Technologie{i:02d} Kubernetes Terraform Azure Python FastAPI' for i in range(28))
            page.insert_textbox(fitz.Rect(54, 155, 540, 500), dense, fontsize=8)
            page2 = self.add_page(doc)
            page2.insert_text((54, 90), 'Cloud & DevOps (suite)', fontsize=12)
            page2.insert_text((54, 120), 'Expériences professionnelles', fontsize=13)

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('skills_too_dense', codes)
        self.assertIn('skill_block_too_long', codes)
        self.assertIn('skill_overflow_page_created', codes)

    def test_detects_experience_heading_orphaned_near_page_bottom(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 710), '2024 - Aujourd’hui', fontsize=9)
            page.insert_text((54, 732), 'ARCHITECTE CLOUD CHEZ CLIENT', fontsize=11)
            page2 = self.add_page(doc)
            page2.insert_text((54, 90), 'Missions clés', fontsize=10)
            page2.insert_text((54, 115), 'Architecture cible et accompagnement des équipes.', fontsize=9)

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('experience_orphan_heading', codes)
        self.assertIn('bad_page_break', codes)

    def test_detects_section_heading_orphaned_before_suite_even_if_page_underused(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 145), 'Mai 2017 à Mai 2023', fontsize=9)
            page.insert_text((54, 168), 'ASSURONE GROUP — PRODUCT OWNER LEADER | ASSURANCE', fontsize=10)
            page.insert_text((54, 520), 'PRESTATIONS REALISEE', fontsize=9)
            page2 = self.add_page(doc)
            page2.insert_text((54, 90), 'PRESTATIONS REALISEE (suite)', fontsize=9)
            page2.insert_text((67, 118), '• Refonte full responsive des anciens tunnels.', fontsize=8)

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('experience_section_orphan_heading', codes)
        self.assertIn('bad_page_break', codes)

    def test_detects_sparse_last_page_and_abnormally_dense_page(self):
        def draw(doc):
            page = self.add_page(doc)
            for i in range(58):
                page.insert_text((54, 45 + i * 13), f'Ligne dense {i:02d} avec détails projet, contexte, livrables et environnement technique complet', fontsize=8)
            last = self.add_page(doc)
            last.insert_text((54, 90), 'Langues', fontsize=11)
            last.insert_text((54, 115), 'Anglais professionnel', fontsize=9)

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('page_too_dense', codes)
        self.assertIn('last_page_sparse', codes)


    def test_detects_medium_sparse_last_experience_page(self):
        def draw(doc):
            for i in range(3):
                page = self.add_page(doc)
                for j in range(18):
                    page.insert_text((54, 80 + j * 18), f'Expérience {i} ligne {j} avec contenu professionnel utile', fontsize=9)
            last = self.add_page(doc)
            last.insert_text((54, 90), 'Octobre 2012 - Octobre 2015', fontsize=9)
            last.insert_text((54, 120), 'Apprenti ingénieur Méthodes/Bureau d’Etudes / SI LESAFFRE', fontsize=10)
            last.insert_textbox(
                fitz.Rect(67, 155, 535, 260),
                '• Assistance suivi de chantier, gestion de projet industriel, étude et mise en place d’une Gestion Electronique des Documents.\n'
                '• Mise en place et pilotage de l’analyse AMDEC maintenance sur l’ensemble de l’usine.',
                fontsize=8,
            )

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('last_page_sparse', codes)
        self.assertIn('page_too_sparse', codes)

    def test_detects_sparse_last_page_even_on_two_page_pdf(self):
        def draw(doc):
            page = self.add_page(doc)
            for i in range(30):
                page.insert_text((54, 70 + i * 18), f'Première page ligne {i:02d} avec contenu expérience détaillé et utile', fontsize=9)
            last = self.add_page(doc)
            last.insert_text((54, 90), 'Octobre 2012 - Octobre 2015', fontsize=9)
            last.insert_text((54, 120), 'Apprenti ingénieur Méthodes/Bureau d’Etudes / SI LESAFFRE', fontsize=10)
            last.insert_textbox(
                fitz.Rect(67, 155, 535, 245),
                '• Assistance suivi de chantier, gestion de projet industriel, étude et mise en place d’une GED.\n'
                '• Pilotage ponctuel de l’analyse AMDEC maintenance.',
                fontsize=8,
            )

        codes = self.issue_codes(self.write_pdf(draw))

        self.assertIn('last_page_sparse', codes)
        self.assertIn('page_too_sparse', codes)

    def test_detects_sparse_non_final_continuation_page_with_large_blank(self):
        def draw(doc):
            page1 = self.add_page(doc)
            for i in range(28):
                page1.insert_text((54, 70 + i * 18), f'Page initiale ligne {i:02d} avec contenu expérience détaillé et utile', fontsize=9)

            page2 = self.add_page(doc)
            page2.insert_text((54, 90), 'Missions (suite)', fontsize=10)
            page2.insert_textbox(
                fitz.Rect(67, 120, 535, 230),
                '• Finalisation de quelques ateliers métier.\n'
                '• Transmission des livrables clés et support ponctuel aux équipes.',
                fontsize=8,
            )

            page3 = self.add_page(doc)
            for i in range(24):
                page3.insert_text((54, 75 + i * 18), f'Page finale ligne {i:02d} avec éléments suffisants pour éviter une fin vide', fontsize=9)

        doc = fitz.open(self.write_pdf(draw))
        self.addCleanup(doc.close)
        issues = find_layout_issues(doc)
        sparse_pages = [issue['page'] for issue in issues if issue['code'] == 'page_too_sparse']

        self.assertIn(2, sparse_pages)

    def test_does_not_flag_normal_medium_non_final_page_as_sparse(self):
        def draw(doc):
            page1 = self.add_page(doc)
            for i in range(28):
                page1.insert_text((54, 70 + i * 18), f'Page initiale ligne {i:02d} avec contenu expérience détaillé et utile', fontsize=9)

            page2 = self.add_page(doc)
            for i in range(21):
                page2.insert_text((54, 80 + i * 22), f'Page intermédiaire équilibrée ligne {i:02d} avec contenu professionnel significatif', fontsize=9)

            page3 = self.add_page(doc)
            for i in range(24):
                page3.insert_text((54, 75 + i * 18), f'Page finale ligne {i:02d} avec éléments suffisants pour éviter une fin vide', fontsize=9)

        doc = fitz.open(self.write_pdf(draw))
        self.addCleanup(doc.close)
        issues = find_layout_issues(doc)
        page2_sparse = [issue for issue in issues if issue['code'] == 'page_too_sparse' and issue['page'] == 2]

        self.assertEqual(page2_sparse, [])

    def test_run_qa_fails_with_layout_issue_report(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 130), 'Compétences techniques', fontsize=13)
            dense = '; '.join(f'Item technique très long {i:02d}' for i in range(35))
            page.insert_textbox(fitz.Rect(54, 155, 540, 470), dense, fontsize=8)
            # Insert fake logo/watermark images so asset checks pass and layout failure is isolated.
            logo_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1051, 398), 0)
            wm_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1192, 1192), 0)
            page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=logo_pix)
            page.insert_image(fitz.Rect(400, 700, 500, 800), pixmap=wm_pix)

        with self.assertRaises(QAError) as ctx:
            run_qa(self.write_pdf(draw))

        report = ctx.exception.report
        self.assertFalse(report['passed'])
        self.assertIn('layout_issues', report)
        self.assertIn('human_taste', report)
        self.assertIn('layout_metrics', report)
        self.assertLess(report['human_taste']['score'], 100)
        self.assertIn('skills_too_dense', [issue['code'] for issue in report['layout_issues']])

    def test_does_not_classify_experience_bullets_as_skills_after_experience_heading(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 110), 'Expériences professionnelles', fontsize=13)
            page.insert_text((54, 145), 'Mai 2017 à Mai 2023', fontsize=9)
            page.insert_text((54, 168), 'ASSURONE GROUP — PRODUCT OWNER LEADER | ASSURANCE', fontsize=10)
            page.insert_text((54, 200), 'PRESTATIONS REALISEE', fontsize=9)
            long_bullet = (
                '• Coordination avec les teams en tant que pivot central d’intégration : produit, architectes, SSO, infra, '
                'paiement, signature électronique, éditiques, conformité, APIs, CRC, paramétrage du CTI dans ISICOM, '
                'priorisation des anomalies, sécurisation de la MEP, run et accompagnement métier sur plusieurs parcours.'
            )
            page.insert_textbox(fitz.Rect(67, 225, 535, 390), long_bullet, fontsize=8)

        doc = fitz.open(self.write_pdf(draw))
        self.addCleanup(doc.close)
        issues = find_layout_issues(doc)
        skill_issues = [issue for issue in issues if issue['code'] in {'skill_block_too_long', 'skills_too_dense'}]

        self.assertEqual(skill_issues, [])

    def test_resets_skill_area_when_dated_experience_starts_without_exp_heading(self):
        def draw(doc):
            page = self.add_page(doc)
            page.insert_text((54, 110), 'Compétences techniques', fontsize=13)
            page.insert_text((54, 140), 'Power BI, SQL', fontsize=9)
            page.insert_text((54, 180), 'Juin 2023 à ce jour', fontsize=9)
            page.insert_text((54, 205), 'CHEF DE PROJET | GROUPE KLESIA | PROTECTION SOCIALE', fontsize=10)
            long_bullet = (
                '• Pilotage recette transverse avec ateliers, cadrage, coordination métier, préparation des comités, '
                'suivi anomalies, priorisation, accompagnement utilisateurs et synchronisation des équipes projet.'
            )
            page.insert_textbox(fitz.Rect(67, 235, 535, 390), long_bullet, fontsize=8)

        doc = fitz.open(self.write_pdf(draw))
        self.addCleanup(doc.close)
        issues = find_layout_issues(doc)
        skill_issues = [issue for issue in issues if issue['code'] in {'skill_block_too_long', 'skills_too_dense'}]

        self.assertEqual(skill_issues, [])


if __name__ == '__main__':
    unittest.main()
