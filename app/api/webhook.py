import logging
import os
import re
import time
from concurrent.futures import TimeoutError
from secrets import compare_digest
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.lead import Lead
from app.schemas.generic_webhook import GenericWebhookEvent
from app.schemas.webhook import OutboundReply, WahaMessagePayload, WahaWebhookEvent
from app.services.agent_service import AgentService
from app.services.audio_queue import AudioTranscriptionQueue
from app.services.lead_service import LeadService
from app.services.redis_service import RedisService
from app.services.session_service import SessionService
from app.services.communication import CommunicationService
from app.utils.language import detect_language_from_phone
from app.utils.pii import mask_phone, mask_waha_id
from app.utils.phone import normalize_phone
from app.utils.text import normalize_text

logger = logging.getLogger("webhook")

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _audio_ack_message(language: str) -> str:
    if language == "es":
        return "Recibí tu audio, ya lo escucho y te respondo."
    return "Recebi seu áudio, já vou ouvir e te respondo."


def _faq_reply(language: str, settings: object) -> str:
    if language == "es":
        return (
            "Puedo ayudarte mejor por aquí: "
            f"{settings.faq_url} \n"
            "Si prefieres, también puedo derivar tu atención a un especialista."
        )
    return (
        "Posso te ajudar melhor por aqui: "
        f"{settings.faq_url} \n"
        "Se preferir, também posso encaminhar seu atendimento para um especialista."
    )


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _quick_intent_reply(
    text: str,
    lead: Lead,
    lead_service: LeadService,
    language: str,
    settings: object,
) -> str | None:
    normalized = normalize_text(text)
    lowered = normalized.lower()
    if not lowered:
        return None

    greeting_patterns = [
        r"\b(oi|olá|ola|eai|ei|hello|hi)\b",
        r"\bbom dia\b",
        r"\bboa tarde\b",
        r"\bboa noite\b",
    ]
    thanks_patterns = [r"\b(obrigad[ao]|valeu|agradecid[ao]|thanks|gracias)\b"]
    human_patterns = [r"\b(atendente|humano|pessoa|especialista|vendedor|consultor)\b"]
    price_patterns = [r"\b(preço|preco|valor|custa|custam|orçamento|orcamento)\b"]
    address_patterns = [r"\b(endereço|endereco|localiza|onde fica|localização|ubicación|direccion)\b"]
    hours_patterns = [r"\b(hor[aá]rio|horario|aberto|fecha|funciona|atendimento)\b"]
    catalog_patterns = [r"\b(catálogo|catalogo|card[aá]pio|menu|lista)\b"]

    next_question = lead_service.next_question(lead, language=language)

    if _matches_any(lowered, greeting_patterns):
        if next_question:
            return (
                f"¡Hola! {next_question}"
                if language == "es"
                else f"Olá! {next_question}"
            )
        return "¿En qué puedo ayudarte?" if language == "es" else "Como posso te ajudar?"

    if _matches_any(lowered, thanks_patterns):
        return (
            "De nada! Si necesitas algo más, solo dime."
            if language == "es"
            else "Por nada! Se precisar de algo, é só me chamar."
        )

    if _matches_any(lowered, human_patterns):
        if next_question:
            return (
                "Puedo derivarte con un especialista. Antes, necesito algunos datos. "
                f"{next_question}"
                if language == "es"
                else "Posso encaminhar para um especialista. Antes, preciso de alguns dados. "
                f"{next_question}"
            )
        return (
            "Puedo derivarte con un especialista. ¿Quieres que lo haga?"
            if language == "es"
            else "Posso encaminhar para um especialista. Quer que eu faça isso?"
        )

    if _matches_any(lowered, price_patterns + address_patterns + hours_patterns + catalog_patterns):
        return _faq_reply(language, settings)

    short_ack = {"ok", "okay", "certo", "beleza", "blz", "sim", "isso", "isso mesmo", "claro", "yes", "si"}
    if lowered in short_ack and next_question:
        return next_question

    return None


def _resolve_lead(
    session_service: SessionService,
    lead_service: LeadService,
    chat_id: str,
    cellnumber: str,
) -> tuple[Lead, str, dict | None]:
    session = session_service.load(chat_id, cellnumber)
    known_lead = None
    if session and session.get("known_lead"):
        known_lead = Lead(**session["known_lead"])
    if not known_lead:
        known_lead = lead_service.get_known_lead(cellnumber)
    lead = known_lead or Lead(id=None, cellnumber=cellnumber)
    session_summary = session.get("summary", "") if session else ""
    return lead, session_summary, session


