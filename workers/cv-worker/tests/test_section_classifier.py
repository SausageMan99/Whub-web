from src.content_blocks import ContentBlock, SourceDocument
from src.section_classifier import classify_sections


def b(order: int, text: str):
    return ContentBlock.from_text("other", order, 0, text)


def test_classifies_skills_after_competences_header():
    doc = SourceDocument(blocks=[b(1, "COMPÉTENCES"), b(2, "Java, Spring, AWS")])
    classified = classify_sections(doc)
    assert classified.blocks[1].type == "skills"


def test_classifies_experience_after_experience_header():
    doc = SourceDocument(blocks=[b(1, "EXPÉRIENCES PROFESSIONNELLES"), b(2, "2021 - 2024 Développeur Java Client X")])
    classified = classify_sections(doc)
    assert classified.blocks[1].type == "experience"


def test_classification_preserves_text_verbatim():
    text = "2021 - 2024 Développement d'API REST"
    doc = SourceDocument(blocks=[b(1, "EXPÉRIENCES"), b(2, text)])
    classified = classify_sections(doc)
    assert classified.blocks[1].text == text


def test_experience_continuation_stays_experience():
    doc = SourceDocument(blocks=[
        b(1, "EXPÉRIENCES"),
        b(2, "2020 - 2023 Développeur Java Client A"),
        b(3, "Réalisations clés : développement API, maintenance"),
        b(4, "Environnement technique : Java, Spring, AWS"),
    ])
    classified = classify_sections(doc)
    assert [block.type for block in classified.blocks[1:]] == ["experience", "experience", "experience"]
