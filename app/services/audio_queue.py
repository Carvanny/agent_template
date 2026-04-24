from concurrent.futures import Future, ThreadPoolExecutor

from app.services.audio_service import AudioService


class AudioTranscriptionQueue:
    def __init__(self, audio_service: AudioService, max_workers: int = 1) -> None:
        self.audio_service = audio_service
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="audio-transcription"
        )

    def transcribe(self, audio_path: str) -> str:
        future = self.executor.submit(self.audio_service.transcribe, audio_path)
        return future.result()

    def submit(self, audio_path: str) -> Future[str]:
        return self.executor.submit(self.audio_service.transcribe, audio_path)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
