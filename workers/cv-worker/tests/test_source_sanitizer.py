import pytest

from src.source_sanitizer import sanitize_source_text, SourceSanitizationError


BUSINESS_CONTENT = """
Profil
Architecte Solution AWS et DevOps avec 10 ans d'expérience.

Compétences
AWS, Kubernetes, Docker, Terraform, Python, GitHub Actions, API REST, Node.js, .NET.
Méthodes Agile Scrum, CI/CD, observabilité, sécurité cloud.

Expériences
2022 - 2025 : Lead DevOps chez EDF
- Migration Kubernetes de plateformes critiques et automatisation Terraform.
- Mise en place de pipelines CI/CD et supervision Prometheus.

2020 - 2022 : Consultant cloud chez BNP Paribas
- Modernisation d'API REST et industrialisation des déploiements.
- Animation d'ateliers avec les équipes produit et sécurité.

Formation
Master informatique, architecture logicielle et systèmes distribués.
"""


def _sanitize(raw: str, **kwargs):
    return sanitize_source_text(raw, candidate_first_name="Jean", min_chars=120, **kwargs)


def _report_text(report) -> str:
    return "".join(repr(report).casefold().split())


def _secret_text(value: str) -> str:
    return "".join(value.casefold().split())


def test_removes_direct_email_without_storing_raw_value_in_report():
    raw = f"""
Jean Dupont
Email : jean.dupont@example.com
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert "jean.dupont@example.com" not in result.text
    assert "Architecte Solution AWS" in result.text
    assert "Migration Kubernetes" in result.text
    assert result.report.removed_email_count == 1
    assert "jean.dupont" not in _report_text(result.report)
    assert "example.com" not in _report_text(result.report)


@pytest.mark.parametrize(
    "phone",
    ["06 12 34 56 78", "07.12.34.56.78", "+33 6 12 34 56 78"],
)
def test_removes_french_mobile_formats(phone):
    raw = f"""
Jean Dupont
Téléphone : {phone}
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert phone not in result.text
    assert phone.replace(" ", "").replace(".", "") not in result.text.replace(" ", "").replace(".", "")
    assert "Lead DevOps chez EDF" in result.text
    assert result.report.removed_phone_count == 1
    assert _secret_text(phone).replace(".", "") not in _report_text(result.report).replace(".", "")


@pytest.mark.parametrize(
    "url",
    ["https://www.linkedin.com/in/jean-dupont", "https://fr.linkedin.com/in/jean-dupont", "https://lnkd.in/abc123"],
)
def test_removes_linkedin_profile_and_short_urls(url):
    raw = f"""
Jean Dupont
LinkedIn : {url}
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert url not in result.text
    assert "linkedin.com/in" not in result.text.lower()
    assert "lnkd.in" not in result.text.lower()
    assert "Consultant cloud chez BNP Paribas" in result.text
    assert result.report.removed_linkedin_count == 1
    assert "jean-dupont" not in _report_text(result.report)
    assert "lnkd.in" not in _report_text(result.report)


def test_removes_github_profile_urls_but_preserves_github_actions():
    raw = f"""
Jean Dupont
GitHub : https://github.com/jdupont
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert "https://github.com/jdupont" not in result.text
    assert "github.com/jdupont" not in result.text.lower()
    assert "GitHub Actions" in result.text
    assert result.report.removed_github_profile_count == 1
    assert "jdupont" not in _report_text(result.report)


