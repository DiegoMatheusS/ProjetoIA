from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

from ..enrichment.core import (
    required_missing_fields,
    technical_coverage,
    technical_missing_fields,
)
from ..enrichment.identity import build_identity
from ..enrichment.quality import validate_specs
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    merge_meta_ai_response_into_payload_detailed,
)
from .cost_guard import ExternalAIResponseCache
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


def _record_official_evidence_conflicts_enabled() -> bool:
    return os.getenv("TECH_RESEARCH_RECORD_OFFICIAL_EVIDENCE_CONFLICTS", "true").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


def _skip_external_coverage() -> float:
    """Cobertura local a partir da qual opcionais nao justificam uma chamada paga."""
    try:
        value = float(os.getenv("TECH_RESEARCH_OPENAI_SKIP_COVERAGE", "0.88"))
    except (TypeError, ValueError):
        value = 0.88
    return min(0.99, max(0.75, value))


def _total_budget_seconds() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_OPENAI_TOTAL_BUDGET_SECONDS", "50"))
    except (TypeError, ValueError):
        value = 50.0
    return min(75.0, max(10.0, value))


def _max_round_budget_seconds() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_OPENAI_MAX_ROUND_SECONDS", "28"))
    except (TypeError, ValueError):
        value = 28.0
    return min(45.0, max(5.0, value))


def _budget_error() -> TechnicalAIProviderError:
    return TechnicalAIProviderError(
        "ORCAMENTO_TEMPO_ESGOTADO",
        "Orçamento de tempo da pesquisa OpenAI esgotado antes da próxima rodada",
        status_code=504,
        transient=True,
    )


def _repair_prompt(base_prompt: str) -> str:
    """Reforca somente o formato quando a primeira resposta nao foi aproveitavel."""
    return (
        f"{base_prompt}\n\n"
        "ATENCAO DE FORMATO: a resposta anterior nao pode ser aproveitada pelo parser. "
        "Responda SOMENTE com uma linha por campo no formato exato Campo: valor. "
        "Nao use tabela, JSON, Markdown, bullets, cabecalho, explicacoes ou texto antes/depois. "
        "Use exatamente os nomes dos campos solicitados. Se um valor nao puder ser confirmado, escreva null."
    )


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _comparison_key(value: Any) -> Any:
    """Normaliza apenas para comparar IA x evidência oficial; não altera o payload."""
    if isinstance(value, str):
        return ("str", " ".join(value.split()).casefold())
    if isinstance(value, list):
        return ("list", tuple(sorted((_comparison_key(item) for item in value), key=repr)))
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                sorted(
                    ((str(key), _comparison_key(item)) for key, item in value.items()),
                    key=lambda pair: pair[0],
                )
            ),
        )
    return ("scalar", value)


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


def _call_provider_with_budget(
    provider,
    prompt: str,
    budget_seconds: float,
    *,
    cache_identity: str | None = None,
):
    # A resposta paga e cacheada por identidade forte + prompt exato. Se o cadastro
    # falhar depois e o mesmo hardware for reenviado, nao ha nova cobranca.
    response_cache = None
    try:
        response_cache = ExternalAIResponseCache()
        cached = response_cache.get(
            provider,
            prompt,
            identity_key=cache_identity,
        )
        if cached is not None:
            return cached
    except Exception:
        response_cache = None

    enrich_with_budget = getattr(provider, "enrich_with_budget", None)
    if callable(enrich_with_budget):
        response = enrich_with_budget(prompt, budget_seconds=budget_seconds)
    else:
        response = provider.enrich(prompt)

    if response_cache is not None:
        try:
            response_cache.set(
                provider,
                prompt,
                response,
                identity_key=cache_identity,
            )
        except Exception:
            pass
    return response


def _verified_provenance(
    *,
    field: str,
    value: Any,
    verified_evidence: dict[str, Any],
    external,
    source_urls: list[str],
    round_number: int,
) -> dict[str, Any]:
    evidence = verified_evidence.get(field)
    if (
        isinstance(evidence, dict)
        and not _missing(evidence.get("valor"))
        and _comparison_key(evidence.get("valor")) == _comparison_key(value)
    ):
        return {
            "fonte": str(evidence.get("fonte") or "FABRICANTE_OFICIAL").strip().upper(),
            "url": evidence.get("url"),
            "trecho": evidence.get("trecho"),
            "valor": value,
            "modelo": external.model,
            "urls": source_urls,
            "metodo": "OPENAI_COM_CITACAO_OFICIAL_REVALIDADA",
            "rodada": round_number,
            "evidenciaCampoConfirmada": True,
        }

    return {
        "fonte": "OPENAI_WEB_SEARCH" if source_urls else "OPENAI",
        "modelo": external.model,
        "urls": source_urls,
        "metodo": "IA_PARSER_SCHEMA_VALIDADO",
        "rodada": round_number,
        "evidenciaCampoConfirmada": False,
    }