def _build_reply(
    text: str,
    lead: Lead,
    session_summary: str,
    response_language: str,
    lead_service: LeadService,
    agent_service: AgentService,
    settings: object,
) -> tuple[str, bool, Lead]:
    updates = lead_service.extract_updates(text)
    allow_override = lead_service.should_allow_override(text)
    lead, changed_fields = lead_service.apply_updates(lead, updates, allow_override)

    if not changed_fields:
        quick_reply = _quick_intent_reply(text, lead, lead_service, response_language, settings)
        if quick_reply:
            return quick_reply, False, lead

    use_rule_based = bool(changed_fields) or not agent_service.is_llm_enabled()
    if use_rule_based:
        reply_text = lead_service.build_rule_based_reply(
            lead,
            changed_fields,
            language=response_language,
        )
        used_faq = False
    else:
        result = agent_service.generate_reply(
            text,
            lead,
            session_summary,
            language=response_language,
        )
        reply_text = result["reply"]
        used_faq = result.get("used_faq", False)

    return reply_text, used_faq, lead


def _update_session_and_persist(
    *,
    session_service: SessionService,
    lead_service: LeadService,
    chat_id: str,
    cellnumber: str,
    payload_id: str,
    incoming_text: str,
    reply_text: str,
    response_language: str,
    lead: Lead,
    existing_summary: str,
) -> bool:
    session_payload = {
        "last_message_id": payload_id,
        "cellnumber": cellnumber,
        "chat_id": chat_id,
        "last_user_text": incoming_text,
        "known_lead": asdict(lead),
        "summary": session_service.build_summary(existing_summary, incoming_text, reply_text),
        "language": response_language,
        "last_interaction_at": time.time(),
        "pending_audio": False,
    }
    session_service.save(chat_id, cellnumber, session_payload)

    should_persist = False
    if lead_service.is_complete(lead):
        lead.status = "completed"
        should_persist = lead_service.persist_if_complete(lead, completed=True)

    return should_persist


def get_redis_service(request: Request) -> RedisService:
    return request.app.state.redis_service


def get_lead_service(request: Request) -> LeadService:
    return request.app.state.lead_service


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service


def get_audio_queue(request: Request) -> AudioTranscriptionQueue:
    return request.app.state.audio_queue


