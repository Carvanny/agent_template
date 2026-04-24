from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.webhook import receive_waha_message
from app.core.config import reset_settings_cache
from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.schemas.webhook import WahaWebhookEvent
from app.services.agent_service import AgentService
from app.services.audio_queue import AudioTranscriptionQueue
from app.services.audio_service import AudioService
from app.services.lead_service import LeadService
from app.services.redis_service import RedisService
from app.services.session_service import SessionService
from app.services.waha_service import WahaService


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float]] = {}

    def _expired(self, key: str) -> bool:
        if key not in self.store:
            return True
        _, expires_at = self.store[key]
        if expires_at < 0:
            return False
        return expires_at < self._now()

    def _now(self) -> float:
        import time

        return time.time()

    def exists(self, key: str) -> int:
        if self._expired(key):
            self.store.pop(key, None)
            return 0
        return 1

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = (value, self._now() + ttl)

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
        if nx and not self._expired(key):
            return None
        ttl = ex if ex is not None else -1
        expires_at = self._now() + ttl if ttl >= 0 else -1
        self.store[key] = (value, expires_at)
        return True

    def get(self, key: str) -> str | None:
        if self._expired(key):
            self.store.pop(key, None)
            return None
        return self.store[key][0]

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakeAudioService(AudioService):
    def transcribe(self, audio_path: str) -> str:
        return "quero colchão queen"


class FakeAudioQueue(AudioTranscriptionQueue):
    def __init__(self, audio_service: AudioService) -> None:
        self.audio_service = audio_service

    def transcribe(self, audio_path: str) -> str:
        return self.audio_service.transcribe(audio_path)

    def submit(self, audio_path: str):
        from concurrent.futures import Future

        future: Future[str] = Future()
        future.set_result(self.audio_service.transcribe(audio_path))
        return future

    def shutdown(self) -> None:
        return None


class FakeWahaService(WahaService):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict[str, str]] = []
        self.seen: list[dict[str, str]] = []
        self.lid_map: dict[str, str] = {}

    def download_audio(self, audio_url: str) -> str:
        path = Path("/tmp/fake_audio.ogg")
        path.write_bytes(b"fake")
        return str(path)

    def send_seen(self, session: str, chat_id: str) -> None:
        self.seen.append({"session": session, "chat_id": chat_id})

    def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
        self.sent.append({"session": session, "chat_id": chat_id, "text": text, "reply_to": reply_to or ""})

    def get_phone_by_lid(self, session: str, lid: str) -> str | None:
        return self.lid_map.get(lid)


