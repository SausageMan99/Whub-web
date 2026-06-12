from src.config import Settings


def test_content_preserving_flags_default_false(monkeypatch):
    monkeypatch.delenv("WHUB_CONTENT_PRESERVING_PIPELINE", raising=False)
    monkeypatch.delenv("WHUB_CONTENT_PRESERVING_SHADOW", raising=False)

    settings = Settings()

    assert settings.whub_content_preserving_pipeline is False
    assert settings.whub_content_preserving_shadow is False


def test_content_preserving_flags_can_be_enabled(monkeypatch):
    monkeypatch.setenv("WHUB_CONTENT_PRESERVING_PIPELINE", "true")
    monkeypatch.setenv("WHUB_CONTENT_PRESERVING_SHADOW", "true")

    settings = Settings()

    assert settings.whub_content_preserving_pipeline is True
    assert settings.whub_content_preserving_shadow is True
