from typing import Optional

from app.core.config import get_settings
from app.utils.text import normalize_text


class AudioService:
    _model: Optional[object] = None

    def __init__(self) -> None:
        self.settings = get_settings()

    def transcribe(self, audio_path: str) -> str:
        if self.settings.whisper_model == "mock":
            return normalize_text("transcrição mock")
        if not AudioService._model:
            from faster_whisper import WhisperModel

            AudioService._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        segments, _ = AudioService._model.transcribe(audio_path)
        transcript = " ".join(segment.text for segment in segments)
        return normalize_text(transcript)
