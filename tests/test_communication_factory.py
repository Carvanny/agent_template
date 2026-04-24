import pytest

from app.core.config import reset_settings_cache
from app.services.communication_factory import build_communication_service
from app.services.console_service import ConsoleCommunicationService
from app.services.http_comm_service import HttpCommunicationService
from app.services.waha_service import WahaService


def test_build_comm_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMMUNICATION_PROVIDER", "console")
    reset_settings_cache()
    service = build_communication_service()
    assert isinstance(service, ConsoleCommunicationService)


def test_build_comm_waha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMMUNICATION_PROVIDER", "waha")
    reset_settings_cache()
    service = build_communication_service()
    assert isinstance(service, WahaService)


def test_build_comm_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMMUNICATION_PROVIDER", "http")
    reset_settings_cache()
    service = build_communication_service()
    assert isinstance(service, HttpCommunicationService)
