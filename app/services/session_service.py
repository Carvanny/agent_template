import time
from typing import Any, Optional

from app.core.config import get_settings
from app.services.redis_service import RedisService


class SessionService:
    def __init__(self, redis_service: RedisService) -> None:
        self.settings = get_settings()
        self.redis = redis_service

    def load(self, chat_id: str, cellnumber: str) -> Optional[dict[str, Any]]:
        session = self.redis.get_session(chat_id, cellnumber)
        if not session:
            return None
        last_interaction = session.get("last_interaction_at")
        if not last_interaction:
            self.redis.delete_session(chat_id, cellnumber)
            return None
        if time.time() - float(last_interaction) > self.settings.redis_ttl_seconds:
            self.redis.delete_session(chat_id, cellnumber)
            return None
        return session

    def build_summary(self, existing: str, user_text: str, assistant_text: str) -> str:
        lines = [line for line in existing.splitlines() if line.strip()]
        lines.extend([f"Cliente: {user_text}", f"Agente: {assistant_text}"])

        max_chars = self.settings.session_summary_max_chars
        while lines and len("\n".join(lines)) > max_chars:
            lines.pop(0)

        summary = "\n".join(lines)
        if len(summary) <= max_chars:
            return summary
        return summary[-max_chars:]

    def save(
        self,
        chat_id: str,
        cellnumber: str,
        session_payload: dict[str, Any],
    ) -> None:
        self.redis.save_session(chat_id, cellnumber, session_payload)
