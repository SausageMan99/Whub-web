"""Output sanitizers must only touch strings that really carry contact/identity data."""
from src.structuring import sanitize_contact_in_json, sanitize_identity_terms_in_json

CLEAN_LINES = [
    "Pilotage des campagnes LinkedIn Ads et emailing",
    "Gestion du contact client et du support email",
    "Environnement technique : C#, ASP.NET MVC 5, ADO.NET ; Jira",
    "Missions :",
]


def _cv(lines):
    return {"experiences": [{"sections": [{"heading": "Missions", "content": list(lines)}]}]}


def _content(data):
    return data["experiences"][0]["sections"][0]["content"]


def test_contact_sanitizer_leaves_clean_sentences_verbatim():
    assert _content(sanitize_contact_in_json(_cv(CLEAN_LINES))) == CLEAN_LINES


def test_contact_sanitizer_still_strips_real_contacts_and_their_labels():
    cleaned = _content(sanitize_contact_in_json(_cv([
        "Email : jean.dupont@gmail.com",
        "LinkedIn : linkedin.com/in/jean-dupont",
        "Portfolio jean-dupont.dev et React",
    ])))

    assert cleaned == ["Portfolio et React"]


def test_identity_sanitizer_leaves_strings_without_the_term_verbatim():
    assert _content(sanitize_identity_terms_in_json(_cv(CLEAN_LINES), ["Dupont"])) == CLEAN_LINES


def test_identity_sanitizer_still_redacts_the_term():
    assert _content(sanitize_identity_terms_in_json(_cv(["Projet Dupont : refonte"]), ["Dupont"])) == ["Projet: refonte"]
