import re


def mask_phone(value: str, show_last: int = 4) -> str:
    if not value:
        return value
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return value
    if len(digits) <= show_last:
        return "*" * len(digits)
    masked = "*" * (len(digits) - show_last) + digits[-show_last:]
    prefix = "+" if value.strip().startswith("+") else ""
    return f"{prefix}{masked}"


def mask_waha_id(value: str, show_last: int = 4) -> str:
    if not value:
        return value
    if "@" not in value:
        return mask_phone(value, show_last=show_last)
    head, tail = value.split("@", 1)
    return f"{mask_phone(head, show_last=show_last)}@{tail}"
