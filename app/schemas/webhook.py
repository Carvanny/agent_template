from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WahaMedia(BaseModel):
    url: Optional[str] = None
    mimetype: Optional[str] = None
    filename: Optional[str] = None
    model_config = ConfigDict(extra="ignore")


class WahaMessagePayload(BaseModel):
    id: str
    timestamp: float
    from_id: str = Field(..., alias="from")
    fromMe: bool = False
    source: Optional[str] = None
    to: Optional[str] = None
    participant: Optional[str] = None
    body: Optional[str] = None
    hasMedia: bool = False
    media: Optional[WahaMedia] = None
    mediaUrl: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class WahaWebhookEvent(BaseModel):
    id: str
    timestamp: float
    session: str
    engine: Optional[str] = None
    event: str
    payload: Any = None
    model_config = ConfigDict(extra="ignore")


class OutboundReply(BaseModel):
    reply: str
    used_faq: bool = False
    should_persist: bool = False
