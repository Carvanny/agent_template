import tempfile
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.services.communication import CommunicationService


class HttpCommunicationService(CommunicationService):
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        raw = self.settings.comm_http_headers or ""
        headers: dict[str, str] = {}
        for token in raw.split(";"):
            token = token.strip()
            if not token or ":" not in token:
                continue
            name, value = token.split(":", 1)
            name = name.strip()
            value = value.strip()
            if name:
                headers[name] = value
        return headers

    def _post(self, url: str, payload: dict[str, object]) -> None:
        timeout = httpx.Timeout(self.settings.comm_http_timeout_seconds)
        last_error: Exception | None = None
        for _ in range(self.settings.httpx_max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, json=payload, headers=self._headers())
                if response.status_code not in {200, 201, 202, 204}:
                    raise RuntimeError(f"http comm failed with status {response.status_code}: {response.text}")
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError("http comm failed") from last_error

    def send_seen(self, session: str, chat_id: str) -> None:
        url = self.settings.comm_http_send_seen_url
        if not url:
            return
        payload: dict[str, object] = {"session": session, "chat_id": chat_id}
        self._post(url, payload)

    def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
        url = self.settings.comm_http_send_text_url
        if not url:
            raise RuntimeError("comm_http_send_text_url not configured")
        payload: dict[str, object] = {"session": session, "chat_id": chat_id, "text": text}
        if reply_to:
            payload["reply_to"] = reply_to
        self._post(url, payload)

    def download_audio(self, audio_url: str) -> str:
        if not audio_url:
            raise RuntimeError("audio_url is empty")
        timeout = httpx.Timeout(self.settings.comm_http_timeout_seconds)
        last_error: Exception | None = None
        for _ in range(self.settings.httpx_max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(audio_url, headers=self._headers())
                if response.status_code != 200:
                    raise RuntimeError(f"download failed with status {response.status_code}")
                if len(response.content) > self.settings.comm_http_max_audio_bytes:
                    raise RuntimeError("audio too large")
                suffix = Path(audio_url).suffix or ".ogg"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name
            except Exception as exc:
                last_error = exc
        raise RuntimeError("failed to download audio") from last_error
