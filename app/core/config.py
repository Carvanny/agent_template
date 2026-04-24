from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sales Assistant Agent"
    brand_name: str = "Sua Empresa"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_provider: str = "gemini"
    openai_like_base_url: str = ""
    openai_like_api_key: str = ""
    openai_like_model: str = ""
    country_language_map: str = "55:pt,595:es"

    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 86400
    redis_dedup_ttl_seconds: int = 300

    sqlite_db_path: str = "./assistant.db"

    waha_base_url: str = "http://localhost:3000"
    waha_api_key: str = ""
    waha_webhook_secret: str = ""
    allow_webhook_query_secret: bool = False
    allow_unauthenticated_webhook: bool = False
    communication_provider: str = "waha"

    comm_http_send_text_url: str = ""
    comm_http_send_seen_url: str = ""
    comm_http_headers: str = ""
    comm_http_timeout_seconds: int = 10
    comm_http_max_audio_bytes: int = 8_000_000
    waha_session_name: str = "default"
    waha_download_timeout_seconds: int = 20
    waha_max_audio_bytes: int = 8_000_000

    faq_url: str = "https://example.com/faq.html"

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    audio_queue_max_workers: int = 1
    audio_ack_timeout_seconds: float = 2.5
    audio_min_response_seconds: float = 1.2

    lead_finalization_min_fields: int = 5
    session_summary_max_chars: int = 1500
    llm_max_retries: int = 2
    httpx_timeout_seconds: int = 10
    httpx_max_retries: int = 2

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
