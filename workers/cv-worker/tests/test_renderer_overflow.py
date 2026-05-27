import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import fitz


RENDERER = Path('/root/.hermes/scripts/whub_cv_renderer.py')


class RendererOverflowTest(unittest.TestCase):
    def render(self, data):
        tmp = tempfile.TemporaryDirectory()
        workdir = Path(tmp.name)
        input_path = workdir / 'input.json'
        output_path = workdir / 'output.pdf'
        input_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        result = subprocess.run(
            [sys.executable, str(RENDERER), str(input_path), str(output_path)],
            text=True,
            capture_output=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.addCleanup(tmp.cleanup)
        return output_path

    def assert_no_text_below_margin(self, pdf_path, margin=24):
        doc = fitz.open(str(pdf_path))
        for page_number in range(1, doc.page_count + 1):
            page = doc[page_number - 1]
            limit = page.rect.height - margin
            blocks = cast(dict[str, Any], page.get_text('dict'))['blocks']
            for block in blocks:
                if block.get('type') != 0:
                    continue
                text = ''.join(span['text'] for line in block['lines'] for span in line['spans']).strip()
                if not text:
                    continue
                self.assertLessEqual(
                    block['bbox'][3],
                    limit,
                    f'text block below margin on page {page_number}: {text[:80]!r} bbox={block["bbox"]}',
                )

    def test_long_experience_list_is_split_without_dropping_items_or_overflowing(self):
        items = [
            f'Activité projet Lino numéro {i:02d} avec cadrage, suivi, recette et documentation technique détaillée'
            for i in range(1, 95)
        ]
        data = {
            'name': 'LINO',
            'title': 'Chef de projet IT',
            'formations': [{'date': '2020', 'degree': 'Master informatique', 'school': 'Université'}],
            'skills': [{'category': 'Gestion de projet', 'items': ['Agile', 'Jira', 'Confluence']}],
            'experiences': [
                {
                    'date': "Janvier 2023 - Aujourd'hui",
                    'role': 'CHEF DE PROJET IT CHEZ CLIENT',
                    'company_highlight': 'CLIENT',
                    'sections': [{'heading': 'Activités', 'content': items}],
                }
            ],
        }

        pdf_path = self.render(data)
        doc = fitz.open(str(pdf_path))
        text = '\n'.join(str(doc[page_index].get_text()) for page_index in range(doc.page_count))

        self.assertGreater(doc.page_count, 1)
        self.assertIn('Activités (suite)', text)
        for i in range(1, 95):
            self.assertIn(f'Activité projet Lino numéro {i:02d}', text)
        self.assert_no_text_below_margin(pdf_path)

    def test_renderer_rejects_bare_linkedin_and_github_contact_markers(self):
        base = {
            'name': 'LINO',
            'title': 'Architecte Cloud',
            'formations': [],
            'skills': [],
            'experiences': [],
        }
        contacts = [
            'linkedin',
            'linkedin.com/in/lino',
            'fr.linkedin.com/in/lino',
            'linkedin/in/lino',
            'github.com/lino',
            'www.github.com/lino',
            'GitHub: lino',
            'github/lino',
            'github @lino',
        ]
        for contact in contacts:
            data = dict(base)
            data['description'] = f'Contact candidat: {contact}'
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                input_path = workdir / 'input.json'
                output_path = workdir / 'output.pdf'
                input_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, str(RENDERER), str(input_path), str(output_path)],
                    text=True,
                    capture_output=True,
                    timeout=180,
                )
            self.assertNotEqual(result.returncode, 0, contact)
            self.assertIn('contact', (result.stderr or result.stdout).lower())

    def test_renderer_allows_dates_containing_07_and_technical_github_usage(self):
        data = {
            'name': 'LINO',
            'title': 'Architecte Cloud',
            'description': 'Industrialisation CI/CD avec GitHub Actions.',
            'formations': [{'date': '2007', 'degree': 'Master informatique', 'school': 'Université'}],
            'skills': [{'category': 'DevOps', 'items': ['GitHub Actions', 'CI/CD']}],
            'experiences': [
                {
                    'date': 'Juillet 2007 - Juin 2008',
                    'role': 'ARCHITECTE CLOUD CHEZ CLIENT',
                    'sections': [{'heading': 'Missions clés', 'content': ['Projet mené de 07/2007 à 07/2008']}],
                }
            ],
        }
        pdf_path = self.render(data)
        self.assertTrue(pdf_path.exists())

    def test_long_page_one_skill_list_continues_before_experiences(self):
        skill_items = [f'Compétence technique longue {i:02d} Python Azure Kubernetes Terraform SQL Server' for i in range(1, 80)]
        data = {
            'name': 'LINO',
            'title': 'Architecte Cloud',
            'formations': [{'date': '2020', 'degree': 'Master informatique', 'school': 'Université'}],
            'skills': [{'category': 'Cloud & DevOps', 'items': skill_items}],
            'experiences': [
                {
                    'date': '2024',
                    'role': 'ARCHITECTE CLOUD CHEZ CLIENT',
                    'sections': [{'heading': 'Missions clés', 'content': ['Architecture cible', 'Accompagnement équipes']}],
                }
            ],
        }

        pdf_path = self.render(data)
        doc = fitz.open(str(pdf_path))
        text = '\n'.join(str(doc[page_index].get_text()) for page_index in range(doc.page_count))

        self.assertGreater(doc.page_count, 1)
        self.assertIn('Cloud & DevOps (suite)', text)
        for i in range(1, 80):
            self.assertIn(f'Compétence technique longue {i:02d}', text)
        self.assertIn('ARCHITECTE CLOUD CHEZ CLIENT', text)
        self.assert_no_text_below_margin(pdf_path)


if __name__ == '__main__':
    unittest.main()
