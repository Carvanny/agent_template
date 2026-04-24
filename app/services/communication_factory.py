from app.core.config import get_settings
from app.services.communication import CommunicationService
from app.services.console_service import ConsoleCommunicationService
from app.services.http_comm_service import HttpCommunicationService
from app.services.waha_service import WahaService


def build_communication_service() -> CommunicationService:
    settings = get_settings()
    provider = settings.communication_provider.lower().strip()
    if provider == "waha":
        return WahaService()
    if provider == "console":
        return ConsoleCommunicationService()
    if provider == "http":
        return HttpCommunicationService()
    raise ValueError(f"unsupported communication provider: {provider}")