def _official_evidence_conflict(
    *,
    field: str,
    current_value: Any,
    evidence: Any,
    round_number: int,
) -> dict[str, Any] | None:
    if not _record_official_evidence_conflicts_enabled() or not isinstance(evidence, dict):
        return None
    official_value = evidence.get("valor")
    if _missing(current_value) or _missing(official_value):
        return None
    if _comparison_key(current_value) == _comparison_key(official_value):
        return None
    return {
        "campo": field,
        "valorAtual": current_value,
        "valorExterno": official_value,
        "fonte": str(evidence.get("fonte") or "FABRICANTE_OFICIAL").strip().upper(),
        "url": evidence.get("url"),
        "trecho": evidence.get("trecho"),
        "rodada": round_number,
        "metodo": "CITACAO_OFICIAL_DIVERGIU_DA_RESPOSTA_OPENAI",
        "requerRevisao": True,
    }


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
    """Pesquisa externa com protecao de custo.

    Regra normal: no maximo uma chamada OpenAI. Uma segunda rodada so acontece
    quando, depois da primeira, ainda existe campo OBRIGATORIO ausente. Se a pesquisa
    local ja atingiu o limiar de cobertura e todos os obrigatorios estao presentes,
    a OpenAI e ignorada. Respostas OpenAI bem-sucedidas sao cacheadas pela identidade
    forte + prompt para que uma falha posterior no cadastro nao gere nova cobranca.
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
    identity_info = build_identity(
        {
            "categoriaDetectada": category,
            "payloadParcialBackend": current,
        }
    )
    identity_key = str(identity_info.get("chave") or "").strip()
    cache_identity = f"{category}|{identity_key}" if identity_key else None

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
    total_budget = _total_budget_seconds()
    round_ceiling = _max_round_budget_seconds()
    external_started = time.monotonic()
    local_info = local_info if isinstance(local_info, dict) else {}

    initial_specs = current.get(spec_field) if isinstance(current.get(spec_field), dict) else {}
    initial_state = {
        "categoriaDetectada": category,
        "especificacoesEncontradas": initial_specs,
    }
    initial_missing = technical_missing_fields(initial_state)
    initial_required = required_missing_fields(initial_state)
    initial_coverage = technical_coverage(initial_state)
    local_filled = list(local_info.get("camposPreenchidos") or [])
    skip_threshold = _skip_external_coverage()

    if (
        initial_missing
        and local_filled
        and not initial_required
        and initial_coverage >= skip_threshold
    ):
        return IterativeAIResult(
            payload=current,
            filled_fields=[],
            parsed_specs={},
            conflicts=[],
            rejected=[],
            sources=[],
            provenance={},
            rounds=[
                {
                    "numero": 0,
                    "modo": "ECONOMIA_CUSTO",
                    "status": "OPENAI_IGNORADA_COBERTURA_LOCAL",
                    "chamadaExecutada": False,
                    "coberturaLocal": round(initial_coverage, 4),
                    "limiarCobertura": round(skip_threshold, 4),
                    "camposAusentes": list(initial_missing),
                    "camposObrigatoriosAusentes": [],
                }
            ],
            first_prompt=None,
            first_requested_fields=[],
            provider="PROJETO_IA",
            model=None,
            provider_error=None,
        )

    for round_number in range(1, max_rounds + 1):
        specs_before = current.get(spec_field) if isinstance(current.get(spec_field), dict) else {}
        state_before = {
            "categoriaDetectada": category,
            "especificacoesEncontradas": specs_before,
        }
        all_missing_before = technical_missing_fields(state_before)
        required_before = required_missing_fields(state_before)
        if not all_missing_before:
            break

        # Primeira rodada pode tentar todas as lacunas. Uma eventual segunda rodada
        # pergunta SOMENTE pelos obrigatorios restantes, reduzindo tokens e custo.
        if round_number > 1:
            if not required_before:
                break
            required_set = set(required_before)
            missing_before = [field for field in all_missing_before if field in required_set]
        else:
            missing_before = list(all_missing_before)

        elapsed_before = time.monotonic() - external_started
        remaining_total = max(0.0, total_budget - elapsed_before)
        if remaining_total < 3.0:
            provider_error = _budget_error()
            rounds.append(
                {
                    "numero": round_number,
                    "modo": "REPARO_FORMATO" if repair_next_round else "PADRAO_META_AI",
                    "status": "ORCAMENTO_TEMPO_ESGOTADO",
                    "camposSolicitados": list(missing_before),
                    "codigoErro": provider_error.code,
                    "mensagemErro": provider_error.message,
                    "orcamentoTotalSegundos": round(total_budget, 2),
                    "tempoRestanteAntesSegundos": round(remaining_total, 2),
                }
            )
            break

        round_budget = min(round_ceiling, remaining_total)
        base_prompt = build_meta_ai_prompt(category, identity, missing_before)
        prompt_mode = "REPARO_FORMATO" if repair_next_round else "PADRAO_META_AI"
        prompt = _repair_prompt(base_prompt) if repair_next_round else base_prompt
        if first_prompt is None:
            first_prompt = base_prompt
            first_requested = list(missing_before)

        round_started = time.monotonic()
        try:
            external = _call_provider_with_budget(
                provider,
                prompt,
                round_budget,
                cache_identity=cache_identity,
            )
        except TechnicalAIProviderError as exc:
            provider_error = exc
            elapsed_round = time.monotonic() - round_started
            remaining_after_error = max(0.0, total_budget - (time.monotonic() - external_started))
            rounds.append(
                {
                    "numero": round_number,
                    "modo": prompt_mode,
                    "status": "ERRO_PROVEDOR",
                    "camposSolicitados": list(missing_before),
                    "codigoErro": exc.code,
                    "mensagemErro": exc.message,
                    "orcamentoRodadaSegundos": round(round_budget, 2),
                    "duracaoRodadaMs": int(elapsed_round * 1000),
                    "tempoRestanteDepoisSegundos": round(remaining_after_error, 2),
                }
            )
            break

        elapsed_round = time.monotonic() - round_started
        remaining_after_call = max(0.0, total_budget - (time.monotonic() - external_started))
        last_provider = external.provider
        last_model = external.model
        metadata = external.raw_metadata if isinstance(external.raw_metadata, dict) else {}
        cache_hit_openai = bool(metadata.get("cacheHit"))
        round_sources = [item for item in (external.sources or []) if isinstance(item, dict)]
        sources_all.extend(round_sources)

        verified_evidence: dict[str, Any] = {}
        try:
            verified_evidence = collect_cited_sources(
                category,
                current,
                round_sources,
                local_info,
            ) or {}
        except Exception:
            verified_evidence = {}

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
        fields_with_verified_evidence: list[str] = []
        fields_with_official_conflict: list[str] = []
        for field in valid_filled:
            current_value = normalized_specs.get(field)
            evidence = verified_evidence.get(field)
            official_conflict = _official_evidence_conflict(
                field=field,
                current_value=current_value,
                evidence=evidence,
                round_number=round_number,
            )
            if official_conflict is not None:
                conflicts_all.append(official_conflict)
                fields_with_official_conflict.append(field)

            provenance[field] = _verified_provenance(
                field=field,
                value=current_value,
                verified_evidence=verified_evidence,
                external=external,
                source_urls=source_urls,
                round_number=round_number,
            )
            if provenance[field].get("evidenciaCampoConfirmada"):
                fields_with_verified_evidence.append(field)

        state_after = {
            "categoriaDetectada": category,
            "especificacoesEncontradas": normalized_specs,
        }
        missing_after = technical_missing_fields(state_after)
        required_after = required_missing_fields(state_after)
        rounds.append(
            {
                "numero": round_number,
                "modo": prompt_mode,
                "status": "CONCLUIDA" if valid_filled else "SEM_AVANCO",
                "chamadaExecutada": not cache_hit_openai,
                "cacheHitOpenAI": cache_hit_openai,
                "camposSolicitados": list(missing_before),
                "camposPreenchidos": list(valid_filled),
                "camposComEvidenciaOficialConfirmada": fields_with_verified_evidence,
                "camposComConflitoEvidenciaOficial": fields_with_official_conflict,
                "camposAusentesDepois": list(missing_after),
                "camposObrigatoriosAusentesDepois": list(required_after),
                "fontesRetornadas": len(round_sources),
                "modelo": external.model,
                "reparoDeFormato": prompt_mode == "REPARO_FORMATO",
                "orcamentoRodadaSegundos": round(round_budget, 2),
                "duracaoRodadaMs": int(elapsed_round * 1000),
                "tempoRestanteDepoisSegundos": round(remaining_after_call, 2),
            }
        )

        if not valid_filled:
            if (
                round_number < max_rounds
                and required_after
                and not repair_next_round
                and _repair_on_no_advance_enabled()
                and remaining_after_call >= 3.0
            ):
                repair_next_round = True
                continue
            break

        repair_next_round = False
        if not missing_after or not required_after:
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
