from dataclasses import dataclass
from typing import Optional


@dataclass
class Lead:
    id: Optional[int]
    cellnumber: str
    name: Optional[str] = None
    mattress_size: Optional[str] = None
    need: Optional[str] = None
    budget_range: Optional[str] = None
    city: Optional[str] = None
    urgency: Optional[str] = None
    status: str = "open"
