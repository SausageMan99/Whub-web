from __future__ import annotations

import importlib.util
from pathlib import Path


RENDERER_PATH = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"
spec = importlib.util.spec_from_file_location("whub_cv_renderer", RENDERER_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
renderer.register_fonts(renderer.ensure_poppins())


def test_skill_line_html_renders_bold_category_with_readable_item_separator(tmp_path):
    r = renderer.Renderer(str(tmp_path / "out.pdf"))

    html = r.skill_line_html({"category": "Ops", "items": ["Git", "Kubernetes", "Azure"]})

    assert 'font name="Poppins-Bold">Ops</font>' in html
    assert "Git · Kubernetes · Azure" in html
    assert "Ops :" not in html


def test_split_skill_columns_preserves_source_order_for_source_categories(tmp_path):
    r = renderer.Renderer(str(tmp_path / "out.pdf"))
    skills = [
        {"category": "Technologies Plateformes", "items": [".NET", "ASP.NET", "Xamarin"]},
        {"category": "Front-end", "items": ["Angular", "TypeScript"]},
        {"category": "Data", "items": ["PostgreSQL", "SQL Server"]},
        {"category": "Ops", "items": ["Git", "Kubernetes"]},
    ]

    columns, overflow = r.split_skill_columns_for_page(skills, start_y=200, bottom_y=780)
    rendered_order = [cat["category"] for col in columns for cat in col]

    assert overflow == []
    assert all(columns)
    assert rendered_order == [
        "Technologies Plateformes",
        "Front-end",
        "Data",
        "Ops",
    ]
