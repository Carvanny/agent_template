import pytest

from app.core.config import reset_settings_cache
from app.services.agent_service import AgentService


def test_agent_fallback_to_faq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    reset_settings_cache()
    service = AgentService()
    result = service.generate_reply("não sei", None, "")
    assert result["used_faq"] is True


def _patch_agno_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make agno.agent.Agent.run raise a 429 RESOURCE_EXHAUSTED error."""
    import unittest.mock as mock

    fake_agent = mock.MagicMock()
    fake_agent.run.side_effect = Exception(
        "429 RESOURCE_EXHAUSTED: You exceeded your current quota"
    )
    fake_agent_cls = mock.MagicMock(return_value=fake_agent)
    monkeypatch.setattr("agno.agent.Agent", fake_agent_cls, raising=False)


def test_agent_rate_limit_returns_friendly_message_pt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    reset_settings_cache()
    _patch_agno_rate_limit(monkeypatch)

    service = AgentService()
    result = service.generate_reply("Oi", None, "", language="pt")

    assert result["used_faq"] is False
    assert "429" not in result["reply"]
    assert "quota" not in result["reply"].lower()
    assert "minutos" in result["reply"]


def test_agent_rate_limit_returns_friendly_message_es(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    reset_settings_cache()
    _patch_agno_rate_limit(monkeypatch)

    service = AgentService()
    result = service.generate_reply("Hola", None, "", language="es")

    assert result["used_faq"] is False
    assert "429" not in result["reply"]
    assert "quota" not in result["reply"].lower()
    assert "minutos" in result["reply"]
