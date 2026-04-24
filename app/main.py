from fastapi import FastAPI
from app.api.webhook import router as webhook_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.prompts import warm_prompt_cache
from app.services.agent_service import AgentService
from app.services.audio_queue import AudioTranscriptionQueue
from app.services.audio_service import AudioService
from app.services.communication_factory import build_communication_service
from app.services.lead_service import LeadService
from app.services.redis_service import RedisService
from app.services.session_service import SessionService

settings = get_settings()
configure_logging()
app = FastAPI(title=settings.app_name)
app.include_router(webhook_router)


@app.on_event("startup")
def startup() -> None:
    app.state.redis_service = RedisService()
    app.state.lead_service = LeadService()
    app.state.agent_service = AgentService()
    app.state.audio_service = AudioService()
    app.state.audio_queue = AudioTranscriptionQueue(
        app.state.audio_service, max_workers=settings.audio_queue_max_workers
    )
    app.state.communication_service = build_communication_service()
    app.state.session_service = SessionService(app.state.redis_service)
    warm_prompt_cache()


@app.on_event("shutdown")
def shutdown() -> None:
    if getattr(app.state, "audio_queue", None):
        app.state.audio_queue.shutdown()
    if getattr(app.state, "redis_service", None):
        app.state.redis_service.close()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
