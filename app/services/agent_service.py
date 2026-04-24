import logging
from dataclasses import asdict
from typing import Any

from app.core.config import get_settings
from app.core.prompts import build_system_prompt
from app.models.lead import Lead


logger = logging.getLogger("agent_service")


class AgentService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_llm_enabled(self) -> bool:
        provider = self.settings.llm_provider.lower().strip()
        if provider == "gemini":
            return bool(self.settings.gemini_api_key)
        if provider in {"openai_like", "lmstudio"}:
            return bool(self.settings.openai_like_base_url and self.settings.openai_like_model)
        return False

    def _check_error_content(self, content: str, language: str, attempt: int) -> str | None:
        """Inspect content returned by Agno for embedded API error payloads.

        Returns:
            - A friendly reply string  when the error is terminal (429, auth, etc.)
            - None                     when the error is retryable (caller should retry)
            - The original content     when no error pattern is detected (valid reply)
        """
        # Agno embeds the raw API error JSON in the content string on failure.
        if '"error"' not in content and "RESOURCE_EXHAUSTED" not in content:
            return content  # Looks like a real reply — pass it through.

        # 429 / quota exceeded — no point retrying, return friendly message.
        if "429" in content or "RESOURCE_EXHAUSTED" in content:
            logger.warning(
                "llm_rate_limit",
                extra={"attempt": attempt + 1, "error": content[:300]},
            )
            return self._rate_limit_reply(language)

        # Other API errors (auth, invalid model, etc.) — log and signal retry.
        logger.warning(
            "llm_api_error_in_content",
            extra={"attempt": attempt + 1, "error": content[:300]},
        )
        return None  # Will be treated as retryable by the caller.

    def _rate_limit_reply(self, language: str) -> str:
        if language == "es":
            return (
                "En este momento estoy con mucha demanda 😊 "
                "Por favor, envíame un mensaje en unos minutos y te respondo enseguida."
            )
        return (
            "Estou com muita demanda agora 😊 "
            "Por favor, me manda uma mensagem em alguns minutos que te respondo na hora."
        )

    def _fallback_reply(self, language: str) -> str:
        if language == "es":
            return (
                "Puedo ayudarte mejor por aquí: "
                f"{self.settings.faq_url} \n"
                "Si prefieres, también puedo derivar tu atención a un especialista."
            )
        return (
            "Posso te ajudar melhor por aqui: "
            f"{self.settings.faq_url} \n"
            "Se preferir, também posso encaminhar seu atendimento para um especialista."
        )

    def generate_reply(
        self,
        incoming_text: str,
        known_lead: Lead | None = None,
        session_summary: str = "",
        language: str = "pt",
    ) -> dict[str, Any]:
        known_data = asdict(known_lead) if known_lead else {}
        system_prompt = build_system_prompt(
            self.settings.faq_url,
            known_data,
            session_summary,
            response_language=language,
        )

        provider = self.settings.llm_provider.lower().strip()
        if provider == "gemini" and not self.settings.gemini_api_key:
            logger.warning("llm_disabled_missing_api_key", extra={"provider": provider})
            return {
                "reply": (
                    "Consegue me dizer um pouco mais sobre o que você procura?"
                    if language == "pt"
                    else "¿Puedes contarme un poco más sobre lo que estás buscando?"
                ),
                "used_faq": False,
                "should_persist": False,
                "system_prompt_preview": system_prompt[:300],
            }
        if provider in {"openai_like", "lmstudio"} and (
            not self.settings.openai_like_base_url or not self.settings.openai_like_model
        ):
            logger.warning("llm_disabled_missing_config", extra={"provider": provider})
            return {
                "reply": (
                    "Consegue me dizer um pouco mais sobre o que você procura?"
                    if language == "pt"
                    else "¿Puedes contarme un poco más sobre lo que estás buscando?"
                ),
                "used_faq": False,
                "should_persist": False,
                "system_prompt_preview": system_prompt[:300],
            }

        lowered = incoming_text.lower()
        if "preço técnico" in lowered or "não sei" in lowered or "no sé" in lowered:
            logger.info("llm_fallback_keyword_rule", extra={"incoming_text": incoming_text[:120]})
            return {"reply": self._fallback_reply(language), "used_faq": True, "should_persist": False}

        reply_text = ""
        last_error: Exception | None = None
        max_attempts = self.settings.llm_max_retries + 1
        for attempt in range(max_attempts):
            try:
                from agno.agent import Agent

                if provider == "gemini":
                    from agno.models.google import Gemini

                    model = Gemini(id=self.settings.gemini_model, api_key=self.settings.gemini_api_key)
                elif provider in {"openai_like", "lmstudio"}:
                    from agno.models.openai.like import OpenAILike

                    api_key = self.settings.openai_like_api_key or "not-provided"
                    model = OpenAILike(
                        id=self.settings.openai_like_model,
                        base_url=self.settings.openai_like_base_url,
                        api_key=api_key,
                    )
                else:
                    raise RuntimeError(f"unsupported llm provider: {provider}")

                agent = Agent(model=model, instructions=[system_prompt])
                response = agent.run(incoming_text)
                reply_text = getattr(response, "content", "") or str(response)
                # Agno swallows API errors and returns them as plain content strings
                # instead of raising. Detect error payloads here before treating
                # the text as a valid reply.
                if reply_text:
                    reply_text = self._check_error_content(reply_text, language, attempt)
                    if reply_text is None:
                        # Retryable error — clear so the loop continues.
                        reply_text = ""
                        continue
                    # Non-empty string means either a clean reply or a final
                    # built-in message; either way, we are done.
                    break
            except Exception as exc:
                error_str = str(exc)
                # 429 RESOURCE_EXHAUSTED — quota esgotada; não adianta retrial.
                # Retorna mensagem amigável sem expor detalhes técnicos.
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logger.warning(
                        "llm_rate_limit",
                        extra={"attempt": attempt + 1, "error": error_str[:200]},
                    )
                    return {
                        "reply": self._rate_limit_reply(language),
                        "used_faq": False,
                        "should_persist": False,
                    }
                last_error = exc
                logger.warning(
                    "llm_generate_retry",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "error": error_str,
                    },
                )

        if not reply_text:
            if last_error is not None:
                logger.exception(
                    "llm_fallback_to_faq_due_error",
                    exc_info=last_error,
                    extra={
                        "max_attempts": max_attempts,
                        "incoming_text": incoming_text[:200],
                    },
                )
            else:
                logger.error(
                    "llm_fallback_to_faq_empty_response",
                    extra={
                        "max_attempts": max_attempts,
                        "incoming_text": incoming_text[:200],
                    },
                )
            return {
                "reply": self._fallback_reply(language),
                "used_faq": True,
                "should_persist": False,
                "error": str(last_error),
            }

        return {
            "reply": reply_text,
            "used_faq": False,
            "should_persist": False,
            "system_prompt_preview": system_prompt[:300],
        }