@pytest.mark.parametrize("url", ["https://portfolio.dev", "www.jean-dupont.fr"])
def test_removes_personal_and_portfolio_urls(url):
    raw = f"""
Jean Dupont
Portfolio : {url}
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert url not in result.text
    assert "portfolio.dev" not in result.text.lower()
    assert "jean-dupont.fr" not in result.text.lower()
    assert "API REST" in result.text
    assert result.report.removed_url_count == 1
    assert "portfolio.dev" not in _report_text(result.report)
    assert "jean-dupont.fr" not in _report_text(result.report)


def test_preserves_technical_terms_that_look_like_contact_tokens():
    raw = f"""
{BUSINESS_CONTENT}
Projet Th@Bot : automatisation de réponses clients.
Campagnes LinkedIn Ads pour acquisition B2B.
Industrialisation GitHub Actions, emailing transactionnel, Node.js, .NET et API REST.
"""

    result = _sanitize(raw)

    for expected in ["Th@Bot", "emailing", "LinkedIn Ads", "GitHub Actions", "Node.js", ".NET", "API REST"]:
        assert expected in result.text
    assert result.report.removed_email_count == 0
    assert result.report.removed_linkedin_count == 0
    assert result.report.removed_github_profile_count == 0


def test_preserves_space_before_dotnet_framework_token():
    raw = f"""
{BUSINESS_CONTENT}
Développeur full stack React .NET
Développement d'applications .NET full stack et migration d'API .NET en .NET Core.
"""

    result = _sanitize(raw)

    assert "React .NET" in result.text
    assert "applications .NET full stack" in result.text
    assert "API .NET en .NET Core" in result.text
    assert "React.NET" not in result.text
    assert "applications.NET" not in result.text


def test_removes_icon_prefixed_header_address_line():
    raw = f"""
Jean Dupont
3 rue de Genève
74100 Annemasse
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert "3 rue de Genève" not in result.text
    assert "74100 Annemasse" not in result.text
    assert "Lead DevOps chez EDF" in result.text


def test_removes_hellowork_boilerplate_lines_without_removing_experience_lines():
    raw = f"""
CV téléchargé depuis Hellowork
Profil consulté le 04/06/2026
Voir le profil candidat
Mettre à jour mon CV
{BUSINESS_CONTENT}
Expérience Hellowork utile : intégration d'une API REST pour un jobboard interne.
"""

    result = _sanitize(raw)

    assert "CV téléchargé" not in result.text
    assert "Profil consulté" not in result.text
    assert "Voir le profil" not in result.text
    assert "Mettre à jour mon CV" not in result.text
    assert "Lead DevOps chez EDF" in result.text
    assert "Expérience Hellowork utile" in result.text
    assert result.report.removed_hellowork_line_count == 4


@pytest.mark.parametrize("label", ["Coordonnées", "Contact", "Téléphone", "Email", "LinkedIn"])
def test_removes_isolated_contact_label_only_lines(label):
    raw = f"""
Jean Dupont
{label}
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert f"\n{label}\n" not in f"\n{result.text}\n"
    assert "Compétences" in result.text
    assert result.report.removed_contact_label_line_count == 1


def test_removes_likely_header_address_but_preserves_experience_location_facts():
    raw = f"""
Jean Dupont
12 rue de la Paix
75008 Paris
{BUSINESS_CONTENT}
2019 - 2020 : Mission chez Société Générale - La Défense / Paris
- Déploiement d'une plateforme Kubernetes pour les équipes data.
"""

    result = _sanitize(raw)

    assert "12 rue de la Paix" not in result.text
    assert "75008 Paris" not in result.text
    assert "Mission chez Société Générale - La Défense / Paris" in result.text
    assert "plateforme Kubernetes" in result.text
    assert result.report.removed_address_line_count == 2


def test_returns_report_with_counts_and_no_raw_sensitive_substrings():
    raw = f"""
Jean Dupont
Email : jean.dupont@example.com
Mobile : 06 12 34 56 78
LinkedIn : https://linkedin.com/in/jean-dupont
GitHub : https://github.com/jdupont
Portfolio : https://portfolio.dev
12 rue de la Paix
75008 Paris
CV téléchargé depuis Hellowork
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)
    report_text = _report_text(result.report)

    assert result.report.raw_chars == len(raw)
    assert result.report.sanitized_chars == len(result.text)
    assert result.report.removed_email_count == 1
    assert result.report.removed_phone_count == 1
    assert result.report.removed_linkedin_count == 1
    assert result.report.removed_github_profile_count == 1
    assert result.report.removed_url_count == 1
    assert result.report.removed_address_line_count == 2
    assert result.report.removed_hellowork_line_count == 1
    for forbidden in [
        "jean.dupont@example.com",
        "0612345678",
        "linkedin.com/in/jean-dupont",
        "github.com/jdupont",
        "portfolio.dev",
        "rue de la paix",
        "dupont",
    ]:
        assert _secret_text(forbidden) not in report_text


