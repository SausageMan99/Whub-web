import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

import fitz


RENDERER = Path('/root/.hermes/scripts/whub_cv_renderer.py')


def load_renderer_module():
    spec = importlib.util.spec_from_file_location('whub_cv_renderer', RENDERER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RendererOverflowTest(unittest.TestCase):
    def test_role_html_appends_company_highlight_when_role_omits_company(self):
        renderer_module = load_renderer_module()
        with tempfile.TemporaryDirectory() as tmp:
            renderer = renderer_module.Renderer(str(Path(tmp) / 'company.pdf'))
            html = renderer.role_html({'role': 'Responsable ERP SAP', 'company_highlight': 'DELPHARM LILLE'})
        self.assertIn('Responsable ERP SAP', html)
        self.assertIn('DELPHARM LILLE', html)
        self.assertIn('#7001F5', html)

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

    def test_renderer_normalizes_unsupported_symbols_without_nul_glyphs(self):
        data = {
            'name': 'ZAHIA',
            'title': 'Chef de projet IT',
            'formations': [],
            'skills': [{'category': 'Data', 'items': ['Taux d’adoption ≥ 90 %']}],
            'experiences': [
                {
                    'date': '2023 - à ce jour',
                    'role': 'CHEF DE PROJET CHEZ CLIENT',
                    'sections': [{
                        'heading': 'Missions clés',
                        'content': ['Distribution des dossiers contentieux → -15 % de tâches manuelles'],
                    }],
                }
            ],
        }
        pdf_path = self.render(data)
        doc = fitz.open(str(pdf_path))
        text = '\n'.join(str(doc[page_index].get_text()) for page_index in range(doc.page_count))

        self.assertNotIn('\x00', text)
        self.assertIn('-> -15 %', text)
        self.assertIn('≥ 90 %', text)

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

    def test_skill_columns_are_balanced_by_measured_height_not_alternating_index(self):
        renderer_module = load_renderer_module()
        renderer_module.prep_assets()
        renderer_module.register_fonts(renderer_module.ensure_poppins())
        with tempfile.TemporaryDirectory() as tmp:
            renderer = renderer_module.Renderer(str(Path(tmp) / 'balanced.pdf'))
            wide_items = [
                'Architecture microservices Java Spring Boot Kubernetes observabilité sécurité performance',
                'Industrialisation CI CD GitLab Terraform Helm Docker Azure DevOps et supervision',
                'Cadrage technique APIs REST événements Kafka haute disponibilité et documentation',
                'Accompagnement équipes revues de code mentoring et amélioration continue',
            ]
            skills = [
                {'category': 'Backend', 'items': wide_items},
                {'category': 'Méthodes', 'items': ['Agile', 'Scrum']},
                {'category': 'Cloud DevOps', 'items': wide_items},
                {'category': 'Outils', 'items': ['Jira', 'Confluence']},
            ]

            fitted, overflow = renderer.split_skill_columns_for_page(skills, 220, renderer.content_bottom - 12)
            heights = [
                sum(renderer.skill_block_height(cat, width) for cat in cats)
                for cats, width in zip(fitted, [156, 152])
            ]

        self.assertFalse(overflow)
        self.assertLess(abs(heights[0] - heights[1]), max(heights) * 0.35)
        self.assertEqual([len(col) for col in fitted], [2, 2])
        self.assertEqual(fitted[0][0]['category'], 'Backend')
        self.assertEqual(fitted[1][0]['category'], 'Cloud DevOps')

    def test_first_experience_uses_same_anti_orphan_renderer_as_following_experiences(self):
        renderer_module = load_renderer_module()
        calls = []
        original_render_experience = renderer_module.Renderer.render_experience

        def record_render_experience(self, exp, *args, **kwargs):
            calls.append(exp.get('role'))
            return original_render_experience(self, exp, *args, **kwargs)

        renderer_module.Renderer.render_experience = record_render_experience
        self.addCleanup(setattr, renderer_module.Renderer, 'render_experience', original_render_experience)
        renderer_module.prep_assets()
        renderer_module.register_fonts(renderer_module.ensure_poppins())
        data = {
            'name': 'LINO',
            'title': 'Architecte Cloud',
            'formations': [],
            'skills': [{'category': 'Cloud', 'items': ['Azure']}],
            'experiences': [
                {
                    'date': '2024',
                    'role': 'PREMIÈRE EXPÉRIENCE CHEZ CLIENT',
                    'sections': [{'heading': 'Missions clés', 'content': ['Architecture cible']}],
                },
                {
                    'date': '2023',
                    'role': 'DEUXIÈME EXPÉRIENCE CHEZ CLIENT',
                    'sections': [{'heading': 'Missions clés', 'content': ['Accompagnement équipes']}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            renderer_module.Renderer(str(Path(tmp) / 'output.pdf')).render(data)

        self.assertEqual(calls, ['PREMIÈRE EXPÉRIENCE CHEZ CLIENT', 'DEUXIÈME EXPÉRIENCE CHEZ CLIENT'])

    def test_anti_crowding_moves_new_experience_to_fresh_page_when_current_page_is_dense(self):
        renderer_module = load_renderer_module()
        renderer_module.prep_assets()
        renderer_module.register_fonts(renderer_module.ensure_poppins())
        with tempfile.TemporaryDirectory() as tmp:
            renderer = renderer_module.Renderer(
                str(Path(tmp) / 'anti-crowding.pdf'),
                {'anti_crowding': True, 'page_dense_char_threshold': 100, 'max_used_ratio': 0.80},
            )
            renderer.current_name = 'LINO'
            renderer.new_page(False, 'LINO')
            renderer.flow(renderer.left, renderer.y, renderer.right - renderer.left)
            renderer.current_page_chars = 120
            renderer.y = renderer.page_start_y + 120
            page_before = renderer.page
            moved = renderer.maybe_break_before_experience(
                {'date': '2023', 'role': 'EXPÉRIENCE SUIVANTE CHEZ CLIENT', 'sections': []},
                index=2,
                total=3,
            )

        self.assertTrue(moved)
        self.assertEqual(renderer.page, page_before + 1)

    def test_zahia_like_layout_retry_rebalances_pages_without_dropping_experience_content(self):
        bullets = [
            f'Zahia mission source conservée numéro {i:02d} avec atelier métier, recette et coordination assurance'
            for i in range(1, 42)
        ]
        environment = ['Jira', 'Confluence', 'SQL', 'API REST', 'Assurance santé', 'Prévoyance']
        data = {
            'name': 'ZAHIA',
            'title': 'Product Owner Assurance',
            'formations': [{'date': '2007', 'degree': 'Master 2', 'school': 'Université Paris'}],
            'skills': [{'category': 'Assurance', 'items': ['Santé', 'Prévoyance', 'Retraite']}],
            'experiences': [
                {
                    'date': 'Janvier 2024 - Décembre 2025',
                    'role': 'Product Owner Assurance - KLESIA',
                    'company_highlight': 'KLESIA',
                    'sections': [
                        {'heading': 'Missions clés', 'content': bullets},
                        {'heading': 'Environnement technique', 'content': environment},
                    ],
                },
                {
                    'date': '2019 - 2023',
                    'role': 'Business Analyst Assurance - Client source',
                    'company_highlight': 'Client source',
                    'sections': [{'heading': 'Missions clés', 'content': ['Cadrage fonctionnel', 'Support recette métier']}],
                },
            ],
        }
        retry_data = dict(data)
        retry_data['_layout'] = {
            'anti_crowding': True,
            'page_dense_char_threshold': 100,
            'max_used_ratio': 0.80,
            'readability_reserve': 220,
        }

        base_pdf = self.render(data)
        retry_pdf = self.render(retry_data)
        base_doc = fitz.open(str(base_pdf))
        retry_doc = fitz.open(str(retry_pdf))
        retry_text = '\n'.join(str(retry_doc[page_index].get_text()) for page_index in range(retry_doc.page_count))
        normalized_retry_text = ' '.join(retry_text.split())

        self.assertGreaterEqual(retry_doc.page_count, base_doc.page_count)
        for item in bullets + environment + ['Cadrage fonctionnel', 'Support recette métier']:
            self.assertIn(' '.join(item.split()), normalized_retry_text)
        self.assert_no_text_below_margin(retry_pdf)


if __name__ == '__main__':
    unittest.main()
