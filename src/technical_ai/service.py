"""Orquestração de enriquecimento técnico.

Fluxo atual:
1. tenta primeiro a IA própria/fontes técnicas da Produto IA;
2. usa OpenAI apenas para preencher lacunas restantes;
3. se a OpenAI falhar, preserva e devolve o resultado da IA própria sem 503.
"""
from __future__ import annotations

from typing import Any
import json
from pathlib import Path

from ..enrichment.core import (
    PROVIDER_PRIORITY,
    apply_enrichment,
    required_missing_fields,
    technical_coverage,
    technical_missing_fields,
    technical_status,
)
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import (
    normalize_hardware_payload_for_backend,
    registration_payload_issues,
)
from ..extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    fallback_coverage_threshold,
    merge_meta_ai_response_into_payload_detailed,
    should_use_meta_ai_fallback,
)
from .providers import TechnicalAIProviderError, get_technical_ai_provider


def _identity_name(name: str | None, payload: dict[str, Any]) -> str:
    values = [
        name,
        payload.get("nome"),
        payload.get("marca"),
        payload.get("modelo"),
        payload.get("mpn"),
        payload.get("gtin"),
        payload.get("ean"),
    ]
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text.casefold() not in {item.casefold() for item in out}:
            out.append(text)
    return " | ".join(out) or "hardware"


def _coverage_state(category: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any], float, list[str]]:
    safe = normalize_hardware_payload_for_backend(category, payload or {})
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise TechnicalAIProviderError(
            "PAYLOAD_INVALIDO",
            "Categoria sem ficha técnica estruturada",
            status_code=400,
        )
    spec_field = schema[1]
    specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
    state = {"categoriaDetectada": category, "especificacoesEncontradas": specs}
    return safe, spec_field, state, technical_coverage(state), technical_missing_fields(state)


