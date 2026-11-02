from src.structuring import assemble_structured_blocks


def _part(**overrides):
    part = {"name": "AMINA", "title": "QA Engineer", "formations": [], "skills": [], "experiences": []}
    part.update(overrides)
    return part


def test_block_boundary_split_experience_is_reattached():
    # Amina (2026-11-02): header at the end of one block, missions at the start of the next.
    parts = [
        _part(experiences=[
            {"date": "04/2014 – 10/2014", "role": "ASSISTANTE CONTRÔLE DE GESTION", "sections": [{"heading": "Contexte", "content": ["Audit"]}]},
            {"date": "09/2010 – 10/2010", "role": "ASSISTANTE ADMINISTRATIVE", "sections": []},
        ]),
        _part(experiences=[
            {"date": "", "role": "", "sections": [{"heading": "Missions", "content": ["Étude du circuit de traitement des dossiers."]}]},
        ]),
    ]

    experiences = assemble_structured_blocks(parts, "Amina")["experiences"]

    assert len(experiences) == 2
    assert experiences[1]["role"] == "ASSISTANTE ADMINISTRATIVE"
    assert experiences[1]["sections"][0]["content"] == ["Étude du circuit de traitement des dossiers."]


def test_complete_experiences_are_not_merged():
    parts = [_part(experiences=[
        {"date": "2020", "role": "Dev", "sections": [{"heading": "Missions", "content": ["A"]}]},
        {"date": "", "role": "", "sections": [{"heading": "Missions", "content": ["B"]}]},
    ])]

    assert len(assemble_structured_blocks(parts, "Amina")["experiences"]) == 2


def test_languages_and_certifications_from_every_block_are_kept_once():
    parts = [
        _part(languages=[{"name": "Français", "level": "natif"}], certifications=["ISTQB Foundation"]),
        _part(languages=[{"name": "Français", "level": "natif"}, {"name": "Anglais", "level": "courant"}], certifications=["ISTQB Foundation", "PSM I"]),
    ]

    assembled = assemble_structured_blocks(parts, "Amina")

    assert assembled["languages"] == [{"name": "Français", "level": "natif"}, {"name": "Anglais", "level": "courant"}]
    assert assembled["certifications"] == ["ISTQB Foundation", "PSM I"]
