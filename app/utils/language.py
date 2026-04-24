import re


def _parse_country_language_map(mapping: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for item in (mapping or "").split(","):
        token = item.strip()
        if not token or ":" not in token:
            continue
        prefix, lang = token.split(":", 1)
        prefix_digits = re.sub(r"\D+", "", prefix)
        language = lang.strip().lower()
        if not prefix_digits or language not in {"pt", "es"}:
            continue
        parsed.append((prefix_digits, language))

    # Longer prefixes first for more specific matching.
    return sorted(parsed, key=lambda pair: len(pair[0]), reverse=True)


def detect_language_from_phone(value: str, mapping: str = "55:pt,595:es") -> str:
    """
    Detect response language from phone country code (DDI).
    Defaults to Portuguese for unknown prefixes.
    """
    if not value:
        return "pt"

    digits = re.sub(r"\D+", "", value)

    for prefix, language in _parse_country_language_map(mapping):
        if digits.startswith(prefix):
            return language

    return "pt"
