from pathlib import Path
import json
import subprocess
import sys
from PIL import Image
from .config import settings
from .layout_retry import assert_layout_retry_preserves_content

class RenderingError(Exception):
    pass

def assert_whub_assets() -> None:
    logo = Path(settings.whub_assets_dir) / "img_0dcab6df734b.png"
    watermark = Path(settings.whub_assets_dir) / "img_90df8f14aa40.png"
    expected = [(logo, (1051, 398)), (watermark, (1192, 1192))]
    for path, size in expected:
        if not path.exists():
            raise RenderingError(f"Asset W hub manquant: {path}")
        actual = Image.open(path).size
        if actual != size:
            raise RenderingError(f"Mauvais asset W hub {path}: {actual}, attendu {size}")

def render_pdf(data: dict, workdir: Path, layout_options: dict | None = None, output_name: str = "output.pdf") -> Path:
    assert_whub_assets()
    input_path = workdir / ("input_layout_retry.json" if layout_options else "input.json")
    output_path = workdir / output_name
    renderer_data = dict(data)
    if layout_options:
        renderer_data["_layout"] = dict(layout_options)
        assert_layout_retry_preserves_content(data, renderer_data)
    input_path.write_text(json.dumps(renderer_data, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run([sys.executable, settings.whub_renderer_path, str(input_path), str(output_path)], text=True, capture_output=True, timeout=180)
    if result.returncode != 0 or not output_path.exists():
        raise RenderingError(result.stderr or result.stdout or "Renderer failed")
    return output_path
