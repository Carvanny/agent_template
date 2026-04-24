import tempfile
import time
from urllib.parse import quote
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.services.communication import CommunicationService
from app.utils.waha import is_waha_lid


class WahaService(CommunicationService):
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.waha_api_key:
            return {}
        return {"X-Api-Key": self.settings.waha_api_key}

    def _normalize_url(self, url: str) -> str:
        if not url:
            return url
        if url.startswith("/"):
            return f"{self.settings.waha_base_url.rstrip('/')}{url}"
        if url.startswith("http://localhost:3000"):
            base = self.settings.waha_base_url.rstrip("/")
            return f"{base}{url.removeprefix('http://localhost:3000')}"
        return url

    def download_audio(self, audio_url: str) -> str:
        timeout = httpx.Timeout(self.settings.waha_download_timeout_seconds)
        normalized_url = self._normalize_url(audio_url)
        last_error: Exception | None = None
        for _ in range(self.settings.httpx_max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(normalized_url, headers=self._headers())
                if response.status_code != 200:
                    raise RuntimeError(f"download failed with status {response.status_code}")
                if len(response.content) > self.settings.waha_max_audio_bytes:
                    raise RuntimeError("audio too large")
                suffix = Path(normalized_url).suffix or ".ogg"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name
            except Exception as exc:
                last_error = exc
        raise RuntimeError("failed to download audio") from last_error

    def send_seen(self, session: str, chat_id: str) -> None:
        timeout = httpx.Timeout(self.settings.httpx_timeout_seconds)
        session_name = session or self.settings.waha_session_name
        payload: dict[str, object] = {"chatId": chat_id, "session": session_name}
        self._post_with_session_recovery(
            endpoint="/api/sendSeen",
            payload=payload,
            timeout=timeout,
            session_name=session_name,
            action_name="sendSeen",
        )

    def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
        timeout = httpx.Timeout(self.settings.httpx_timeout_seconds)
        session_name = session or self.settings.waha_session_name
        payload: dict[str, object] = {"chatId": chat_id, "text": text, "session": session_name}
        if reply_to:
            payload["reply_to"] = reply_to
        self._post_with_session_recovery(
            endpoint="/api/sendText",
            payload=payload,
            timeout=timeout,
            session_name=session_name,
            action_name="sendText",
        )

    def get_phone_by_lid(self, session: str, lid: str) -> str | None:
        timeout = httpx.Timeout(self.settings.httpx_timeout_seconds)
        session_name = session or self.settings.waha_session_name
        encoded_lid = quote(lid, safe="")
        url = f"{self.settings.waha_base_url.rstrip('/')}/api/{session_name}/lids/{encoded_lid}"
        last_error: Exception | None = None
        for _ in range(self.settings.httpx_max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(url, headers=self._headers())
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise RuntimeError(f"get lid failed with status {response.status_code}: {response.text}")
                data = response.json()
                pn = data.get("pn")
                return pn or None
            except Exception as exc:
                last_error = exc
        if last_error:
            raise RuntimeError("failed to resolve lid") from last_error
        return None

    def resolve_phone_identifier(self, session: str, raw_id: str) -> str | None:
        if not raw_id:
            return None
        if is_waha_lid(raw_id):
            try:
                resolved = self.get_phone_by_lid(session, raw_id)
            except Exception:
                return None
            return resolved or None
        return raw_id

    def _post_with_session_recovery(
        self,
        endpoint: str,
        payload: dict[str, object],
        timeout: httpx.Timeout,
        session_name: str,
        action_name: str,
    ) -> None:
        url = f"{self.settings.waha_base_url.rstrip('/')}{endpoint}"
        last_error: Exception | None = None
        session_start_attempted = False
        for _ in range(self.settings.httpx_max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, json=payload, headers=self._headers())
                if response.status_code not in {200, 201}:
                    response_body = response.text.strip()
                    if (
                        response.status_code == 422
                        and "Session status is not as expected" in response_body
                        and not session_start_attempted
                    ):
                        session_start_attempted = True
                        self._start_session(session_name, timeout)
                        time.sleep(1)
                        continue
                    raise RuntimeError(
                        f"{action_name} failed with status {response.status_code}: {response_body}"
                    )
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"failed to {action_name}") from last_error

    def _start_session(self, session: str, timeout: httpx.Timeout) -> None:
        url = f"{self.settings.waha_base_url.rstrip('/')}/api/sessions/{session}/start"
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json={}, headers=self._headers())
        if response.status_code not in {200, 201, 409}:
            raise RuntimeError(f"failed to start WAHA session '{session}': {response.status_code}: {response.text}")
