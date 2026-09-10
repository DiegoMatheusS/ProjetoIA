"""Orquestração de enriquecimento técnico por IA externa.

A IA externa pesquisa/responde. A Produto IA continua responsável por decidir
lacunas, interpretar, normalizar, preservar valores existentes e validar a
resposta final contra o contrato técnico do CriaByte.
"""
from __future__ import annotations

from typing import Any

from ..enrichment.core import technical_coverage, technical_missing_fields, technical_status
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend, registration_payload_issues
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


def build_technical_ai_prompt(category: str, name: str | None, payload: dict[str, Any]) -> tuple[str, list[str]]:
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise TechnicalAIProviderError("PAYLOAD_INVALIDO", "Categoria sem ficha técnica estruturada", status_code=400)

    safe = normalize_hardware_payload_for_backend(category, payload or {})
    spec_field = schema[1]
    specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
    coverage_input = {"categoriaDetectada": category, "especificacoesEncontradas": specs}
    missing = technical_missing_fields(coverage_input)
    identity = _identity_name(name, safe)
    base = build_meta_ai_prompt(category, identity, missing)
    prompt = (
        "Use pesquisa na Web quando disponível e confirme que os dados pertencem EXATAMENTE ao modelo/variante informado. "
        "Dê preferência ao fabricante oficial e a fontes técnicas confiáveis. Não misture variantes com MPN/GTIN diferentes.\n\n"
        + base
    )
    return prompt, missing


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
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise TechnicalAIProviderError("PAYLOAD_INVALIDO", "Categoria sem ficha técnica estruturada", status_code=400)
    if only_fill_gaps is not True:
        # Atualização automática nunca substitui valor confirmado.
        raise TechnicalAIProviderError(
            "PAYLOAD_INVALIDO",
            "somentePreencheLacunas deve permanecer true para enriquecimento automático",
            status_code=400,
        )

    safe_before = normalize_hardware_payload_for_backend(category, payload or {})
    spec_field = schema[1]
    specs_before = safe_before.get(spec_field) if isinstance(safe_before.get(spec_field), dict) else {}
    before_input = {"categoriaDetectada": category, "especificacoesEncontradas": specs_before}
    coverage_before = technical_coverage(before_input)
    missing_before = technical_missing_fields(before_input)
    status_before = technical_status(before_input)

    prompt, missing_from_prompt = build_technical_ai_prompt(category, name, safe_before)
    if not missing_before:
        result = {
            "utilizado": False,
            "motivo": "FICHA_SEM_LACUNAS",
            "provedor": (provider_name or "GEMINI").upper(),
            "categoria": category,
            "nome": name or safe_before.get("nome"),
            "somentePreencheLacunas": True,
            "coberturaAntes": round(coverage_before, 4),
            "coberturaDepois": round(coverage_before, 4),
            "camposPreenchidos": [],
            "camposAusentes": [],
            "conflitos": [],
            "especificacoesInterpretadas": {},
            "statusFicha": status_before,
            "payload": safe_before,
            "promptUtilizado": prompt,
        }
        if hardware_id is not None:
            result["hardwareId"] = hardware_id
        return result

    provider = get_technical_ai_provider(provider_name)
    external = provider.enrich(prompt)
    safe_after, filled, parsed_specs, conflicts = merge_meta_ai_response_into_payload_detailed(
        category, safe_before, external.text
    )
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    specs_after = safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {}
    after_input = {"categoriaDetectada": category, "especificacoesEncontradas": specs_after}
    coverage_after = technical_coverage(after_input)
    missing_after = technical_missing_fields(after_input)
    status_after = technical_status(after_input, conflicts=conflicts)

    if not parsed_specs:
        raise TechnicalAIProviderError(
            "PARSER_SEM_DADOS",
            "A IA externa respondeu, mas nenhum campo técnico compatível foi interpretado",
            status_code=422,
        )

    # Última barreira de compatibilidade antes de devolver ao CriaByte.
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
        "promptSugerido": build_meta_ai_prompt(
            category,
            str(name or safe_after.get("nome") or "hardware"),
            missing_after,
        ) if meta_recommended and missing_after else None,
    }

    result: dict[str, Any] = {
        "utilizado": True,
        "provedor": external.provider,
        "modelo": external.model,
        "categoria": category,
        "nome": name or safe_after.get("nome"),
        "somentePreencheLacunas": True,
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_after, 4),
        "camposPreenchidos": filled,
        "camposAusentes": missing_after,
        "conflitos": conflicts,
        "especificacoesInterpretadas": parsed_specs,
        "statusFicha": status_after,
        "payload": safe_after,
        "payloadValidoParaCadastro": not bool(payload_issues),
        "problemasPayload": list(payload_issues),
        "promptUtilizado": prompt,
        "camposSolicitados": missing_from_prompt,
        "fontesDeclaradas": external.sources,
        "metaAiWhatsappFallback": meta_fallback,
    }
    if hardware_id is not None:
        result["hardwareId"] = hardware_id
        result["payloadOriginal"] = safe_before
    return result