def _local_enrich(category: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    safe, spec_field, state, _coverage, _missing = _coverage_state(category, payload)
    result = {
        "categoriaDetectada": category,
        "nome": safe.get("nome"),
        "especificacoesEncontradas": state["especificacoesEncontradas"],
        "payloadParcialBackend": safe,
    }
    try:
        enriched = apply_enrichment(result, auto_mode=True)
    except Exception as exc:
        return safe, {
            "executado": False,
            "motivoIgnorado": "ERRO_ENRIQUECIMENTO_PROPRIO",
            "erro": str(exc),
            "camposPreenchidos": [],
            "fontesConsultadas": [],
        }

    local_payload = enriched.get("payloadParcialBackend")
    if not isinstance(local_payload, dict):
        local_payload = dict(safe)
        local_specs = enriched.get("especificacoesEncontradas")
        if isinstance(local_specs, dict):
            local_payload[spec_field] = local_specs

    local_safe = normalize_hardware_payload_for_backend(category, local_payload)
    info = enriched.get("enriquecimentoTecnico")
    return local_safe, info if isinstance(info, dict) else {}


def _local_sources(info: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in info.get("fontesConsultadas") or []:
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        source = str(item.get("fonte") or "").strip()
        if source and source not in out:
            out.append(source)
    return out


def _local_only_result(
    *,
    category: str,
    name: str | None,
    safe_initial: dict[str, Any],
    safe_local: dict[str, Any],
    local_info: dict[str, Any],
    coverage_before: float,
    provider_error: TechnicalAIProviderError | None = None,
    hardware_id: int | str | None = None,
) -> dict[str, Any]:
    safe_after, _spec_field, state_after, coverage_after, missing_after = _coverage_state(category, safe_local)
    filled = list(dict.fromkeys(local_info.get("camposPreenchidos") or []))
    result: dict[str, Any] = {
        "utilizado": bool(filled),
        "provedor": "PROJETO_IA",
        "provedorExterno": "OPENAI",
        "categoria": category,
        "nome": name or safe_after.get("nome"),
        "somentePreencheLacunas": True,
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_after, 4),
        "camposPreenchidos": filled,
        "camposAusentes": missing_after,
        "camposObrigatoriosAusentes": required_missing_fields(state_after),
        "conflitos": list(local_info.get("conflitos") or []),
        "especificacoesInterpretadas": {},
        "statusFicha": technical_status(state_after, conflicts=local_info.get("conflitos") or []),
        "payload": safe_after,
        "payloadValidoParaCadastro": not bool(registration_payload_issues(category, safe_after)),
        "problemasPayload": list(registration_payload_issues(category, safe_after)),
        "fontesIaPropria": _local_sources(local_info),
        "enriquecimentoProprio": local_info,
    }
    if provider_error is not None:
        result["fallbackExternoFalhou"] = True
        result["motivo"] = provider_error.code
        result["erroProvedor"] = {
            "codigo": provider_error.code,
            "mensagem": provider_error.message,
            "statusProvedor": provider_error.provider_status_code,
        }
        result["mensagem"] = (
            "A OpenAI não pôde completar a ficha. Foram preservados os dados obtidos pela IA própria."
        )
    elif not missing_after:
        result["motivo"] = "FICHA_COMPLETADA_PELA_IA_PROPRIA"

    if hardware_id is not None:
        result["hardwareId"] = hardware_id
        result["payloadOriginal"] = safe_initial
    return result


def build_technical_ai_prompt(category: str, name: str | None, payload: dict[str, Any]) -> tuple[str, list[str]]:
    category = str(category or "").strip().upper()
    safe, _spec_field, _state, _coverage, missing = _coverage_state(category, payload)
    identity = str(name or safe.get("nome") or safe.get("modelo") or "hardware").strip()
    return build_meta_ai_prompt(category, identity, missing), missing


def enrich_hardware_with_external_ai(
    *,
    provider_name: str | None,
    category: str,
    name: str | None,
    payload: dict[str, Any],
    hardware_id: int | str | None = None,
    only_fill_gaps: bool = True,
) -> dict[str, Any]:
    category = str(category or "").strip().upper()
    if only_fill_gaps is not True:
        raise TechnicalAIProviderError(
            "PAYLOAD_INVALIDO",
            "somentePreencheLacunas deve permanecer true para enriquecimento automático",
            status_code=400,
        )

    safe_initial, spec_field, state_initial, coverage_before, missing_before = _coverage_state(category, payload)
    status_before = technical_status(state_initial)

    if not missing_before:
        result = {
            "utilizado": False,
            "motivo": "FICHA_SEM_LACUNAS",
            "provedor": "PROJETO_IA",
            "provedorExterno": "OPENAI",
            "categoria": category,
            "nome": name or safe_initial.get("nome"),
            "somentePreencheLacunas": True,
            "coberturaAntes": round(coverage_before, 4),
            "coberturaDepois": round(coverage_before, 4),
            "camposPreenchidos": [],
            "camposAusentes": [],
            "camposObrigatoriosAusentes": required_missing_fields(state_initial),
            "conflitos": [],
            "especificacoesInterpretadas": {},
            "statusFicha": status_before,
            "payload": safe_initial,
        }
        if hardware_id is not None:
            result["hardwareId"] = hardware_id
        return result

    # 1) IA própria / fontes técnicas primeiro.
    safe_local, local_info = _local_enrich(category, safe_initial)
    safe_local, _local_spec_field, state_local, _coverage_local, missing_local = _coverage_state(category, safe_local)

    if not missing_local:
        return _local_only_result(
            category=category,
            name=name,
            safe_initial=safe_initial,
            safe_local=safe_local,
            local_info=local_info,
            coverage_before=coverage_before,
            hardware_id=hardware_id,
        )

    # 2) OpenAI somente para lacunas que permaneceram.
    prompt, missing_from_prompt = build_technical_ai_prompt(category, name, safe_local)
    provider = get_technical_ai_provider(provider_name or "OPENAI")
    try:
        external = provider.enrich(prompt)
    except TechnicalAIProviderError as exc:
        # 3) Falha externa nunca derruba o botão Completar com IA.
        return _local_only_result(
            category=category,
            name=name,
            safe_initial=safe_initial,
            safe_local=safe_local,
            local_info=local_info,
            coverage_before=coverage_before,
            provider_error=exc,
            hardware_id=hardware_id,
        )

    safe_after, external_filled, parsed_specs, external_conflicts = merge_meta_ai_response_into_payload_detailed(
        category,
        safe_local,
        external.text,
    )
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    specs_after = safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {}
    state_after = {"categoriaDetectada": category, "especificacoesEncontradas": specs_after}
    coverage_after = technical_coverage(state_after)
    missing_after = technical_missing_fields(state_after)
    local_conflicts = list(local_info.get("conflitos") or [])
    conflicts = local_conflicts + list(external_conflicts or [])
    status_after = technical_status(state_after, conflicts=conflicts)

    local_filled = list(local_info.get("camposPreenchidos") or [])
    filled = list(dict.fromkeys(local_filled + list(external_filled or [])))

    if not parsed_specs and not local_filled:
        return _local_only_result(
            category=category,
            name=name,
            safe_initial=safe_initial,
            safe_local=safe_local,
            local_info=local_info,
            coverage_before=coverage_before,
            provider_error=TechnicalAIProviderError(
                "PARSER_SEM_DADOS",
                "A OpenAI respondeu, mas nenhum campo técnico compatível foi interpretado",
                status_code=422,
            ),
            hardware_id=hardware_id,
        )

    payload_issues = registration_payload_issues(category, safe_after)
    threshold = fallback_coverage_threshold()
    meta_recommended = should_use_meta_ai_fallback(coverage_after, threshold=threshold)
    meta_fallback = {
        "recomendado": bool(meta_recommended),
        "fonte": "META_AI_WHATSAPP",
        "somenteQuandoPoucosDados": True,
        "coberturaAtual": round(coverage_after, 4),
        "limiarCobertura": round(threshold, 4),
        "camposAusentes": missing_after,
        "camposObrigatoriosAusentes": required_missing_fields(state_after),
        "promptSugerido": build_meta_ai_prompt(
            category,
            str(name or safe_after.get("nome") or "hardware"),
            missing_after,
        ) if meta_recommended and missing_after else None,
    }

    result: dict[str, Any] = {
        "utilizado": bool(filled),
        "provedor": external.provider,
        "modelo": external.model,
        "categoria": category,
        "nome": name or safe_after.get("nome"),
        "somentePreencheLacunas": True,
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_after, 4),
        "camposPreenchidos": filled,
        "camposAusentes": missing_after,
        "camposObrigatoriosAusentes": required_missing_fields(state_after),
        "conflitos": conflicts,
        "especificacoesInterpretadas": parsed_specs,
        "statusFicha": status_after,
        "payload": safe_after,
        "payloadValidoParaCadastro": not bool(payload_issues),
        "problemasPayload": list(payload_issues),
        "promptUtilizado": prompt,
        "camposSolicitados": missing_from_prompt,
        "fontesDeclaradas": external.sources,
        "fontesIaPropria": _local_sources(local_info),
        "enriquecimentoProprio": local_info,
        "metaAiWhatsappFallback": meta_fallback,
    }
    if hardware_id is not None:
        result["hardwareId"] = hardware_id
        result["payloadOriginal"] = safe_initial
    return result
