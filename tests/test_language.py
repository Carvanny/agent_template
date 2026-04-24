from app.utils.language import detect_language_from_phone


def test_detect_language_default_mapping() -> None:
    assert detect_language_from_phone("551199999999@c.us") == "pt"
    assert detect_language_from_phone("59599999999@c.us") == "es"


def test_detect_language_custom_mapping() -> None:
    mapping = "1:en,55:pt,595:es"

    # Unsupported language codes are ignored; fallback remains pt.
    assert detect_language_from_phone("14155552671@c.us", mapping=mapping) == "pt"
    assert detect_language_from_phone("551199999999@c.us", mapping=mapping) == "pt"
    assert detect_language_from_phone("59599999999@c.us", mapping=mapping) == "es"
