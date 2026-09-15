from __future__ import annotations

from copy import deepcopy
import os
import time
from typing import Any

from ..enrichment.core import (
    TechnicalEnricher,
    technical_coverage,
    technical_missing_fields,
)
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .cache import ResearchCache, merge_cached_gaps
from .confidence import annotate_field_confidence
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


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _dedupe(values: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for value in values:
        marker = repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(value)
    return out


def _merge_round_info(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(first or {})
    other = second or {}
    for key in (
        "camposPreenchidos",
        "fontesConsultadas",
        "evidenciasColetadas",
        "problemasConsistencia",
        "conflitos",
        "pesquisasFocadas",
    ):
        out[key] = _dedupe(list(out.get(key) or []) + list(other.get(key) or []))
    origins = dict(out.get("origemPorCampo") or {})
    origins.update(other.get("origemPorCampo") or {})
    out["origemPorCampo"] = origins
    out["executado"] = bool(out.get("executado") or other.get("executado"))
    out["interrompidoPorTimeout"] = bool(
        out.get("interrompidoPorTimeout") or other.get("interrompidoPorTimeout")
    )
    out["interrompidoPorCobertura"] = bool(
        out.get("interrompidoPorCobertura") or other.get("interrompidoPorCobertura")
    )
    return out


class TechnicalResearchAgent:
    """Agente de pesquisa técnica para um único hardware selecionado.

    A V3 mantém cache, confiança e rodadas da V2 e passa a transformar as lacunas
    atuais em consultas de busca específicas. Ex.: se faltam BIOS Flashback,
    ethernet e slots M.2, as fontes recebem uma consulta direcionada a esses dados
    antes da busca genérica pelo modelo. A identidade do hardware continua sendo
    validada pelo coletor e a OpenAI continua depois apenas para o que restar.
    """

    def __init__(self, *, enabled: bool | None = None, cache: ResearchCache | None = None):
        self.enabled = _enabled() if enabled is None else bool(enabled)
        self.cache = cache or ResearchCache()

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
            "pesquisasFocadas": [],
            "camposAusentesAntes": technical_missing_fields(result),
            "camposAusentesDepois": technical_missing_fields(result),
            "coberturaTecnicaAntes": round(technical_coverage(result), 4),
            "coberturaTecnicaDepois": round(technical_coverage(result), 4),
            "agentePesquisa": {
                "versao": 3,
                "ativo": False,
            },
        }

    @staticmethod
    def _payload_from_enriched(
        category: str,
        spec_field: str,
        safe_fallback: dict[str, Any],
        enriched: dict[str, Any],
    ) -> dict[str, Any]:
        local_payload = enriched.get("payloadParcialBackend")
        if not isinstance(local_payload, dict):
            local_payload = dict(safe_fallback)
            specs = enriched.get("especificacoesEncontradas")
            if isinstance(specs, dict):
                local_payload[spec_field] = specs
        return normalize_hardware_payload_for_backend(category, local_payload)

    @staticmethod
    def _filled_between(spec_field: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        before_specs = before.get(spec_field) if isinstance(before.get(spec_field), dict) else {}
        after_specs = after.get(spec_field) if isinstance(after.get(spec_field), dict) else {}
        return [
            field
            for field, value in after_specs.items()
            if _missing(before_specs.get(field)) and not _missing(value)
        ]

    @staticmethod
    def _focused_search_diagnostics(providers, missing_fields: list[str]) -> list[dict[str, Any]]:
        diagnostics = []
        for provider in providers:
            resolver = getattr(provider, "resolver", None)
            focus_terms = list(getattr(resolver, "focus_terms", ()) or ())
            queries = list(getattr(resolver, "queries_executed", ()) or ())
            if not focus_terms and not queries:
                continue
            diagnostics.append(
                {
                    "fonte": getattr(provider, "name", provider.__class__.__name__),
                    "camposFoco": list(missing_fields),
                    "termosBusca": focus_terms,
                    "consultasExecutadas": queries,
                }
            )
        return diagnostics

    def _run_round(
        self,
        *,
        category: str,
        payload: dict[str, Any],
        spec_field: str,
        source_names: list[str],
        timeout_seconds: float,
        source_timeout_seconds: int,
        target_coverage: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        base, _ = self._base_result(category, payload)
        missing_for_round = technical_missing_fields(base)
        providers = build_providers(
            source_names,
            category=category,
            missing_fields=missing_for_round,
        )
        if not providers:
            return payload, {
                "executado": False,
                "camposPreenchidos": [],
                "fontesConsultadas": [],
                "origemPorCampo": {},
                "conflitos": [],
                "pesquisasFocadas": [],
            }
        enricher = TechnicalEnricher(
            providers=providers,
            auto_mode=True,
            total_timeout_override=timeout_seconds,
            max_sources_override=len(providers),
            source_timeout_override=source_timeout_seconds,
            target_coverage_override=target_coverage,
        )
        enriched = enricher.enrich(base)
        safe_after = self._payload_from_enriched(category, spec_field, payload, enriched)
        info = enriched.get("enriquecimentoTecnico")
        info = deepcopy(info) if isinstance(info, dict) else {}
        info["pesquisasFocadas"] = self._focused_search_diagnostics(
            providers,
            missing_for_round,
        )
        return safe_after, info

    def research(
        self,
        *,
        category: str,
        payload: dict[str, Any],
        name: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        category = str(category or "").strip().upper()
        base, spec_field = self._base_result(category, payload)
        safe_original = dict(base["payloadParcialBackend"])
        if name and not safe_original.get("nome"):
            safe_original["nome"] = str(name).strip()
            base["nome"] = safe_original["nome"]
            base["payloadParcialBackend"] = safe_original

        if not self.enabled:
            return safe_original, self._disabled_info(base)

        cache_hit = False
        cached_filled: list[str] = []
        cached_origins: dict[str, Any] = {}
        safe_seed = safe_original
        cached = self.cache.get(category, safe_original)
        if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
            candidate = merge_cached_gaps(category, safe_original, cached["payload"])
            cached_filled = self._filled_between(spec_field, safe_original, candidate)
            if cached_filled:
                cache_hit = True
                safe_seed = candidate
                all_cached_origins = cached.get("origemPorCampo") or {}
                cached_origins = {
                    field: all_cached_origins[field]
                    for field in cached_filled
                    if field in all_cached_origins
                }

        base, spec_field = self._base_result(category, safe_seed)
        plan: ResearchPlan = build_research_plan(category, base)

        if not plan.missing_fields:
            info = self._disabled_info(base)
            info.update(
                {
                    "executado": bool(cached_filled),
                    "motivoIgnorado": "FICHA_SEM_LACUNAS",
                    "modo": "AGENTE_CACHE_COMPLETO" if cache_hit else "AGENTE_SEM_LACUNAS",
                    "camposPreenchidos": cached_filled,
                    "origemPorCampo": cached_origins,
                    "agentePesquisa": {
                        "versao": 3,
                        "ativo": True,
                        "cacheHit": cache_hit,
                        "camposDoCache": cached_filled,
                        "plano": plan.as_dict(),
                        "rodadas": [],
                        "resultado": "SEM_LACUNAS",
                        "duracaoMs": int((time.monotonic() - started) * 1000),
                    },
                }
            )
            info = annotate_field_confidence(info)
            return safe_seed, info

        planned_sources = list(plan.sources[: plan.max_sources])
        primary_count = min(3, len(planned_sources))
        primary_sources = planned_sources[:primary_count]
        fallback_sources = planned_sources[primary_count:]
        first_budget = min(plan.total_timeout_seconds, max(5.0, plan.total_timeout_seconds * 0.65))

        safe_after, info = self._run_round(
            category=category,
            payload=safe_seed,
            spec_field=spec_field,
            source_names=primary_sources,
            timeout_seconds=first_budget,
            source_timeout_seconds=plan.source_timeout_seconds,
            target_coverage=plan.target_coverage,
        )
        first_state, _ = self._base_result(category, safe_after)
        rounds = [
            {
                "numero": 1,
                "tipo": "PRIORITARIA_FOCADA",
                "fontesPlanejadas": primary_sources,
                "camposFoco": list(plan.missing_fields),
                "coberturaDepois": round(technical_coverage(first_state), 4),
                "camposAusentesDepois": technical_missing_fields(first_state),
            }
        ]

        missing_after_first = technical_missing_fields(first_state)
        coverage_after_first = technical_coverage(first_state)
        elapsed = time.monotonic() - started
        remaining_budget = max(0.0, plan.total_timeout_seconds - elapsed)

        if (
            fallback_sources
            and missing_after_first
            and coverage_after_first < plan.target_coverage
            and remaining_budget >= 4.0
        ):
            second_payload, second_info = self._run_round(
                category=category,
                payload=safe_after,
                spec_field=spec_field,
                source_names=fallback_sources,
                timeout_seconds=remaining_budget,
                source_timeout_seconds=min(plan.source_timeout_seconds, max(2, int(remaining_budget))),
                target_coverage=plan.target_coverage,
            )
            info = _merge_round_info(info, second_info)
            safe_after = second_payload
            second_state, _ = self._base_result(category, safe_after)
            rounds.append(
                {
                    "numero": 2,
                    "tipo": "FALLBACK_FOCADO",
                    "fontesPlanejadas": fallback_sources,
                    "camposFoco": missing_after_first,
                    "coberturaDepois": round(technical_coverage(second_state), 4),
                    "camposAusentesDepois": technical_missing_fields(second_state),
                }
            )

        info = deepcopy(info or {})
        info["camposPreenchidos"] = _dedupe(cached_filled + list(info.get("camposPreenchidos") or []))
        origins = dict(cached_origins)
        origins.update(info.get("origemPorCampo") or {})
        info["origemPorCampo"] = origins

        result_state, _ = self._base_result(category, safe_after)
        focused_queries = sum(
            len(item.get("consultasExecutadas") or [])
            for item in info.get("pesquisasFocadas") or []
            if isinstance(item, dict)
        )
        info["agentePesquisa"] = {
            "versao": 3,
            "ativo": True,
            "cacheHit": cache_hit,
            "camposDoCache": cached_filled,
            "plano": plan.as_dict(),
            "rodadas": rounds,
            "consultasEspecificasExecutadas": focused_queries,
            "coberturaDepois": round(technical_coverage(result_state), 4),
            "camposAusentesDepois": technical_missing_fields(result_state),
            "fontesExecutadas": [
                item.get("fonte")
                for item in info.get("fontesConsultadas") or []
                if isinstance(item, dict) and item.get("fonte")
            ],
            "resultado": "PESQUISA_CONCLUIDA",
            "duracaoMs": int((time.monotonic() - started) * 1000),
        }
        info = annotate_field_confidence(info)
        self.cache.set(category, safe_after, info)
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
