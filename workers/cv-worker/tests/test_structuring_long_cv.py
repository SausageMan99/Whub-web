import json
import unittest

from src.structuring import (
    build_whub_json,
    split_cv_text_into_blocks,
    assemble_structured_blocks,
    apply_client_synthesis_policy,
    _hermes_prompt,
    assert_no_contact_in_json,
    StructuringError,
    LONG_CV_CHAR_THRESHOLD,
    LONG_CV_BLOCK_TARGET_CHARS,
)


class LongCvStructuringTest(unittest.TestCase):
    def test_default_long_cv_threshold_targets_timeout_prone_inputs(self):
        self.assertLessEqual(LONG_CV_CHAR_THRESHOLD, 10000)
        self.assertLessEqual(LONG_CV_BLOCK_TARGET_CHARS, 7000)

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

        synthesized = apply_client_synthesis_policy(data, mode="standard", allow_condensation=True)

        self.assertEqual([exp["role"] for exp in synthesized["experiences"]], ["Lead chez A", "Lead chez B", "Lead chez C", "Développeur chez D", "Développeur chez E"])
        self.assertEqual(synthesized["experiences"][0]["sections"][0]["content"], ["A1", "A2", "A3"])
        old_sections = synthesized["experiences"][3]["sections"]
        self.assertEqual(old_sections[0]["heading"], "Synthèse mission")
        self.assertIn("D1", old_sections[0]["content"])
        self.assertTrue(any("Synthèse W hub" in item for item in old_sections[0]["content"]))
        self.assertEqual(old_sections[1]["heading"], "Environnement technique")
        self.assertIn("Backend", old_sections[1]["content"])
        self.assertIn("DevOps", old_sections[1]["content"])

    def test_complete_synthesis_mode_preserves_experience_sections_but_curates_long_skills(self):
        items = [
            "Java", "Spring", "React", "Angular", "AWS", "Azure", "Docker",
            "Kubernetes", "Terraform", "Helm", "PostgreSQL", "Power BI", "Jira",
        ]
        data = {
            "name": "JEAN",
            "title": "Architecte Solution",
            "formations": [],
            "skills": [{"category": "Compétences techniques", "items": items}],
            "experiences": [{"date": "2018", "role": "Dev", "sections": [{"heading": "Missions clés", "content": ["X1", "X2", "X3"]}]}],
        }

        synthesized = apply_client_synthesis_policy(data, mode="complete")
        flat_items = [item for skill in synthesized["skills"] for item in skill["items"]]

        self.assertEqual(synthesized["experiences"][0]["sections"], data["experiences"][0]["sections"])
        self.assertTrue(any(skill["category"] == "Backend" for skill in synthesized["skills"]))
        self.assertTrue(any(skill["category"] == "Cloud / DevOps" for skill in synthesized["skills"]))
        self.assertTrue(all(len(skill["items"]) <= 6 for skill in synthesized["skills"]))
        for expected in items:
            self.assertIn(expected, flat_items)

    def test_build_whub_json_source_gates_invented_skill_expansions(self):
        data = {
            "name": "Zahia",
            "title": "Chef de projet",
            "formations": [],
            "skills": [{
                "category": "Compétences techniques",
                "items": ["Power BI", "SQL", "Google Analytics", "Méthode hybride", "Études de faisabilité"],
            }],
            "experiences": [{"date": "2024", "role": "Chef de projet KLESIA", "company_highlight": "KLESIA", "sections": [
                {"heading": "Missions clés", "content": [
                    "Pilotage recette transverse",
                    "Impact business : croissance du chiffre d’affaires de +40 % entre 2018",
                    "Cartographie des achats de 10 business units",
                ]}
            ]}],
        }
        source_text = "Zahia\nChef de projet KLESIA\nCompétences\nPower BI\nSQL\n"

        with self.assertRaises(StructuringError):
            build_whub_json(source_text, "", [], "Zahia", hermes_runner=lambda prompt, timeout: (0, json.dumps(data, ensure_ascii=False), ""))

    def test_long_certifications_and_skills_are_grouped_without_dropping_items(self):
        certs = [f"Certification AWS niveau {i}" for i in range(1, 8)]
        data = {
            "name": "JEAN",
            "title": "Architecte Solution",
            "formations": [{"date": "2024", "degree": cert, "school": "AWS"} for cert in certs],
            "skills": [{"category": "Certifications", "items": certs}],
            "experiences": [],
        }

        synthesized = apply_client_synthesis_policy(data, mode="standard", allow_condensation=True)

        self.assertEqual(len(synthesized["formations"]), 1)
        self.assertEqual(synthesized["formations"][0]["degree"].count("Certification AWS"), 7)
        self.assertEqual([skill["category"] for skill in synthesized["skills"]], ["Certifications"])
        self.assertEqual(synthesized["skills"][0]["items"], certs)

    def test_oussama_like_long_skill_category_is_curated_into_short_family_groups(self):
        items = [
            "Java", "Spring Boot", "Spring", "Hibernate", "API REST", "Microservices",
            "React", "Angular", "TypeScript", "JavaScript", "HTML5", "CSS3",
            "AWS", "Azure", "Docker", "Kubernetes", "Jenkins", "GitLab CI", "Terraform", "Helm",
            "PostgreSQL", "MySQL", "Oracle", "MongoDB", "Power BI",
            "Agile Scrum", "Kanban", "Jira", "Confluence", "Git", "Maven", "SonarQube",
            "Java", "spring boot",
        ]
        data = {
            "name": "OUSSAMA",
            "title": "Tech Lead Full Stack Java / Angular",
            "formations": [],
            "skills": [{"category": "Compétences techniques", "items": items}],
            "experiences": [],
        }

        synthesized = apply_client_synthesis_policy(data, mode="standard", allow_condensation=True)
        skills = synthesized["skills"]
        flat_items = [item for skill in skills for item in skill["items"]]
        flat_text = " | ".join(flat_items)

        self.assertGreaterEqual(len(skills), 5)
        self.assertTrue(any(skill["category"] == "Backend" for skill in skills))
        self.assertTrue(any(skill["category"] == "Frontend" for skill in skills))
        self.assertTrue(any(skill["category"] == "Cloud / DevOps" for skill in skills))
        self.assertTrue(any(skill["category"] == "Cloud / DevOps — suite" for skill in skills))
        self.assertTrue(any(skill["category"] == "Data" for skill in skills))
        self.assertTrue(any(skill["category"] == "Outils & méthodes" for skill in skills))
        self.assertTrue(all(len(skill["items"]) <= 6 for skill in skills))
        self.assertTrue(all(len(item) <= 80 for item in flat_items))
        self.assertEqual(sum(1 for item in flat_items if item.lower() == "java"), 1)
        expected_unique_terms = [
            "Java", "Spring Boot", "Spring", "Hibernate", "API REST", "Microservices", "Maven",
            "React", "Angular", "TypeScript", "JavaScript", "HTML5", "CSS3",
            "AWS", "Azure", "Docker", "Kubernetes", "Jenkins", "GitLab CI", "Terraform", "Helm",
            "PostgreSQL", "MySQL", "Oracle", "MongoDB", "Power BI",
            "Agile Scrum", "Kanban", "Jira", "Confluence", "Git", "SonarQube",
        ]
        for expected in expected_unique_terms:
            self.assertIn(expected, flat_text)

    def test_structuring_prompt_requests_client_facing_hierarchical_short_skills(self):
        prompt = _hermes_prompt("COMPÉTENCES\nJava\nSpring\nAWS", "", [], "Oussama")

        self.assertIn("compétences", prompt.lower())
        self.assertIn("hiérarchisées", prompt.lower())
        self.assertIn("client-facing", prompt.lower())
        self.assertIn("pavés", prompt.lower())

    def test_long_cv_sanitizes_contact_details_after_synthesis(self):
        def fake_runner(prompt: str, timeout: int):
            return 0, '{"name":"JEAN","title":"Architecte Solution","formations":[],"skills":[],"experiences":[{"date":"2024","role":"Lead","sections":[{"heading":"Missions clés","content":["Contact: jean@example.com"]}]}]}', ""

        result = build_whub_json("Jean\nArchitecte Solution\n2024 Lead\n" + ("ligne\n" * 20), "", [], "Jean", long_cv_threshold=10, hermes_runner=fake_runner)

        self.assertEqual(result["experiences"][0]["sections"][0]["content"], [])
        assert_no_contact_in_json(result)

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
