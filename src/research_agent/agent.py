from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from ..enrichment.core import (
    TechnicalEnricher,
    technical_coverage,
    technical_missing_fields,
)
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .planner import ResearchPlan, build_research_plan
from .source_router import build_providers


def _enabled() -> bool:
    return os.getenv("TECH_RESEARCH_AGENT_ENABLED", "true").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


class TechnicalResearchAgent:
    """Orquestra pesquisa técnica antes do fallback externo de IA.

    V1 mantém o mesmo contrato já usado pelo serviço técnico: recebe um payload
    CriaByte, pesquisa somente o hardware selecionado, preenche lacunas com as
    fontes existentes e devolve o mesmo bloco de informações produzido pelo
    TechnicalEnricher. A OpenAI continua sendo chamada depois, pelo service.py,
    somente para as lacunas que restarem.
    """

    def __init__(self, *, enabled: bool | None = None):
        self.enabled = _enabled() if enabled is None else bool(enabled)

    @staticmethod
    def _base_result(category: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        safe = normalize_hardware_payload_for_backend(category, payload or {})
        schema = SCHEMAS.get(category)
        if not schema or not schema[1]:
            raise ValueError(f"Categoria sem ficha técnica estruturada: {category}")
        spec_field = schema[1]
        specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
        return {
            "categoriaDetectada": category,
            "nome": safe.get("nome"),
            "especificacoesEncontradas": deepcopy(specs),
            "payloadParcialBackend": deepcopy(safe),
        }, spec_field

    @staticmethod
    def _disabled_info(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "executado": False,
            "modo": "AGENTE_DESABILITADO",
            "motivoIgnorado": "TECH_RESEARCH_AGENT_ENABLED_FALSE",
            "camposPreenchidos": [],
            "fontesConsultadas": [],
            "origemPorCampo": {},
            "conflitos": [],
            "camposAusentesAntes": technical_missing_fields(result),
            "camposAusentesDepois": technical_missing_fields(result),
            "coberturaTecnicaAntes": round(technical_coverage(result), 4),
            "coberturaTecnicaDepois": round(technical_coverage(result), 4),
            "agentePesquisa": {
                "versao": 1,
                "ativo": False,
            },
        }

    def research(
        self,
        *,
        category: str,
        payload: dict[str, Any],
        name: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        category = str(category or "").strip().upper()
        base, spec_field = self._base_result(category, payload)
        safe_initial = dict(base["payloadParcialBackend"])
        if name and not safe_initial.get("nome"):
            safe_initial["nome"] = str(name).strip()
            base["nome"] = safe_initial["nome"]
            base["payloadParcialBackend"] = safe_initial

        plan: ResearchPlan = build_research_plan(category, base)
        if not self.enabled:
            return safe_initial, self._disabled_info(base)

        if not plan.missing_fields:
            info = self._disabled_info(base)
            info.update(
                {
                    "motivoIgnorado": "FICHA_SEM_LACUNAS",
                    "modo": "AGENTE_SEM_LACUNAS",
                    "agentePesquisa": {
                        "versao": 1,
                        "ativo": True,
                        "plano": plan.as_dict(),
                        "resultado": "SEM_LACUNAS",
                    },
                }
            )
            return safe_initial, info

        planned_sources = plan.sources[: plan.max_sources]
        providers = build_providers(planned_sources)
        enricher = TechnicalEnricher(
            providers=providers,
            auto_mode=True,
            total_timeout_override=plan.total_timeout_seconds,
            max_sources_override=max(1, len(providers)),
            source_timeout_override=plan.source_timeout_seconds,
            target_coverage_override=plan.target_coverage,
        )
        enriched = enricher.enrich(base)

        local_payload = enriched.get("payloadParcialBackend")
        if not isinstance(local_payload, dict):
            local_payload = dict(safe_initial)
            specs = enriched.get("especificacoesEncontradas")
            if isinstance(specs, dict):
                local_payload[spec_field] = specs

        safe_after = normalize_hardware_payload_for_backend(category, local_payload)
        info = enriched.get("enriquecimentoTecnico")
        if not isinstance(info, dict):
            info = {}
        else:
            info = deepcopy(info)

        result_state = {
            "categoriaDetectada": category,
            "especificacoesEncontradas": safe_after.get(spec_field) or {},
        }
        info["agentePesquisa"] = {
            "versao": 1,
            "ativo": True,
            "plano": plan.as_dict(),
            "coberturaDepois": round(technical_coverage(result_state), 4),
            "camposAusentesDepois": technical_missing_fields(result_state),
            "fontesExecutadas": [
                item.get("fonte")
                for item in info.get("fontesConsultadas") or []
                if isinstance(item, dict) and item.get("fonte")
            ],
            "resultado": "PESQUISA_CONCLUIDA",
        }
        return safe_after, info


def research_hardware_locally(
    category: str,
    payload: dict[str, Any],
    *,
    name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return TechnicalResearchAgent().research(
        category=category,
        payload=payload,
        name=name,
    )
