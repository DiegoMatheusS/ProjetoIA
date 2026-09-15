"""Orquestracao de enriquecimento tecnico.

Fluxo atual:
1. o agente de pesquisa tecnica consulta fontes especializadas para o hardware selecionado;
2. a OpenAI recebe a mesma pergunta do Meta AI somente para as lacunas restantes;
3. se a primeira resposta avancar e ainda houver lacunas, uma segunda rodada focada pode ocorrer;
4. falha posterior preserva todo avanco obtido nas rodadas anteriores;
5. a ficha final passa por uma auditoria de qualidade antes de poder ser marcada como PRONTO.
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
    should_use_meta_ai_fallback,
)
from ..research_agent.agent import research_hardware_locally
from ..research_agent.confidence import annotate_field_confidence
from ..research_agent.quality_gate import evaluate_research_quality
from .iterative_research import run_iterative_external_research
from .providers import TechnicalAIProviderError, get_technical_ai_provider


def _coverage_state(category: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any], float, list[str]]:
    safe = normalize_hardware_payload_for_backend(category, payload or {})
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        raise TechnicalAIProviderError(
            "PAYLOAD_INVALIDO",
            "Categoria sem ficha tecnica estruturada",
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
        # O agente local e uma etapa de pesquisa, nao um ponto unico de falha.
        # Em erro inesperado, a OpenAI ainda recebe a mesma pergunta do Meta AI.
        return safe, {
            "executado": False,
            "motivoIgnorado": "ERRO_AGENTE_PESQUISA_TECNICA",
            "erro": f"{type(exc).__name__}: {exc}",
            "camposPreenchidos": [],
            "fontesConsultadas": [],
            "origemPorCampo": {},
            "conflitos": [],
            "agentePesquisa": {
                "versao": 5,
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


def _status_with_quality_gate(status: str, audit: dict[str, Any]) -> str:
    # A auditoria nunca promove uma ficha. Ela apenas impede PRONTO silencioso
    # quando um campo essencial veio de fonte fraca, sem proveniencia ou em conflito.
    if status == "PRONTO" and not audit.get("podeMarcarPronto"):
        return "PRECISA_REVISAO"
    return status


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
    conflicts = list(local_info.get("conflitos") or [])
    payload_issues = list(registration_payload_issues(category, safe_after))
    confidence_by_field = local_info.get("confiancaPorCampo") or {}
    audit = evaluate_research_quality(
        category,
        original_payload=safe_initial,
        final_payload=safe_after,
        confidence_by_field=confidence_by_field,
        conflicts=conflicts,
        registration_issues=payload_issues,
    )
    status_after = _status_with_quality_gate(
        technical_status(state_after, conflicts=conflicts),
        audit,
    )

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
        "conflitos": conflicts,
        "especificacoesInterpretadas": {},
        "statusFicha": status_after,
        "payload": safe_after,
        "payloadValidoParaCadastro": not bool(payload_issues),
        "problemasPayload": payload_issues,
        "fontesIaPropria": _local_sources(local_info),
        "enriquecimentoProprio": local_info,
        "origemPorCampo": local_info.get("origemPorCampo") or {},
        "confiancaPorCampo": confidence_by_field,
        "confiancaMediaPesquisa": local_info.get("confiancaMediaPesquisa"),
        "camposIaNaoConfirmados": local_info.get("camposIaNaoConfirmados") or [],
        "rodadasOpenAI": [],
        "auditoriaPesquisa": audit,
        "pesquisaConfiavel": bool(audit.get("podeMarcarPronto")),
        "camposParaRevisao": list(audit.get("camposParaRevisao") or []),
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
            "A OpenAI nao pode completar a ficha. Foram preservados os dados obtidos pela pesquisa tecnica."
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
            "somentePreencheLacunas deve permanecer true para enriquecimento automatico",
            status_code=400,
        )

    safe_initial, spec_field, state_initial, coverage_before, missing_before = _coverage_state(category, payload)
    status_before = technical_status(state_initial)

    if not missing_before:
        payload_issues = list(registration_payload_issues(category, safe_initial))
        audit = evaluate_research_quality(
            category,
            original_payload=safe_initial,
            final_payload=safe_initial,
            confidence_by_field={},
            conflicts=[],
            registration_issues=payload_issues,
        )
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
            "statusFicha": _status_with_quality_gate(status_before, audit),
            "payload": safe_initial,
            "payloadValidoParaCadastro": not bool(payload_issues),
            "problemasPayload": payload_issues,
            "rodadasOpenAI": [],
            "auditoriaPesquisa": audit,
            "pesquisaConfiavel": bool(audit.get("podeMarcarPronto")),
            "camposParaRevisao": list(audit.get("camposParaRevisao") or []),
        }
        if hardware_id is not None:
            result["hardwareId"] = hardware_id
        return result

    # 1) Agente local: cache seguro, fontes especializadas, busca focada e validacao.
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

    # 2) OpenAI: mesma pergunta Campo: valor do Meta AI. Pode fazer uma segunda
    # rodada somente quando a primeira realmente preencheu campos e ainda ha lacunas.
    provider = get_technical_ai_provider(provider_name or "OPENAI")
    external_result = run_iterative_external_research(
        provider=provider,
        category=category,
        name=name,
        payload=safe_local,
        local_info=local_info,
    )

    # Falha antes de qualquer avanco externo preserva exatamente o comportamento
    # tolerante anterior: devolve a pesquisa local em vez de gerar 503.
    if external_result.provider_error is not None and not external_result.filled_fields:
        return _local_only_result(
            category=category,
            name=name,
            safe_initial=safe_initial,
            safe_local=safe_local,
            local_info=local_info,
            coverage_before=coverage_before,
            provider_error=external_result.provider_error,
            hardware_id=hardware_id,
        )

    safe_after = normalize_hardware_payload_for_backend(category, external_result.payload)
    specs_after, final_consistency_issues = validate_specs(category, safe_after.get(spec_field) or {})
    safe_after[spec_field] = specs_after
    external_filled = [
        field
        for field in external_result.filled_fields
        if specs_after.get(field) not in (None, "", [])
    ]
    rejected = list(external_result.rejected or []) + list(final_consistency_issues or [])
    state_after = {"categoriaDetectada": category, "especificacoesEncontradas": specs_after}
    coverage_after = technical_coverage(state_after)
    missing_after = technical_missing_fields(state_after)
    local_conflicts = list(local_info.get("conflitos") or [])
    conflicts = local_conflicts + list(external_result.conflicts or [])

    local_filled = list(local_info.get("camposPreenchidos") or [])
    filled = list(dict.fromkeys(local_filled + external_filled))

    if not external_result.parsed_specs and not local_filled and not external_filled:
        return _local_only_result(
            category=category,
            name=name,
            safe_initial=safe_initial,
            safe_local=safe_local,
            local_info=local_info,
            coverage_before=coverage_before,
            provider_error=TechnicalAIProviderError(
                "PARSER_SEM_DADOS",
                "A resposta da OpenAI nao trouxe campos tecnicos reconheciveis; os dados coletados foram preservados",
                status_code=422,
            ),
            hardware_id=hardware_id,
        )

    origins = {
        **(local_info.get("origemPorCampo") or {}),
        **(external_result.provenance or {}),
    }
    confidence = annotate_field_confidence(
        {
            "origemPorCampo": origins,
            "conflitos": conflicts,
        }
    )

    payload_issues = list(registration_payload_issues(category, safe_after))
    audit = evaluate_research_quality(
        category,
        original_payload=safe_initial,
        final_payload=safe_after,
        confidence_by_field=confidence.get("confiancaPorCampo") or {},
        conflicts=conflicts,
        registration_issues=payload_issues,
    )
    status_after = _status_with_quality_gate(
        technical_status(state_after, conflicts=conflicts),
        audit,
    )

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
        "provedor": external_result.provider or "OPENAI",
        "modelo": external_result.model,
        "categoria": category,
        "nome": name or safe_after.get("nome"),
        "somentePreencheLacunas": True,
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_after, 4),
        "camposPreenchidos": filled,
        "camposAusentes": missing_after,
        "camposObrigatoriosAusentes": required_missing_fields(state_after),
        "conflitos": conflicts,
        "especificacoesInterpretadas": external_result.parsed_specs,
        "statusFicha": status_after,
        "payload": safe_after,
        "payloadValidoParaCadastro": not bool(payload_issues),
        "problemasPayload": payload_issues,
        # Mantidos por compatibilidade com o frontend/diagnostico existente.
        "promptUtilizado": external_result.first_prompt,
        "camposSolicitados": external_result.first_requested_fields,
        "fontesDeclaradas": external_result.sources,
        "origemPorCampo": origins,
        "confiancaPorCampo": confidence.get("confiancaPorCampo") or {},
        "confiancaMediaPesquisa": confidence.get("confiancaMediaPesquisa"),
        "camposIaNaoConfirmados": rejected,
        "fontesIaPropria": _local_sources(local_info),
        "enriquecimentoProprio": local_info,
        "rodadasOpenAI": external_result.rounds,
        "metaAiWhatsappFallback": meta_fallback,
        "auditoriaPesquisa": audit,
        "pesquisaConfiavel": bool(audit.get("podeMarcarPronto")),
        "camposParaRevisao": list(audit.get("camposParaRevisao") or []),
    }

    # Se a primeira rodada funcionou e a segunda falhou, o avanco nao e descartado.
    if external_result.provider_error is not None and external_filled:
        result["openAiInterrompidaAposAvanco"] = True
        result["erroProvedorParcial"] = {
            "codigo": external_result.provider_error.code,
            "mensagem": external_result.provider_error.message,
            "statusProvedor": external_result.provider_error.provider_status_code,
        }

    if hardware_id is not None:
        result["hardwareId"] = hardware_id
        result["payloadOriginal"] = safe_initial
    return result
