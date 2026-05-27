import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


class TestRenderPdf:
    def test_render_pdf_writes_json_and_calls_renderer(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()
        output_pdf = workdir / "output.pdf"
        output_pdf.write_bytes(b"fake pdf")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result) as mock_run:
                with patch("src.rendering.settings.whub_renderer_path", "/fake/renderer.py"):
                    result = render_pdf(data, workdir)

        input_path = workdir / "input.json"
        assert input_path.exists()
        assert json.loads(input_path.read_text(encoding="utf-8")) == data
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == [sys.executable, "/fake/renderer.py", str(input_path), str(output_pdf)]
        assert result == output_pdf

    def test_render_pdf_raises_when_subprocess_fails(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Renderer error"

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result):
                with patch("src.rendering.settings.whub_renderer_path", "/fake/renderer.py"):
                    with pytest.raises(RenderingError, match="Renderer error"):
                        render_pdf(data, workdir)

    def test_render_pdf_raises_when_output_missing(self, tmp_path: Path):
        data = {"name": "JEAN", "title": "Dev", "formations": [], "skills": [], "experiences": []}
        workdir = tmp_path / "work"
        workdir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""

        with patch("src.rendering.assert_whub_assets"):
            with patch("src.rendering.subprocess.run", return_value=mock_result):
                with patch("src.rendering.settings.whub_renderer_path", "/fake/renderer.py"):
                    with pytest.raises(RenderingError, match="Renderer failed"):
                        render_pdf(data, workdir)
