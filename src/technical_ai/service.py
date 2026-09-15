"""Orquestração de enriquecimento técnico.

Fluxo atual:
1. o agente de pesquisa técnica planeja e consulta fontes especializadas para o hardware selecionado;
2. usa OpenAI com a mesma pergunta do Meta AI para preencher as lacunas restantes;
3. se a pesquisa local ou a OpenAI falhar, preserva o payload atual sem derrubar o botão.
"""
from __future__ import annotations

from typing import Any

from ..enrichment.quality import validate_specs
from ..enrichment.core import (
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
from ..research_agent.agent import research_hardware_locally
from .evidence import collect_cited_sources
from .providers import TechnicalAIProviderError, get_technical_ai_provider


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
    safe, _spec_field, _state, _coverage, _missing = _coverage_state(category, payload)
    try:
        return research_hardware_locally(
            category,
            safe,
            name=safe.get("nome"),
        )
    except Exception as exc:
        # O agente local é uma etapa de pesquisa, não um ponto único de falha.
        # Em erro inesperado, a OpenAI ainda recebe a mesma pergunta do Meta AI
        # para tentar completar as lacunas do payload original.
        return safe, {
            "executado": False,
            "motivoIgnorado": "ERRO_AGENTE_PESQUISA_TECNICA",
            "erro": f"{type(exc).__name__}: {exc}",
            "camposPreenchidos": [],
            "fontesConsultadas": [],
            "origemPorCampo": {},
            "conflitos": [],
            "agentePesquisa": {
                "versao": 1,
                "ativo": True,
                "resultado": "ERRO_COM_FALLBACK_OPENAI",
            },
        }


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
        "origemPorCampo": local_info.get("origemPorCampo") or {},
        "camposIaNaoConfirmados": local_info.get("camposIaNaoConfirmados") or [],
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
            "A OpenAI não pôde completar a ficha. Foram preservados os dados obtidos pela pesquisa técnica."
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

    # 1) Agente de pesquisa técnica / fontes especializadas primeiro.
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

    # 2) OpenAI somente para lacunas que permaneceram. O prompt enviado é
    # exatamente o mesmo formato Campo: valor usado pelo Completar por Meta AI.
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

    # As citações da busca web continuam sendo coletadas como proveniência, mas
    # não bloqueiam o uso de um campo apenas porque o coletor local ainda não
    # possui o mesmo trecho. A resposta continua passando pelo parser, schema,
    # normalização e validação técnica antes de entrar no payload.
    try:
        collect_cited_sources(category, safe_local, external.sources, local_info)
    except Exception as exc:
        local_info["erroVerificacaoCitacoes"] = type(exc).__name__

    safe_after, external_filled, parsed_specs, external_conflicts = merge_meta_ai_response_into_payload_detailed(
        category,
        safe_local,
        external.text,
    )
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    specs_after, consistency_issues = validate_specs(category, safe_after.get(spec_field) or {})
    safe_after[spec_field] = specs_after
    rejected = list(consistency_issues)
    external_filled = [field for field in external_filled if specs_after.get(field) not in (None, "", [])]
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
                "A resposta da OpenAI não trouxe campos técnicos reconhecíveis; os dados coletados foram preservados",
                status_code=422,
            ),
            hardware_id=hardware_id,
        )

    source_urls = [
        str(item.get("url") or "").strip()
        for item in (external.sources or [])
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ][:20]
    ai_provenance = {
        field: {
            "fonte": "OPENAI_WEB_SEARCH" if source_urls else "OPENAI",
            "modelo": external.model,
            "urls": source_urls,
            "metodo": "IA_PARSER_SCHEMA_VALIDADO",
        }
        for field in external_filled
    }

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
        "origemPorCampo": {**(local_info.get("origemPorCampo") or {}), **ai_provenance},
        "camposIaNaoConfirmados": rejected,
        "fontesIaPropria": _local_sources(local_info),
        "enriquecimentoProprio": local_info,
        "metaAiWhatsappFallback": meta_fallback,
    }
    if hardware_id is not None:
        result["hardwareId"] = hardware_id
        result["payloadOriginal"] = safe_initial
    return result
