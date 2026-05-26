from pathlib import Path
import json
import subprocess
from PIL import Image
from .config import settings

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

def render_pdf(data: dict, workdir: Path) -> Path:
    assert_whub_assets()
    input_path = workdir / "input.json"
    output_path = workdir / "output.pdf"
    input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run(["python", settings.whub_renderer_path, str(input_path), str(output_path)], text=True, capture_output=True, timeout=180)
    if result.returncode != 0 or not output_path.exists():
        raise RenderingError(result.stderr or result.stdout or "Renderer failed")
    return output_path
