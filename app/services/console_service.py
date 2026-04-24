import logging
from pathlib import Path

from app.services.communication import CommunicationService

logger = logging.getLogger("console_comm")


class ConsoleCommunicationService(CommunicationService):
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.seen: list[dict[str, str]] = []

    def send_seen(self, session: str, chat_id: str) -> None:
        self.seen.append({"session": session, "chat_id": chat_id})
        logger.info("console_send_seen", extra={"session": session, "chat_id": chat_id})

    def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
        payload = {"session": session, "chat_id": chat_id, "text": text, "reply_to": reply_to or ""}
        self.sent.append(payload)
        logger.info("console_send_text", extra=payload)

    def download_audio(self, audio_url: str) -> str:
        if not audio_url:
            raise RuntimeError("audio_url is empty")
        if audio_url.startswith("file://"):
            audio_url = audio_url.removeprefix("file://")
        path = Path(audio_url)
        if not path.exists():
            raise RuntimeError("audio file not found")
        return str(path)
