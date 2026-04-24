from typing import Any

import pytest

from app.api.webhook import receive_generic_message
from app.core.config import reset_settings_cache
from app.schemas.generic_webhook import GenericWebhookEvent
from app.services.agent_service import AgentService
from app.services.audio_queue import AudioTranscriptionQueue
from app.services.audio_service import AudioService
from app.services.lead_service import LeadService
from app.services.redis_service import RedisService
from app.services.session_service import SessionService
from tests.test_webhook import FakeWahaService, InMemoryRedis


@pytest.fixture()
def services(monkeypatch: pytest.MonkeyPatch, tmp_path) -> dict[str, Any]:
    db_path = tmp_path / "leads.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("WAHA_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_WEBHOOK", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("WHISPER_MODEL", "mock")
    reset_settings_cache()

    redis_service = RedisService(client=InMemoryRedis())
    lead_service = LeadService()
    agent_service = AgentService()
    audio_service = AudioService()
    audio_queue = AudioTranscriptionQueue(audio_service)
    comm_service = FakeWahaService()
    session_service = SessionService(redis_service)

    return {
        "redis_service": redis_service,
        "lead_service": lead_service,
        "agent_service": agent_service,
        "audio_queue": audio_queue,
        "comm_service": comm_service,
        "session_service": session_service,
    }


def test_generic_webhook_text(services: dict[str, Any]) -> None:
    payload = {
        "id": "evt-1",
        "timestamp": 1710960000000,
        "session": "default",
        "event": "message",
        "message": {
            "id": "msg-1",
            "timestamp": 1710960000,
            "from": "551199999999@c.us",
            "body": "Oi, meu nome é Ana",
            "has_media": False,
        },
    }
    message = GenericWebhookEvent(**payload)
    response = receive_generic_message(
        message,
        x_webhook_secret=None,
        webhook_secret=None,
        secret=None,
        redis_service=services["redis_service"],
        lead_service=services["lead_service"],
        agent_service=services["agent_service"],
        audio_queue=services["audio_queue"],
        comm_service=services["comm_service"],
        session_service=services["session_service"],
    )
    assert response.reply