def test_raises_safe_error_when_sanitized_text_becomes_too_short():
    raw = """
Jean Dupont
jean.dupont@example.com
06 12 34 56 78
https://linkedin.com/in/jean-dupont
Coordonnées
Contact
"""

    with pytest.raises(SourceSanitizationError) as exc_info:
        sanitize_source_text(raw, candidate_first_name="Jean", min_chars=120)

    message = str(exc_info.value).lower()
    assert "jean.dupont" not in message
    assert "06 12 34 56 78" not in message
    assert "linkedin.com/in" not in message


def test_removes_hellowork_ats_metadata_not_needed_in_client_cv():
    raw = f"""
Jean Dupont
Disponibilité : ASAP
Salaire souhaité : 55k€
Permis B
Mobilité : France
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert "Disponibilité" not in result.text
    assert "ASAP" not in result.text
    assert "Salaire souhaité" not in result.text
    assert "55k" not in result.text
    assert "Permis B" not in result.text
    assert "Mobilité : France" not in result.text
    assert "Architecte Solution AWS" in result.text
    assert "Lead DevOps chez EDF" in result.text
    assert result.report.removed_hellowork_line_count == 4


def test_removes_tjm_hellowork_metadata():
    raw = f"""
Jean Dupont
TJM souhaité: 500 €/jour
{BUSINESS_CONTENT}
"""

    result = _sanitize(raw)

    assert "TJM" not in result.text
    assert "500 €/jour" not in result.text
    assert "Architecte Solution AWS" in result.text
    assert "Lead DevOps chez EDF" in result.text
    assert result.report.removed_hellowork_line_count == 1


def test_preserves_remote_in_experience_or_location_context():
    raw = f"""
{BUSINESS_CONTENT}
2021 - 2022 : Mission Remote full-stack chez client final
- Développement d'API REST et coordination avec les équipes produit distribuées.
"""

    result = _sanitize(raw)

    assert "Mission Remote full-stack chez client final" in result.text
    assert "équipes produit distribuées" in result.text
    assert result.report.removed_hellowork_line_count == 0


def test_removes_project_url_while_preserving_project_name_and_contribution_sentence():
    raw = f"""
{BUSINESS_CONTENT}
Participation au développement de Th@Bot (lien: https://thbot.example.com) avec GitHub Actions
"""

    result = _sanitize(raw)

    assert "https://thbot.example.com" not in result.text
    assert "thbot.example.com" not in result.text
    assert "Participation au développement" in result.text
    assert "Th@Bot" in result.text
    assert "GitHub Actions" in result.text
    assert result.report.removed_url_count == 1
    assert "thbot" not in _report_text(result.report)


def test_removes_bare_project_domain_urls_in_common_contexts():
    raw = f"""
{BUSINESS_CONTENT}
Projet thbot.example.com/demo livré, portfolio.dev validé.
Contribution (site: jean-dupont.fr/projets) avec Node.js et API REST.
"""

    result = _sanitize(raw)

    for forbidden in ["thbot.example.com/demo", "portfolio.dev", "jean-dupont.fr/projets"]:
        assert forbidden not in result.text
        assert forbidden not in _report_text(result.report)
    assert "Projet" in result.text
    assert "Contribution" in result.text
    assert "Node.js" in result.text
    assert "API REST" in result.text
    assert result.report.removed_url_count == 3


class TestRealisticHelloworkFixture:
    def test_sanitizes_realistic_hellowork_cv_end_to_end_without_losing_business_content(self):
        raw = """
Jean Dupont
Développeur Full Stack Senior / Lead Tech
Coordonnées
Email : jean@example.com
Mobile : 06 12 34 56 78
LinkedIn : https://www.linkedin.com/in/jean-dupont
GitHub : https://github.com/jean
Portfolio : https://jean-dupont.dev
Adresse : 12 rue de la Paix, 75008 Paris

CV téléchargé depuis Hellowork
Profil consulté par W hub
Mettre à jour mon CV
Disponibilité : immédiate
TJM souhaité : 650 €/jour
Type de contrat : CDI ou freelance longue mission
Contrat souhaité : CDI, portage salarial ou mission freelance
Permis B
Mobilité : Paris, Île-de-France, remote partiel
Salaire souhaité : 60 k€ à 70 k€ brut annuel

Compétences
Langages et frameworks : JavaScript, TypeScript, Node.js, React, Next.js, Python, FastAPI, .NET.
Back-end et intégration : API REST, GraphQL, PostgreSQL, MongoDB, Redis, RabbitMQ, architecture hexagonale.
DevOps et qualité : Docker, Kubernetes, GitHub Actions, Terraform, GitLab CI, SonarQube, tests unitaires, tests d'intégration.
Produit et acquisition : analytics, tracking RGPD, campagnes LinkedIn Ads, dashboards métier, optimisation de tunnels.
Méthodes : Scrum, Kanban, discovery produit, ateliers fonctionnels, documentation technique, mentorat de développeurs juniors.

Formations
2014 - 2016 : Master Expert en ingénierie logicielle, Université Paris-Saclay.
Projet de fin d'études : plateforme de supervision d'objets connectés avec API REST, tableau de bord temps réel et règles d'alerte configurables.
2011 - 2014 : Licence informatique, Université de Lille.
Cours principaux : algorithmique, bases de données relationnelles, systèmes distribués, sécurité applicative et conception orientée objet.
Certifications : Professional Scrum Master I, AWS Cloud Practitioner, formation interne sécurité OWASP Top 10.

Expériences
Janvier 2023 - Mai 2026 : Lead développeur full stack - Th@Bot Labs
- Cadrage technique d'un assistant conversationnel nommé Th@Bot pour le support client B2B, avec qualification automatique des demandes et escalade vers les équipes métier.
- Développement de services Node.js et Python exposant une API REST sécurisée par OAuth2, avec gestion des quotas, retries, traces distribuées et monitoring Prometheus.
- Mise en place de pipelines GitHub Actions pour construire, tester et déployer les microservices sur Kubernetes, avec environnements de préproduction reproductibles.
- Animation de revues de code, rédaction d'ADR, accompagnement de quatre développeurs et coordination avec l'équipe produit pour prioriser les fonctionnalités à forte valeur.
- Amélioration de la qualité : couverture de tests passée de 38 % à 82 %, baisse des incidents de production et réduction du temps moyen de livraison.

Septembre 2020 - Décembre 2022 : Ingénieur full stack senior - Retail Media Conseil
- Refonte d'un portail de pilotage de campagnes LinkedIn Ads et Google Ads utilisé par les équipes marketing de plusieurs enseignes nationales.
- Conception de composants React réutilisables, intégration de tableaux de bord d'attribution et optimisation des temps de chargement sur des volumes élevés de données.
- Création d'une API REST d'export de rapports, sécurisée par rôles, utilisée par les contrôleurs de gestion pour consolider les budgets mensuels.
- Industrialisation des déploiements avec Docker, GitHub Actions et migrations PostgreSQL versionnées, en collaboration avec l'équipe infrastructure.
- Participation aux ateliers de cadrage avec les métiers, formalisation des règles de tracking, documentation des endpoints et transfert de compétences aux équipes internes.

Mars 2017 - Août 2020 : Développeur web confirmé - Banque Nord Europe
- Maintenance évolutive d'une application de souscription en ligne, incluant parcours client, workflow de validation, génération de documents et connecteurs vers le système d'information.
- Développement de modules Node.js et .NET pour synchroniser les dossiers, exposer une API REST interne et fiabiliser les échanges avec les partenaires externes.
- Mise en place d'une stratégie de tests automatisés, de revues croisées et d'indicateurs de qualité permettant de réduire les régressions en recette.
- Collaboration quotidienne avec les analystes fonctionnels, le RSSI et les exploitants pour respecter les contraintes de sécurité, d'audit et de disponibilité.
- Contribution à la migration progressive d'une architecture monolithique vers des services découplés, sans interruption des opérations métier.

Réalisations complémentaires
- Création de kits de démarrage projet pour accélérer les nouvelles équipes : structure repository, conventions TypeScript, templates de pipelines et exemples d'API REST.
- Mise en place de rituels d'amélioration continue, suivi de dette technique, partage de bonnes pratiques GitHub Actions et ateliers de sensibilisation sécurité.
- Contribution à des communautés internes autour de Node.js, React, observabilité, architecture applicative et collaboration produit-tech.

Centres d'intérêt
Veille sur les architectures cloud natives, automatisation des tests, accessibilité web, produits SaaS B2B et usages responsables de l'intelligence artificielle.
Footer : document de candidature exporté depuis hellowork.com pour le profil candidat.
"""

        result = sanitize_source_text(raw, candidate_first_name="Jean")
        sanitized = result.text
        report_text = repr(result.report).casefold()

        for forbidden in [
            "jean@example.com",
            "06 12 34 56 78",
            "linkedin.com/in/jean-dupont",
            "github.com/jean",
            "Adresse : 12 rue de la Paix, 75008 Paris",
            "12 rue de la Paix",
            "jean-dupont.dev",
            "CV téléchargé depuis Hellowork",
            "Profil consulté par W hub",
            "Mettre à jour mon CV",
            "Disponibilité : immédiate",
            "TJM souhaité : 650 €/jour",
            "Type de contrat : CDI ou freelance longue mission",
            "Contrat souhaité : CDI, portage salarial ou mission freelance",
            "Permis B",
            "Mobilité : Paris, Île-de-France, remote partiel",
            "Salaire souhaité : 60 k€ à 70 k€ brut annuel",
            "hellowork.com",
        ]:
            assert forbidden not in sanitized

        assert "Jean" in sanitized
        assert "Nom : Dupont" not in sanitized
        assert "Compétences" in sanitized
        assert "JavaScript, TypeScript, Node.js, React, Next.js, Python" in sanitized
        assert "Formations" in sanitized
        assert "2014 - 2016: Master Expert en ingénierie logicielle" in sanitized
        assert "2011 - 2014: Licence informatique" in sanitized

        for expected in [
            "Janvier 2023 - Mai 2026: Lead développeur full stack - Th@Bot Labs",
            "assistant conversationnel nommé Th@Bot",
            "services Node.js et Python exposant une API REST",
            "pipelines GitHub Actions",
            "Septembre 2020 - Décembre 2022: Ingénieur full stack senior - Retail Media Conseil",
            "campagnes LinkedIn Ads et Google Ads",
            "API REST d'export de rapports",
            "Mars 2017 - Août 2020: Développeur web confirmé - Banque Nord Europe",
            "modules Node.js et .NET",
            "GitHub Actions",
            "LinkedIn Ads",
            "Th@Bot",
            "Node.js",
            "API REST",
        ]:
            assert expected in sanitized

        assert sanitized.index("Compétences") < sanitized.index("Formations") < sanitized.index("Expériences")
        assert result.report.removed_email_count >= 1
        assert result.report.removed_phone_count >= 1
        assert result.report.removed_url_count >= 1
        assert result.report.removed_linkedin_count >= 1
        assert result.report.removed_github_profile_count >= 1
        assert result.report.removed_hellowork_line_count >= 1
        assert result.report.removed_address_line_count >= 1
        assert result.report.removed_contact_label_line_count >= 1

        for forbidden_report_value in [
            "jean@example.com",
            "06 12 34 56 78",
            "linkedin.com/in/jean",
            "github.com/jean",
            "12 rue de la paix",
            "jean-dupont.dev",
        ]:
            assert forbidden_report_value.casefold() not in report_text

        assert len(sanitized) >= 400
