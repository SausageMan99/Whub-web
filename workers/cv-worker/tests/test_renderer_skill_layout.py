from __future__ import annotations

import importlib.util
from pathlib import Path


RENDERER_PATH = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"
spec = importlib.util.spec_from_file_location("whub_cv_renderer", RENDERER_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_dense_skill_items_are_split_without_dropping_source_terms():
    dense_item = (
        "Python, Java, JavaScript, TypeScript, React, Next.js, Vue.js, Node.js, Express, "
        "Symfony, .NET, C#, PostgreSQL, MySQL, MongoDB, Redis, Docker, Kubernetes, "
        "Terraform, Helm, Maven, Jenkins, GitLab CI, Azure DevOps, AWS, Azure, GCP"
    )

    chunks = renderer.prepare_readable_skill_categories([
        {"category": "Stack technique", "items": [dense_item]}
    ])

    rendered_text = " ".join(
        [category["category"] for category in chunks]
        + [item for category in chunks for item in category["items"]]
    )
    for term in ["Terraform", "Helm", "Maven", "Kubernetes", "GitLab CI", "Azure DevOps", "Next.js", ".NET"]:
        assert term in rendered_text

    assert all(len(item) <= renderer.DEFAULT_MAX_SKILL_ITEM_CHARS for category in chunks for item in category["items"])
    assert sum(len(category["items"]) for category in chunks) > 1


def test_long_skill_category_is_chunked_as_explicit_suite_without_mutating_source_order():
    source_items = [
        "Python", "FastAPI", "Django", "Flask", "SQLAlchemy", "Pandas", "NumPy", "PyTest",
        "React", "Next.js", "Vue.js", "TypeScript", "Tailwind", "Node.js", "Express", "NestJS",
        "Docker", "Kubernetes", "Terraform", "Helm", "Maven", "Jenkins", "GitLab CI", "Azure DevOps",
    ]

    chunks = renderer.prepare_readable_skill_categories([
        {"category": "Compétences", "items": source_items}
    ])

    flattened = [item for category in chunks for item in category["items"]]
    assert flattened == source_items
    assert [category["category"] for category in chunks] == [
        "Compétences",
        "Compétences (suite)",
        "Compétences (suite)",
    ]
    assert all(len(category["items"]) <= renderer.DEFAULT_MAX_SKILL_ITEMS_PER_BLOCK for category in chunks)


def test_unsplittable_long_skill_text_is_kept_for_qa_instead_of_rewritten():
    item = "x" * 220
    chunks = renderer.prepare_readable_skill_categories([
        {"category": "Outils", "items": [item]}
    ])

    assert chunks == [{"category": "Outils", "items": [item]}]
