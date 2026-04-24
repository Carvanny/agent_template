import re


def normalize_waha_phone_id(value: str) -> str:
    """
    WAHA commonly uses ids like "551199999999@c.us" or "551199999999@g.us".
    We normalize to "+<digits>" for internal storage.
    """
    if not value:
        return ""
    digits = re.sub(r"\D+", "", value.split("@", 1)[0])
    return f"+{digits}" if digits else ""


def is_waha_lid(value: str) -> bool:
    return bool(value) and value.endswith("@lid")