def get_comm_service(request: Request) -> CommunicationService:
    return request.app.state.communication_service


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("/waha", response_model=OutboundReply)
def receive_waha_message(
    payload: WahaWebhookEvent,
    x_webhook_secret: str | None = Header(default=None),
    webhook_secret: str | None = Query(default=None),
    secret: str | None = Query(default=None),
    redis_service: RedisService = Depends(get_redis_service),
    lead_service: LeadService = Depends(get_lead_service),
    agent_service: AgentService = Depends(get_agent_service),
    audio_queue: AudioTranscriptionQueue = Depends(get_audio_queue),
    comm_service: CommunicationService = Depends(get_comm_service),
    session_service: SessionService = Depends(get_session_service),
) -> OutboundReply:
    settings = get_settings()
    if settings.allow_unauthenticated_webhook:
        provided_secret = None
    else:
        provided_secret = x_webhook_secret
        if settings.allow_webhook_query_secret and not provided_secret:
            provided_secret = webhook_secret or secret

        if not settings.waha_webhook_secret or not provided_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")
        if not compare_digest(provided_secret, settings.waha_webhook_secret):
            raise HTTPException(status_code=401, detail="invalid webhook secret")

    if payload.event != "message":
        return OutboundReply(reply="Evento ignorado.", used_faq=False, should_persist=False)

    try:
        message_payload = WahaMessagePayload.model_validate(payload.payload or {})
    except ValidationError:
        logger.exception(
            "waha_invalid_message_payload",
            extra={
                "event": payload.event,
                "payload_id": payload.id,
            },
        )
        raise HTTPException(status_code=400, detail="invalid message payload")

    if message_payload.fromMe:
        return OutboundReply(reply="Mensagem do próprio agente ignorada.", used_faq=False, should_persist=False)

    if redis_service.is_processed(payload.id):
        return OutboundReply(reply="Mensagem já processada.", used_faq=False, should_persist=False)

    if not redis_service.acquire_processing(payload.id):
        return OutboundReply(reply="Mensagem em processamento.", used_faq=False, should_persist=False)

    background_processing = False
    audio_received = False
    audio_start = 0.0
    try:
        chat_id = message_payload.from_id
        cellnumber_raw = message_payload.participant or message_payload.from_id
        resolved = comm_service.resolve_phone_identifier(payload.session, cellnumber_raw)
        if resolved is None and cellnumber_raw:
            logger.warning(
                "comm_phone_resolution_failed",
                extra={"raw_id": mask_waha_id(cellnumber_raw), "chat_id": mask_waha_id(chat_id)},
            )
        cellnumber = normalize_phone(resolved or "")
        if not cellnumber and cellnumber_raw:
            cellnumber = f"lid:{cellnumber_raw}"
        if not cellnumber:
            raise HTTPException(status_code=400, detail="invalid cellnumber")
        # Usa o mesmo identificador do contato real usado para normalizar o número.
        # Em conversas de grupo ou encaminhadas, o DDI pode estar em `participant`
        # e não em `from`.
        response_language = detect_language_from_phone(
            resolved or cellnumber_raw,
            mapping=settings.country_language_map,
        )
        logger.info(
            "language_detected",
            extra={
                "from_id": mask_waha_id(message_payload.from_id),
                "language_source": mask_waha_id(resolved or cellnumber_raw),
                "response_language": response_language,
            },
        )

        try:
            comm_service.send_seen(session=payload.session, chat_id=chat_id)
        except Exception:
            logger.exception(
                "waha_send_seen_failed",
                extra={"chat_id": mask_waha_id(chat_id), "cellnumber": mask_phone(cellnumber)},
            )

        text = message_payload.body or ""
        media_url = (message_payload.media.url if message_payload.media else None) or message_payload.mediaUrl
        mimetype = message_payload.media.mimetype if message_payload.media else None
        if message_payload.hasMedia and media_url and (mimetype or "").startswith("audio/"):
            audio_received = True
            audio_start = time.monotonic()
            audio_path = comm_service.download_audio(media_url)
            future = audio_queue.submit(audio_path)
            try:
                text = future.result(timeout=settings.audio_ack_timeout_seconds)
            except TimeoutError:
                background_processing = True
                ack_text = _audio_ack_message(response_language)
                try:
                    comm_service.send_text(session=payload.session, chat_id=chat_id, text=ack_text)
                except Exception:
                    logger.exception(
                        "waha_send_failed",
                        extra={"chat_id": mask_waha_id(chat_id), "cellnumber": mask_phone(cellnumber)},
                    )
                    raise HTTPException(status_code=503, detail="failed to send reply")

                existing_session = session_service.load(chat_id, cellnumber) or {}
                session_payload = {
                    "last_message_id": payload.id,
                    "cellnumber": cellnumber,
                    "chat_id": chat_id,
                    "last_user_text": "",
                    "known_lead": existing_session.get("known_lead"),
                    "summary": existing_session.get("summary", ""),
                    "language": response_language,
                    "last_interaction_at": time.time(),
                    "pending_audio": True,
                }
                session_service.save(chat_id, cellnumber, session_payload)

                def _background() -> None:
                    try:
                        transcript = future.result()
                        transcript = normalize_text(transcript)
                        if not transcript:
                            reply_text = (
                                "Pode enviar o áudio novamente com um pouco mais de clareza?"
                                if response_language == "pt"
                                else "¿Puedes reenviar el audio con un poco más de claridad?"
                            )
                            used_faq = False
                            lead = Lead(id=None, cellnumber=cellnumber)
                            existing_summary = (
                                session_service.load(chat_id, cellnumber) or {}
                            ).get("summary", "")
                        else:
                            lead, existing_summary, _ = _resolve_lead(
                                session_service, lead_service, chat_id, cellnumber
                            )
                            reply_text, used_faq, lead = _build_reply(
                                transcript,
                                lead,
                                existing_summary,
                                response_language,
                                lead_service,
                                agent_service,
                                settings,
                            )

                        should_persist = _update_session_and_persist(
                            session_service=session_service,
                            lead_service=lead_service,
                            chat_id=chat_id,
                            cellnumber=cellnumber,
                            payload_id=payload.id,
                            incoming_text=transcript or "",
                            reply_text=reply_text,
                            response_language=response_language,
                            lead=lead,
                            existing_summary=existing_summary,
                        )
                        try:
                            comm_service.send_text(session=payload.session, chat_id=chat_id, text=reply_text)
                        except Exception:
                            logger.exception(
                                "waha_send_failed",
                                extra={
                                    "chat_id": mask_waha_id(chat_id),
                                    "cellnumber": mask_phone(cellnumber),
                                },
                            )
                            return
                        redis_service.mark_processed(payload.id)

                        logger.info(
                            "webhook_processed",
                            extra={
                                "from_id": mask_waha_id(message_payload.from_id),
                                "chat_id": mask_waha_id(chat_id),
                                "cellnumber": mask_phone(cellnumber),
                                "response_language": response_language,
                                "used_faq": used_faq,
                                "persisted": should_persist,
                                "delivered": True,
                            },
                        )
                    except Exception:
                        logger.exception(
                            "audio_background_failed",
                            extra={
                                "chat_id": mask_waha_id(chat_id),
                                "cellnumber": mask_phone(cellnumber),
                                "payload_id": payload.id,
                            },
                        )
                    finally:
                        redis_service.release_processing(payload.id)
                        try:
                            os.remove(audio_path)
                        except OSError:
                            logger.warning("audio_temp_cleanup_failed", extra={"audio_path": audio_path})

                audio_queue.executor.submit(_background)
                return OutboundReply(reply=ack_text, used_faq=False, should_persist=False)
            finally:
                if not background_processing:
                    try:
                        os.remove(audio_path)
                    except OSError:
                        logger.warning("audio_temp_cleanup_failed", extra={"audio_path": audio_path})

        text = normalize_text(text)
        if not text:
            raise HTTPException(status_code=400, detail="empty message")

        lead, session_summary, _ = _resolve_lead(session_service, lead_service, chat_id, cellnumber)
        reply_text, used_faq, lead = _build_reply(
            text,
            lead,
            session_summary,
            response_language,
            lead_service,
            agent_service,
            settings,
        )
        should_persist = _update_session_and_persist(
            session_service=session_service,
            lead_service=lead_service,
            chat_id=chat_id,
            cellnumber=cellnumber,
            payload_id=payload.id,
            incoming_text=text,
            reply_text=reply_text,
            response_language=response_language,
            lead=lead,
            existing_summary=session_summary,
        )

        if audio_received and settings.audio_min_response_seconds > 0:
            elapsed = time.monotonic() - audio_start
            remaining = settings.audio_min_response_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)

        try:
            comm_service.send_text(session=payload.session, chat_id=chat_id, text=reply_text)
        except Exception:
            logger.exception(
                "waha_send_failed",
                extra={"chat_id": mask_waha_id(chat_id), "cellnumber": mask_phone(cellnumber)},
            )
            raise HTTPException(status_code=503, detail="failed to send reply")

        redis_service.mark_processed(payload.id)

        logger.info(
            "webhook_processed",
            extra={
                "from_id": mask_waha_id(message_payload.from_id),
                "chat_id": mask_waha_id(chat_id),
                "cellnumber": mask_phone(cellnumber),
                "response_language": response_language,
                "used_faq": used_faq,
                "persisted": should_persist,
                "delivered": True,
            },
        )

        return OutboundReply(
            reply=reply_text,
            used_faq=used_faq,
            should_persist=should_persist,
        )
    finally:
        if not background_processing:
            redis_service.release_processing(payload.id)


