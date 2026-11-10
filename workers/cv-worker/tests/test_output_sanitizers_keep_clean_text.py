"""Output sanitizers must only touch strings that really carry contact/identity data."""
import pytest
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


# Lot 3 (2026-11): words cut out of mission bullets by the JSON sanitizer.
@pytest.mark.parametrize("bullet", [
    "Refonte UX de plusieurs sections du site web, avec une réflexion sur la structure",
    "TAD / OD (architecture diagrams in draw.io) with system, network and storage services",
    "Notifications temps réel avec socket.io et Node.js",
])
def test_json_sanitizer_keeps_product_domains_and_site_web(bullet):
    from src.structuring import sanitize_contact_in_json

    data = {"experiences": [{"sections": [{"heading": "Missions clés", "content": [bullet]}]}]}

    assert sanitize_contact_in_json(data)["experiences"][0]["sections"][0]["content"] == [bullet]
