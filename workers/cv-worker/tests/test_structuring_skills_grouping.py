from src.structuring import _group_long_skills


def test_group_long_skills_preserves_ezzoubir_source_categories():
    skills = [
        {"category": "Mainframe", "items": ["COBOL", "DB2", "DL1", "GSAM", "JCL", "IMS", "DB2BATCH", "IMSBATCH"]},
        {
            "category": "Compétences Organisationnelles",
            "items": [
                "Planification",
                "Développement",
                "Maintenance Corrective",
                "Suivi d'exploitation",
                "Support technique",
                "Suivi des incidents",
                "Livraison",
            ],
        },
    ]

    result = _group_long_skills(skills, max_items=6)

    assert result == skills
