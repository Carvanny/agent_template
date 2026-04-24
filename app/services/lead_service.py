import re
from dataclasses import asdict
from typing import Iterable

from app.core.config import get_settings
from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.utils.text import normalize_text


class LeadService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.repository = LeadRepository()

    def get_known_lead(self, cellnumber: str) -> Lead | None:
        return self.repository.get_by_cellnumber(cellnumber)

    def persist_if_complete(self, lead: Lead, completed: bool) -> bool:
        if not completed:
            return False
        self.repository.upsert(lead)
        return True

    def count_filled_fields(self, lead: Lead) -> int:
        data = asdict(lead)
        relevant = [data.get("name"), data.get("mattress_size"), data.get("need"), data.get("budget_range"), data.get("city"), data.get("urgency")]
        return sum(1 for item in relevant if item)

    def is_complete(self, lead: Lead) -> bool:
        return self.count_filled_fields(lead) >= self.settings.lead_finalization_min_fields

    def next_question(self, lead: Lead, language: str = "pt") -> str | None:
        if language == "es":
            questions = {
                "name": "Para comenzar, ¿cuál es tu nombre?",
                "mattress_size": "¿Qué tamaño de colchón buscas: individual, matrimonial, queen o king?",
                "need": "¿Cuál es tu necesidad principal o preferencia: más firme, más suave, dolor de espalda?",
                "budget_range": "¿Tienes un rango de presupuesto en mente?",
                "city": "¿En qué ciudad estás?",
                "urgency": "¿Cuál es el plazo para la compra?",
            }
        else:
            questions = {
                "name": "Para começar, qual é o seu nome?",
                "mattress_size": "Qual tamanho de colchão você procura: solteiro, casal, queen ou king?",
                "need": "Qual a principal necessidade ou preferência: mais firme, mais macio, dor nas costas?",
                "budget_range": "Tem uma faixa de orçamento em mente?",
                "city": "Em qual cidade você está?",
                "urgency": "Qual o prazo para compra?",
            }
        for field in ["name", "mattress_size", "need", "budget_range", "city", "urgency"]:
            if not getattr(lead, field):
                return questions[field]
        return None

    def extract_updates(self, text: str) -> dict[str, str]:
        normalized = normalize_text(text)
        lowered = normalized.lower()
        updates: dict[str, str] = {}

        name_match = re.search(r"\bmeu nome (?:é|e|eh)\s+([A-Za-zÀ-ÿ ]{2,})", normalized, re.I)
        if name_match:
            updates["name"] = name_match.group(1).strip().title()
        else:
            sou_match = re.search(r"\bsou\s+([A-Za-zÀ-ÿ ]{2,})", normalized, re.I)
            if sou_match:
                sou_candidate = sou_match.group(1).strip()
                if not sou_candidate.lower().startswith("de "):
                    updates["name"] = sou_candidate.title()

        if any(word in lowered for word in ["solteiro", "casal", "queen", "king"]):
            for size in ["solteiro", "casal", "queen", "king"]:
                if size in lowered:
                    updates["mattress_size"] = size
                    break

        if any(word in lowered for word in ["dor", "coluna", "postura", "alerg", "firme", "macio", "ortop"]):
            updates["need"] = normalized

        budget_match = re.search(r"(r\$)\s*([\d\.\,]+)", lowered)
        if budget_match:
            updates["budget_range"] = f"R$ {budget_match.group(2)}"
        else:
            range_match = re.search(r"\bat[eé]\s+([\d\.\,]+)", lowered)
            if range_match:
                updates["budget_range"] = f"até {range_match.group(1)}"

        city_patterns = [
            r"\bmoro em\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)\b",
            r"\bsou de\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)\b",
            r"\bcidade\s*(?::|é|eh)?\s*([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)\b",
        ]
        city_stopwords = {
            "quanto",
            "qual",
            "que",
            "geral",
            "agora",
            "hoje",
            "amanha",
            "amanhã",
            "urgente",
        }
        for pattern in city_patterns:
            city_match = re.search(pattern, normalized, re.I)
            if not city_match:
                continue
            city = city_match.group(1).strip()
            if city.lower() in city_stopwords:
                continue
            updates["city"] = city.title()
            break

        if any(word in lowered for word in ["hoje", "amanhã", "urgente", "semana", "mês", "mes"]):
            updates["urgency"] = normalized

        return updates

    def apply_updates(self, lead: Lead, updates: dict[str, str], allow_override: bool) -> tuple[Lead, list[str]]:
        changed_fields: list[str] = []
        for key, value in updates.items():
            current = getattr(lead, key)
            if current and not allow_override:
                continue
            if value and value != current:
                setattr(lead, key, value)
                changed_fields.append(key)
        return lead, changed_fields

    def should_allow_override(self, text: str) -> bool:
        lowered = normalize_text(text).lower()
        triggers = ["mudar", "trocar", "corrigir", "atualizar", "na verdade", "prefiro", "ajustar"]
        return any(trigger in lowered for trigger in triggers)

    def build_rule_based_reply(
        self,
        lead: Lead,
        updated_fields: Iterable[str],
        language: str = "pt",
    ) -> str:
        prefix = ""
        if updated_fields:
            if language == "es":
                labels = {
                    "name": "nombre",
                    "mattress_size": "tamaño del colchón",
                    "need": "necesidad",
                    "budget_range": "presupuesto",
                    "city": "ciudad",
                    "urgency": "plazo",
                }
                prefix_template = "Actualicé {fields}. "
            else:
                labels = {
                    "name": "nome",
                    "mattress_size": "tamanho do colchão",
                    "need": "necessidade",
                    "budget_range": "orçamento",
                    "city": "cidade",
                    "urgency": "prazo",
                }
                prefix_template = "Atualizei {fields}. "
            fields = ", ".join(labels.get(field, field) for field in updated_fields)
            prefix = prefix_template.format(fields=fields)
        next_question = self.next_question(lead, language=language)
        if next_question:
            return f"{prefix}{next_question}".strip()
        if language == "es":
            return f"{prefix}Perfecto, ya tengo lo necesario. ¿Puedo derivarte con un especialista?"
        return f"{prefix}Perfeito, já tenho o necessário. Posso encaminhar para um especialista?"
