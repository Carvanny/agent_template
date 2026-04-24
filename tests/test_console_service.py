from pathlib import Path

from app.services.console_service import ConsoleCommunicationService


def test_console_send_text_and_seen() -> None:
    service = ConsoleCommunicationService()
    service.send_seen("default", "chat-1")
    service.send_text("default", "chat-1", "hello")
    assert service.seen == [{"session": "default", "chat_id": "chat-1"}]
    assert service.sent[0]["text"] == "hello"


def test_console_download_audio_file(tmp_path: Path) -> None:
    service = ConsoleCommunicationService()
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"fake")
    resolved = service.download_audio(f"file://{audio_path}")
    assert resolved == str(audio_path)
