from pathlib import Path
import fitz
from .config import settings
from .supabase_client import client

class ExtractionError(Exception):
    pass

def download_source(job: dict, workdir: Path) -> Path:
    source_path = job["source_file_path"]
    raw = client.storage.from_(settings.cv_sources_bucket).download(source_path)
    local = workdir / "source.pdf"
    local.write_bytes(raw)
    return local

def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    text = "\n".join(page.get_text("text") for page in doc)
    if len(text.strip()) < 400:
        raise ExtractionError("Texte source trop court: PDF probablement scanné ou illisible")
    return text
