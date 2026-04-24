from abc import ABC, abstractmethod


class CommunicationService(ABC):
    @abstractmethod
    def send_seen(self, session: str, chat_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def send_text(self, session: str, chat_id: str, text: str, reply_to: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def download_audio(self, audio_url: str) -> str:
        raise NotImplementedError

    def resolve_phone_identifier(self, session: str, raw_id: str) -> str | None:
        return raw_id
