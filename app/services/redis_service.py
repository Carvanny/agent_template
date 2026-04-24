import json
from typing import Any, Optional
from redis import Redis
from app.core.config import get_settings


class RedisService:
    def __init__(self, client: Optional[Redis] = None) -> None:
        self.settings = get_settings()
        self.client = client or Redis.from_url(self.settings.redis_url, decode_responses=True)

    def dedup_key(self, message_id: str) -> str:
        return f"dedup:{message_id}"

    def processing_key(self, message_id: str) -> str:
        return f"processing:{message_id}"

    def session_key(self, chat_id: str, cellnumber: str) -> str:
        return f"session:{chat_id}:{cellnumber}"

    def is_duplicate(self, message_id: str) -> bool:
        return self.client.exists(self.dedup_key(message_id)) == 1

    def is_processed(self, message_id: str) -> bool:
        return self.is_duplicate(message_id)

    def acquire_processing(self, message_id: str) -> bool:
        lock_ttl = max(self.settings.redis_dedup_ttl_seconds, 30)
        acquired = self.client.set(
            self.processing_key(message_id),
            "1",
            ex=lock_ttl,
            nx=True,
        )
        return bool(acquired)

    def release_processing(self, message_id: str) -> None:
        self.client.delete(self.processing_key(message_id))

    def mark_processed(self, message_id: str) -> None:
        self.client.setex(self.dedup_key(message_id), self.settings.redis_dedup_ttl_seconds, "1")

    def get_session(self, chat_id: str, cellnumber: str) -> Optional[dict[str, Any]]:
        raw = self.client.get(self.session_key(chat_id, cellnumber))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def save_session(self, chat_id: str, cellnumber: str, payload: dict[str, Any]) -> None:
        self.client.setex(
            self.session_key(chat_id, cellnumber),
            self.settings.redis_ttl_seconds,
            json.dumps(payload, ensure_ascii=False),
        )

    def delete_session(self, chat_id: str, cellnumber: str) -> None:
        self.client.delete(self.session_key(chat_id, cellnumber))

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
