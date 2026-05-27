import unittest

from src.structuring import (
    build_whub_json,
    split_cv_text_into_blocks,
    assemble_structured_blocks,
    apply_client_synthesis_policy,
    StructuringError,
)


class LongCvStructuringTest(unittest.TestCase):
    def test_split_cv_text_into_semantic_blocks_preserves_content_order(self):
        text = """
Jean Dupont
Architecte Solution

PROFIL
Profil senior cloud et data.

COMPÉTENCES
Python
AWS

FORMATIONS
2015 - Master informatique

EXPÉRIENCES PROFESSIONNELLES
2022 - Aujourd'hui Architecte chez ACME
Missions: cadrage architecture
Environnement technique: AWS, Python

2019 - 2022 Tech Lead chez BETA
Missions: développement backend
Environnement technique: Java, Kubernetes
"""
        blocks = split_cv_text_into_blocks(text)

        self.assertEqual([block["kind"] for block in blocks], ["header", "profile", "skills", "education", "experience", "experience"])
        self.assertIn("Jean Dupont", blocks[0]["text"])
        self.assertIn("Profil senior cloud", blocks[1]["text"])
        self.assertIn("Python", blocks[2]["text"])
        self.assertIn("Master informatique", blocks[3]["text"])
        self.assertIn("ACME", blocks[4]["text"])
        self.assertIn("BETA", blocks[5]["text"])
        self.assertEqual("\n".join(block["text"] for block in blocks).count("Environnement technique"), 2)

    def test_assemble_structured_blocks_keeps_all_lists_and_metadata(self):
        assembled = assemble_structured_blocks([
            {"name": "JEAN", "title": "Architecte Solution", "description": "Profil senior", "formations": [], "skills": [], "experiences": []},
            {"name": "JEAN", "title": "Architecte Solution", "formations": [], "skills": [{"category": "Cloud", "items": ["AWS"]}], "experiences": []},
            {"name": "JEAN", "title": "Architecte Solution", "formations": [{"date": "2015", "degree": "Master", "school": "Université"}], "skills": [], "experiences": []},
            {"name": "JEAN", "title": "Architecte Solution", "formations": [], "skills": [], "experiences": [{"date": "2022", "role": "Architecte chez ACME", "sections": []}]},
        ], candidate_first_name="Jean")

        self.assertEqual(assembled["name"], "JEAN")
        self.assertEqual(assembled["title"], "Architecte Solution")
        self.assertEqual(assembled["description"], "Profil senior")
        self.assertEqual(assembled["skills"], [{"category": "Cloud", "items": ["AWS"]}])
        self.assertEqual(assembled["formations"], [{"date": "2015", "degree": "Master", "school": "Université"}])
        self.assertEqual(len(assembled["experiences"]), 1)

    def test_standard_synthesis_keeps_recent_experiences_detailed_and_condenses_old_ones(self):
        data = {
            "name": "JEAN",
            "title": "Architecte Solution",
            "formations": [],
            "skills": [{"category": "Cloud", "items": ["AWS", "Azure"]}],
            "experiences": [
                {"date": "2024", "role": "Lead chez A", "sections": [{"heading": "Missions clés", "content": ["A1", "A2", "A3"]}, {"heading": "Environnement technique", "content": "AWS, Terraform, Kubernetes"}]},
                {"date": "2023", "role": "Lead chez B", "sections": [{"heading": "Missions clés", "content": ["B1", "B2"]}]},
                {"date": "2022", "role": "Lead chez C", "sections": [{"heading": "Missions clés", "content": ["C1", "C2"]}]},
                {"date": "2020", "role": "Développeur chez D", "sections": [{"heading": "Missions clés", "content": ["D1", "D2", "D3"]}, {"heading": "Environnement technique", "content": "Java, Spring, SQL Server, Jenkins"}]},
                {"date": "2018", "role": "Développeur chez E", "sections": [{"heading": "Activités", "content": ["E1", "E2"]}]},
            ],
        }

        synthesized = apply_client_synthesis_policy(data, mode="standard")

        self.assertEqual([exp["role"] for exp in synthesized["experiences"]], ["Lead chez A", "Lead chez B", "Lead chez C", "Développeur chez D", "Développeur chez E"])
        self.assertEqual(synthesized["experiences"][0]["sections"][0]["content"], ["A1", "A2", "A3"])
        old_sections = synthesized["experiences"][3]["sections"]
        self.assertEqual(old_sections[0]["heading"], "Synthèse mission")
        self.assertIn("D1", old_sections[0]["content"])
        self.assertTrue(any("Synthèse W hub" in item for item in old_sections[0]["content"]))
        self.assertEqual(old_sections[1]["heading"], "Environnement technique")
        self.assertIn("Backend", old_sections[1]["content"])
        self.assertIn("DevOps", old_sections[1]["content"])

    def test_complete_synthesis_mode_preserves_experience_sections_verbatim(self):
        data = {
            "name": "JEAN",
            "title": "Architecte Solution",
            "formations": [],
            "skills": [],
            "experiences": [{"date": "2018", "role": "Dev", "sections": [{"heading": "Missions clés", "content": ["X1", "X2", "X3"]}]}],
        }

        synthesized = apply_client_synthesis_policy(data, mode="complete")

        self.assertEqual(synthesized["experiences"][0]["sections"], data["experiences"][0]["sections"])

    def test_long_certifications_and_skills_are_grouped_without_dropping_items(self):
        certs = [f"Certification AWS niveau {i}" for i in range(1, 8)]
        data = {
            "name": "JEAN",
            "title": "Architecte Solution",
            "formations": [{"date": "2024", "degree": cert, "school": "AWS"} for cert in certs],
            "skills": [{"category": "Certifications", "items": certs}],
            "experiences": [],
        }

        synthesized = apply_client_synthesis_policy(data, mode="standard")

        self.assertEqual(len(synthesized["formations"]), 1)
        self.assertEqual(synthesized["formations"][0]["degree"].count("Certification AWS"), 7)
        self.assertEqual(synthesized["skills"][0]["items"], ["; ".join(certs)])

    def test_long_cv_rejects_contact_details_after_synthesis(self):
        def fake_runner(prompt: str, timeout: int):
            return 0, '{"name":"JEAN","title":"Architecte Solution","formations":[],"skills":[],"experiences":[{"date":"2024","role":"Lead","sections":[{"heading":"Missions clés","content":["Contact: jean@example.com"]}]}]}', ""

        with self.assertRaisesRegex(StructuringError, "Coordonnées"):
            build_whub_json("Jean\n" + ("ligne\n" * 20), "", [], "Jean", long_cv_threshold=10, hermes_runner=fake_runner)

    def test_long_cv_uses_multiple_hermes_calls_and_reports_block_failures(self):
        calls = []

        def fake_runner(prompt: str, timeout: int):
            calls.append(prompt)
            if "BETA" in prompt:
                return 1, "", "boom beta"
            return 0, '{"name":"JEAN","title":"Architecte Solution","formations":[],"skills":[],"experiences":[]}', ""

        long_text = "PROFIL\nJean architecte\n\nEXPÉRIENCES\n2022 ACME\n" + ("ligne acme\n" * 30) + "\n2021 BETA\n" + ("ligne beta\n" * 30)

        with self.assertRaisesRegex(StructuringError, "bloc .*BETA|long CV"):
            build_whub_json(long_text, "", [], "Jean", long_cv_threshold=80, hermes_runner=fake_runner)

        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all("CV source" in prompt for prompt in calls))


if __name__ == "__main__":
    unittest.main()
