import json
import re

CONTACT_PATTERNS = [r"@", r"linkedin", r"github\.com", r"https?://", r"\+33", r"0[67](?:[ .-]?\d{2}){4}"]

class StructuringError(Exception):
    pass

def assert_no_contact_in_json(data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False).lower()
    hits = [p for p in CONTACT_PATTERNS if re.search(p, text)]
    if hits:
        raise StructuringError(f"Coordonnées détectées dans JSON renderer: {hits}")

def build_whub_json(extracted_text: str, instructions: str, comments: list[dict]) -> dict:
    """TODO: brancher Hermes CLI/API ici.

    Pour le MVP technique, cette fonction doit être remplacée par l'appel Hermes qui charge
    le skill whub-client-cv-generator et retourne un JSON strictement conforme au renderer.
    """
    raise StructuringError("Structuration Hermes non branchée: implémenter build_whub_json avant prod")
