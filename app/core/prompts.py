from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
BASE_DIR = Path(__file__).resolve().parents[2]
MEMORY_DIR = BASE_DIR / "memory"


@lru_cache(maxsize=16)
def load_memory_file(filename: str) -> str:
    path = MEMORY_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


def warm_prompt_cache() -> None:
    for filename in (
        "agent_profile.md",
        "agent_guidelines.md",
        "questionario.md",
        "agent_aprendizado.md",
    ):
        load_memory_file(filename)


def build_system_prompt(
    faq_url: str,
    known_data: dict[str, str],
    session_summary: str = "",
    response_language: str = "pt",
) -> str:
    placeholders = {
        "{FAQ_URL}": faq_url,
        "{BRAND_NAME}": get_settings().brand_name,
    }

    def apply_placeholders(content: str) -> str:
        for key, value in placeholders.items():
            content = content.replace(key, value)
        return content

    profile = apply_placeholders(load_memory_file("agent_profile.md"))
    guidelines = apply_placeholders(load_memory_file("agent_guidelines.md"))
    questionnaire = apply_placeholders(load_memory_file("questionario.md"))
    learning = apply_placeholders(load_memory_file("agent_aprendizado.md"))

    known_lines = "\n".join(f"- {k}: {v}" for k, v in known_data.items() if v)
    known_block = f"\n## Dados já conhecidos do lead\n{known_lines}\n" if known_lines else ""
    summary_block = f"\n## Resumo da conversa\n{session_summary}\n" if session_summary else ""
    language_block = (
        "## Idioma da resposta\n"
        + ("Responda sempre em português do Brasil." if response_language == "pt" else "Responda sempre em espanhol.")
    )

    return "\n\n".join(
        [profile, guidelines, questionnaire, learning, known_block, summary_block, language_block]
    ).strip()
