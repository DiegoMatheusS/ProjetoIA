from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from ..enrichment.core import technical_missing_fields
from ..enrichment.quality import validate_specs
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    merge_meta_ai_response_into_payload_detailed,
)
from .evidence import collect_cited_sources
from .providers import TechnicalAIProviderError


def _max_rounds() -> int:
    try:
        value = int(os.getenv("TECH_RESEARCH_OPENAI_ROUNDS", "2"))
    except (TypeError, ValueError):
        value = 2
    return min(2, max(1, value))


def _repair_on_no_advance_enabled() -> bool:
    return os.getenv("TECH_RESEARCH_OPENAI_REPAIR_ON_NO_ADVANCE", "true").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


def _repair_prompt(base_prompt: str) -> str:
    """Reforca somente o formato quando a primeira resposta nao foi aproveitavel.

    A primeira chamada continua recebendo exatamente o mesmo prompt usado pelo fluxo
    manual do Meta AI. Esta variacao so pode aparecer na segunda e ultima rodada,
    dentro do mesmo limite de chamadas ja configurado pelo agente.
    """
    return (
        f"{base_prompt}\n\n"
        "ATENCAO DE FORMATO: a resposta anterior nao pode ser aproveitada pelo parser. "
        "Responda SOMENTE com uma linha por campo no formato exato Campo: valor. "
        "Nao use tabela, JSON, Markdown, bullets, cabecalho, explicacoes ou texto antes/depois. "
        "Use exatamente os nomes dos campos solicitados. Se um valor nao puder ser confirmado, escreva null."
    )


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _dedupe_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("url") or "").strip(),
            str(item.get("titulo") or item.get("title") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


@dataclass
class IterativeAIResult:
    payload: dict[str, Any]
    filled_fields: list[str]
    parsed_specs: dict[str, Any]
    conflicts: list[dict[str, Any]]
    rejected: list[Any]
    sources: list[dict[str, Any]]
    provenance: dict[str, dict[str, Any]]
    rounds: list[dict[str, Any]]
    first_prompt: str | None
    first_requested_fields: list[str]
    provider: str | None
    model: str | None
    provider_error: TechnicalAIProviderError | None


def run_iterative_external_research(
    *,
    provider,
    category: str,
    name: str | None,
    payload: dict[str, Any],
    local_info: dict[str, Any] | None = None,
) -> IterativeAIResult:
    """Executa no maximo duas rodadas externas usando o mesmo prompt do Meta AI.

    Fluxo normal: a primeira chamada recebe exatamente o prompt usado no Meta AI;
    se ela preencher campos e ainda houver lacunas, a segunda rodada pergunta apenas
    o restante. V10: se a primeira resposta vier com texto mas nenhum campo puder ser
    aproveitado pelo parser/validador, a segunda e ultima rodada pode repetir a mesma
    pergunta com uma instrucao de formato mais rigida. Isso recupera respostas em
    prosa/tabela/JSON sem aumentar o numero maximo de chamadas configurado.
    """
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise TechnicalAIProviderError(
            "PAYLOAD_INVALIDO",
            "Categoria sem ficha tecnica estruturada",
            status_code=400,
        )
    spec_field = schema[1]
    current = normalize_hardware_payload_for_backend(category, payload or {})
    identity = str(name or current.get("nome") or current.get("modelo") or "hardware").strip()

    all_filled: list[str] = []
    parsed_all: dict[str, Any] = {}
    conflicts_all: list[dict[str, Any]] = []
    rejected_all: list[Any] = []
    sources_all: list[dict[str, Any]] = []
    provenance: dict[str, dict[str, Any]] = {}
    rounds: list[dict[str, Any]] = []
    first_prompt: str | None = None
    first_requested: list[str] = []
    last_provider: str | None = None
    last_model: str | None = None
    provider_error: TechnicalAIProviderError | None = None
    repair_next_round = False
    max_rounds = _max_rounds()

    for round_number in range(1, max_rounds + 1):
        specs_before = current.get(spec_field) if isinstance(current.get(spec_field), dict) else {}
        state_before = {
            "categoriaDetectada": category,
            "especificacoesEncontradas": specs_before,
        }
        missing_before = technical_missing_fields(state_before)
        if not missing_before:
            break

        base_prompt = build_meta_ai_prompt(category, identity, missing_before)
        prompt_mode = "REPARO_FORMATO" if repair_next_round else "PADRAO_META_AI"
        prompt = _repair_prompt(base_prompt) if repair_next_round else base_prompt
        if first_prompt is None:
            # Mantem para diagnostico o prompt original, igual ao do Meta AI.
            first_prompt = base_prompt
            first_requested = list(missing_before)

        try:
            external = provider.enrich(prompt)
        except TechnicalAIProviderError as exc:
            provider_error = exc
            rounds.append(
                {
                    "numero": round_number,
                    "modo": prompt_mode,
                    "status": "ERRO_PROVEDOR",
                    "camposSolicitados": list(missing_before),
                    "codigoErro": exc.code,
                    "mensagemErro": exc.message,
                }
            )
            break

        last_provider = external.provider
        last_model = external.model
        round_sources = [item for item in (external.sources or []) if isinstance(item, dict)]
        sources_all.extend(round_sources)

        try:
            collect_cited_sources(category, current, round_sources, local_info or {})
        except Exception:
            # Citacoes sao proveniencia auxiliar; falha nessa etapa nao invalida
            # o parser/normalizador nem deve derrubar o Completar com IA.
            pass

        merged, filled, parsed_specs, conflicts = merge_meta_ai_response_into_payload_detailed(
            category,
            current,
            external.text,
        )
        merged = normalize_hardware_payload_for_backend(category, merged)
        normalized_specs, consistency_issues = validate_specs(
            category,
            merged.get(spec_field) or {},
        )
        merged[spec_field] = normalized_specs

        before_set = set(missing_before)
        valid_filled = [
            field
            for field in (filled or [])
            if field in before_set and not _missing(normalized_specs.get(field))
        ]
        valid_filled = list(dict.fromkeys(valid_filled))

        current = merged
        all_filled = list(dict.fromkeys(all_filled + valid_filled))
        if isinstance(parsed_specs, dict):
            parsed_all.update(parsed_specs)
        conflicts_all.extend([item for item in (conflicts or []) if isinstance(item, dict)])
        rejected_all.extend(consistency_issues or [])

        source_urls = [
            str(item.get("url") or "").strip()
            for item in round_sources
            if str(item.get("url") or "").strip()
        ][:20]
        for field in valid_filled:
            provenance[field] = {
                "fonte": "OPENAI_WEB_SEARCH" if source_urls else "OPENAI",
                "modelo": external.model,
                "urls": source_urls,
                "metodo": "IA_PARSER_SCHEMA_VALIDADO",
                "rodada": round_number,
            }

        state_after = {
            "categoriaDetectada": category,
            "especificacoesEncontradas": normalized_specs,
        }
        missing_after = technical_missing_fields(state_after)
        rounds.append(
            {
                "numero": round_number,
                "modo": prompt_mode,
                "status": "CONCLUIDA" if valid_filled else "SEM_AVANCO",
                "camposSolicitados": list(missing_before),
                "camposPreenchidos": list(valid_filled),
                "camposAusentesDepois": list(missing_after),
                "fontesRetornadas": len(round_sources),
                "modelo": external.model,
                "reparoDeFormato": prompt_mode == "REPARO_FORMATO",
            }
        )

        if not valid_filled:
            # A primeira resposta sem avanco pode ter vindo em prosa/tabela/JSON.
            # Usa a segunda chamada ja prevista pelo limite, sem criar uma terceira.
            if (
                round_number < max_rounds
                and not repair_next_round
                and _repair_on_no_advance_enabled()
            ):
                repair_next_round = True
                continue
            break

        repair_next_round = False
        if not missing_after:
            break

    return IterativeAIResult(
        payload=current,
        filled_fields=all_filled,
        parsed_specs=parsed_all,
        conflicts=conflicts_all,
        rejected=rejected_all,
        sources=_dedupe_sources(sources_all),
        provenance=provenance,
        rounds=rounds,
        first_prompt=first_prompt,
        first_requested_fields=first_requested,
        provider=last_provider,
        model=last_model,
        provider_error=provider_error,
    )