@pytest.fixture()
def services(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    db_path = tmp_path / "leads.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("WAHA_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_WEBHOOK", "false")
    monkeypatch.setenv("ALLOW_WEBHOOK_QUERY_SECRET", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("WHISPER_MODEL", "mock")
    reset_settings_cache()

    redis_service = RedisService(client=InMemoryRedis())
    lead_service = LeadService()
    agent_service = AgentService()
    audio_service = FakeAudioService()
    audio_queue = FakeAudioQueue(audio_service)
    waha_service = FakeWahaService()
    session_service = SessionService(redis_service)

    return {
        "redis_service": redis_service,
        "lead_service": lead_service,
        "agent_service": agent_service,
        "audio_queue": audio_queue,
        "comm_service": waha_service,
        "session_service": session_service,
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "evt-1",
        "timestamp": 1710960000000,
        "session": "default",
        "engine": "GOWS",
        "event": "message",
        "payload": {
            "id": "false_551199999999@c.us_AAAAAAAAAAAAAAAAAAAA",
            "timestamp": 1710960000,
            "from": "551199999999@c.us",
            "fromMe": False,
            "source": "app",
            "to": "551188888888@c.us",
            "participant": None,
            "body": "Oi, meu nome é Ana",
            "hasMedia": False,
        },
    }
    payload.update(overrides)
    return payload


def _invoke(payload: dict[str, Any], services: dict[str, Any]) -> Any:
    message = WahaWebhookEvent(**payload)
    return receive_waha_message(
        message,
        x_webhook_secret="test-secret",
        redis_service=services["redis_service"],
        lead_service=services["lead_service"],
        agent_service=services["agent_service"],
        audio_queue=services["audio_queue"],
        comm_service=services["comm_service"],
        session_service=services["session_service"],
    )


def test_webhook_text_flow_updates(services: dict[str, Any]) -> None:
    response = _invoke(_payload(), services)
    assert "Atualizei" in response.reply
    assert response.should_persist is False
    assert services["comm_service"].seen == [{"session": "default", "chat_id": "551199999999@c.us"}]


def test_webhook_paraguay_number_uses_spanish_rule_based_reply(services: dict[str, Any]) -> None:
    response = _invoke(
        _payload(
            payload={
                **_payload()["payload"],
                "from": "59599999999@c.us",
                "body": "meu nome é Ana",
            }
        ),
        services,
    )

    assert "Actualicé" in response.reply
    assert "¿Qué tamaño de colchón buscas" in response.reply


def test_webhook_uses_participant_for_language_detection(services: dict[str, Any]) -> None:
    response = _invoke(
        _payload(
            payload={
                **_payload()["payload"],
                "from": "120363999999999999@g.us",
                "participant": "595994381617@c.us",
                "body": "meu nome é Ana",
            }
        ),
        services,
    )

    assert "Actualicé" in response.reply
    assert "¿Qué tamaño de colchón buscas" in response.reply


def test_webhook_resolves_lid_to_detect_language(services: dict[str, Any]) -> None:
    services["comm_service"].lid_map["551199999999@lid"] = "59599999999@c.us"
    response = _invoke(
        _payload(
            payload={
                **_payload()["payload"],
                "from": "551199999999@lid",
                "participant": None,
                "body": "meu nome é Ana",
            }
        ),
        services,
    )

    assert "Actualicé" in response.reply
    assert "¿Qué tamaño de colchón buscas" in response.reply


def test_webhook_audio_flow_transcription(services: dict[str, Any]) -> None:
    response = _invoke(
        _payload(
            payload={
                **_payload()["payload"],
                "body": "",
                "hasMedia": True,
                "media": {"url": "http://localhost:3000/api/files/file.ogg", "mimetype": "audio/ogg"},
            }
        ),
        services,
    )
    assert "tamanho do colchão" in response.reply


def test_webhook_deduplication(services: dict[str, Any]) -> None:
    payload = _payload(id="dup-1")
    _invoke(payload, services)
    response_dup = _invoke(payload, services)
    assert response_dup.reply == "Mensagem já processada."


def test_webhook_loads_lead_from_sqlite(services: dict[str, Any]) -> None:
    lead_repo = LeadRepository()
    lead_repo.upsert(
        Lead(
            id=None,
            cellnumber="+551199999999",
            name="Ana",
            mattress_size="queen",
            need=None,
            budget_range=None,
            city=None,
            urgency=None,
        )
    )
    response = _invoke(_payload(payload={**_payload()["payload"], "body": "Oi"}), services)
    assert "principal necessidade" in response.reply


def test_webhook_greeting_uses_quick_intent_reply(services: dict[str, Any]) -> None:
    response = _invoke(_payload(payload={**_payload()["payload"], "body": "Oi"}), services)

    assert "qual é o seu nome" in response.reply.lower()


def test_webhook_thanks_uses_quick_intent_reply(services: dict[str, Any]) -> None:
    response = _invoke(_payload(payload={**_payload()["payload"], "body": "Obrigado"}), services)

    assert "por nada" in response.reply.lower()


def test_webhook_price_question_routes_to_faq(services: dict[str, Any]) -> None:
    response = _invoke(_payload(payload={**_payload()["payload"], "body": "Qual o preço?"}), services)

    assert "posso te ajudar melhor por aqui" in response.reply.lower()
    assert "faq" in response.reply.lower()


def test_webhook_human_request_uses_quick_intent_reply(services: dict[str, Any]) -> None:
    response = _invoke(
        _payload(payload={**_payload()["payload"], "body": "Quero falar com um atendente"}), services
    )

    assert "especialista" in response.reply.lower()
    assert "qual é o seu nome" in response.reply.lower()


def test_webhook_missing_secret_is_unauthorized(services: dict[str, Any]) -> None:
    payload = _payload(payload={**_payload()["payload"], "body": "Oi"})
    message = WahaWebhookEvent(**payload)
    with pytest.raises(HTTPException) as exc_info:
        receive_waha_message(
            message,
            x_webhook_secret=None,
            redis_service=services["redis_service"],
            lead_service=services["lead_service"],
            agent_service=services["agent_service"],
            audio_queue=services["audio_queue"],
            comm_service=services["comm_service"],
            session_service=services["session_service"],
        )
    assert exc_info.value.status_code == 401


def test_webhook_ignores_non_message_events(services: dict[str, Any]) -> None:
    response = _invoke(
        _payload(
            event="session.status",
            payload={"name": "default", "status": "WORKING"},
        ),
        services,
    )

    assert response.reply == "Evento ignorado."
    assert response.should_persist is False


def test_webhook_send_failure_returns_503_and_not_processed(services: dict[str, Any]) -> None:
    class FailingSendWahaService(FakeWahaService):
        def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
            raise RuntimeError("network down")

    payload = _payload(id="send-fail-1")
    services["comm_service"] = FailingSendWahaService()

    with pytest.raises(HTTPException) as exc_info:
        _invoke(payload, services)

    assert exc_info.value.status_code == 503
    assert services["redis_service"].is_processed("send-fail-1") is False


def test_webhook_send_seen_failure_does_not_abort_reply(services: dict[str, Any]) -> None:
    class FailingSeenWahaService(FakeWahaService):
        def send_seen(self, session: str, chat_id: str) -> None:
            raise RuntimeError("seen down")

    services["comm_service"] = FailingSeenWahaService()

    response = _invoke(_payload(id="seen-fail-1"), services)

    assert response.reply
    assert response.should_persist is False


def test_webhook_audio_temp_file_is_cleaned_up(services: dict[str, Any]) -> None:
    audio_payload = _payload(
        id="audio-cleanup-1",
        payload={
            **_payload()["payload"],
            "body": "",
            "hasMedia": True,
            "media": {"url": "http://localhost:3000/api/files/file.ogg", "mimetype": "audio/ogg"},
        },
    )

    _invoke(audio_payload, services)

    assert Path("/tmp/fake_audio.ogg").exists() is False


def test_webhook_returns_in_processing_when_lock_is_already_acquired(services: dict[str, Any]) -> None:
    payload_id = "processing-1"
    payload = _payload(id=payload_id)

    acquired = services["redis_service"].acquire_processing(payload_id)
    assert acquired is True

    response = _invoke(payload, services)

    assert response.reply == "Mensagem em processamento."
    assert response.should_persist is False
    assert services["redis_service"].is_processed(payload_id) is False


def test_webhook_processes_event_after_processing_lock_release(services: dict[str, Any]) -> None:
    payload_id = "processing-release-1"
    payload = _payload(id=payload_id)

    acquired = services["redis_service"].acquire_processing(payload_id)
    assert acquired is True

    services["redis_service"].release_processing(payload_id)
    response = _invoke(payload, services)

    assert response.reply
    assert response.reply != "Mensagem em processamento."
    assert services["redis_service"].is_processed(payload_id) is True