@router.post("/generic", response_model=OutboundReply)
def receive_generic_message(
    payload: GenericWebhookEvent,
    x_webhook_secret: str | None = Header(default=None),
    webhook_secret: str | None = Query(default=None),
    secret: str | None = Query(default=None),
    redis_service: RedisService = Depends(get_redis_service),
    lead_service: LeadService = Depends(get_lead_service),
    agent_service: AgentService = Depends(get_agent_service),
    audio_queue: AudioTranscriptionQueue = Depends(get_audio_queue),
    comm_service: CommunicationService = Depends(get_comm_service),
    session_service: SessionService = Depends(get_session_service),
) -> OutboundReply:
    message = payload.message
    media_url = (message.media.url if message.media else None) or message.media_url
    media_mimetype = (message.media.mimetype if message.media else None) or message.media_mimetype
    waha_payload = {
        "id": message.id,
        "timestamp": message.timestamp,
        "from": message.from_id,
        "fromMe": False,
        "source": "generic",
        "to": None,
        "participant": message.participant,
        "body": message.body,
        "hasMedia": message.has_media,
        "media": {
            "url": media_url,
            "mimetype": media_mimetype,
            "filename": message.media.filename if message.media else None,
        }
        if media_url or media_mimetype
        else None,
        "mediaUrl": media_url,
    }
    translated = WahaWebhookEvent(
        id=payload.id,
        timestamp=payload.timestamp,
        session=payload.session,
        event=payload.event,
        payload=waha_payload,
    )
    return receive_waha_message(
        translated,
        x_webhook_secret=x_webhook_secret,
        webhook_secret=webhook_secret,
        secret=secret,
        redis_service=redis_service,
        lead_service=lead_service,
        agent_service=agent_service,
        audio_queue=audio_queue,
        comm_service=comm_service,
        session_service=session_service,
    )
