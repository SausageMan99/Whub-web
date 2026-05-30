import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import DEFAULT_WHUB_ASSETS_DIR, DEFAULT_WHUB_FONTS_DIR, DEFAULT_WHUB_RENDERER_PATH
from src.rendering import render_pdf, RenderingError, assert_whub_assets


class TestAssertWHubAssets:
    def test_raises_when_logo_missing(self, tmp_path: Path):
        with patch("src.rendering.settings.whub_assets_dir", str(tmp_path)):
            with pytest.raises(RenderingError, match="Asset W hub manquant"):
                assert_whub_assets()

    def test_raises_when_wrong_size(self, tmp_path: Path):
        from PIL import Image
        logo = tmp_path / "img_0dcab6df734b.png"
        watermark = tmp_path / "img_90df8f14aa40.png"
        Image.new("RGBA", (100, 100)).save(logo)
        Image.new("RGBA", (100, 100)).save(watermark)
        with patch("src.rendering.settings.whub_assets_dir", str(tmp_path)):
            with pytest.raises(RenderingError, match="Mauvais asset W hub"):
                assert_whub_assets()

    def test_packaged_assets_have_valid_dimensions(self):
        from PIL import Image
        assert Image.open(DEFAULT_WHUB_ASSETS_DIR / "img_0dcab6df734b.png").size == (1051, 398)
        assert Image.open(DEFAULT_WHUB_ASSETS_DIR / "img_90df8f14aa40.png").size == (1192, 1192)


class TestRenderPdf:
    def test_default_renderer_path_is_repo_local(self):
        assert DEFAULT_WHUB_RENDERER_PATH.name == "whub_cv_renderer.py"
        assert DEFAULT_WHUB_RENDERER_PATH.parent.name == "renderer"
        assert DEFAULT_WHUB_RENDERER_PATH.exists()

    def test_default_assets_and_fonts_are_repo_local(self):
        assert DEFAULT_WHUB_ASSETS_DIR == DEFAULT_WHUB_RENDERER_PATH.parents[1] / "assets" / "whub"
        assert DEFAULT_WHUB_FONTS_DIR == DEFAULT_WHUB_RENDERER_PATH.parents[1] / "assets" / "fonts" / "poppins"
        for weight in ["Regular", "Bold", "SemiBold", "Light"]:
            assert (DEFAULT_WHUB_FONTS_DIR / f"Poppins-{weight}.ttf").exists()

    def test_render_pdf_writes_json_and_calls_renderer(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()
        output_pdf = workdir / "output.pdf"
        output_pdf.write_bytes(b"fake pdf")
        fake_renderer = tmp_path / "renderer.py"
        fake_renderer.write_text("# renderer stub\n", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result) as mock_run:
                with patch("src.rendering.settings.whub_renderer_path", str(fake_renderer)):
                    result = render_pdf(data, workdir)

        input_path = workdir / "input.json"
        assert input_path.exists()
        assert json.loads(input_path.read_text(encoding="utf-8")) == data
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == [sys.executable, str(fake_renderer), str(input_path), str(output_pdf)]
        assert kwargs["env"]["WHUB_ASSETS_DIR"] == str(DEFAULT_WHUB_ASSETS_DIR)
        assert kwargs["env"]["WHUB_FONTS_DIR"] == str(DEFAULT_WHUB_FONTS_DIR)
        assert result == output_pdf

    def test_render_pdf_can_pass_internal_layout_retry_options(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()
        output_pdf = workdir / "retry.pdf"
        output_pdf.write_bytes(b"fake pdf")
        fake_renderer = tmp_path / "renderer.py"
        fake_renderer.write_text("# renderer stub\n", encoding="utf-8")
        mock_result = MagicMock(returncode=0)

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result) as mock_run:
                with patch("src.rendering.settings.whub_renderer_path", str(fake_renderer)):
                    result = render_pdf(data, workdir, layout_options={"anti_crowding": True}, output_name="retry.pdf")

        input_path = workdir / "input_layout_retry.json"
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        assert payload["_layout"] == {"anti_crowding": True}
        assert "_layout" not in data
        args, _ = mock_run.call_args
        assert args[0] == [sys.executable, str(fake_renderer), str(input_path), str(output_pdf)]
        assert result == output_pdf

    def test_render_pdf_raises_when_subprocess_fails(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()
        fake_renderer = tmp_path / "renderer.py"
        fake_renderer.write_text("# renderer stub\n", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Renderer error"

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result):
                with patch("src.rendering.settings.whub_renderer_path", str(fake_renderer)):
                    with pytest.raises(RenderingError, match="Renderer error"):
                        render_pdf(data, workdir)

    def test_render_pdf_raises_when_output_missing(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()
        fake_renderer = tmp_path / "renderer.py"
        fake_renderer.write_text("# renderer stub\n", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result):
                with patch("src.rendering.settings.whub_renderer_path", str(fake_renderer)):
                    with pytest.raises(RenderingError, match="Renderer failed"):
                        render_pdf(data, workdir)

    def test_render_pdf_raises_when_renderer_missing(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.settings.whub_renderer_path", str(tmp_path / "missing.py")):
                with pytest.raises(RenderingError, match="Renderer W hub manquant"):
                    render_pdf(data, workdir)
