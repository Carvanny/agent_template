import re


def normalize_phone(value: str) -> str:
    """
    Normalize identifiers like "551199999999@c.us" or "+551199999999" to "+<digits>".
    Returns empty string when no digits are found.
    """
    if not value:
        return ""
    digits = re.sub(r"\D+", "", value.split("@", 1)[0])
    return f"+{digits}" if digits else ""
