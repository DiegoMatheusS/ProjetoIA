"""Enriquecimento técnico automático e transparente.

Este módulo liga o provider técnico (Gemini, por enquanto) aos fluxos que já
existiam no CriaByte, sem exigir mudança de frontend/backend. A regra é:

- mantém o mesmo contrato HTTP das rotas existentes;
- só tenta IA externa quando a ficha estruturada está abaixo do limiar;
- preenche somente lacunas;
- qualquer falha do provider preserva o payload original;
- o resultado sempre passa novamente pela normalização DTO-safe.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..enrichment.core import (
    technical_coverage,
    technical_missing_fields,
    technical_status,
    required_missing_fields,
)
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..extractors.meta_ai_whatsapp import fallback_coverage_threshold
from .providers import TechnicalAIProviderError, get_technical_ai_provider
from .service import enrich_hardware_with_external_ai


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "sim", "yes", "on"}


def automatic_technical_ai_enabled() -> bool:
    """Provider técnico automático ligado por padrão quando configurado.

    Pode ser desligado rapidamente no Railway sem mudar código:
    IA_TECNICA_AUTO=false
    """
    return _env_bool("IA_TECNICA_AUTO", True)


def automatic_technical_ai_threshold() -> float:
    raw = os.getenv("IA_TECNICA_AUTO_COVERAGE")
    if raw is None or not str(raw).strip():
        return fallback_coverage_threshold()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback_coverage_threshold()
    return min(1.0, max(0.0, value))


def automatic_technical_ai_max_items() -> int:
    try:
        return min(50, max(1, int(os.getenv("IA_TECNICA_AUTO_MAX_ITEMS", "20"))))
    except ValueError:
        return 20


def automatic_technical_ai_workers() -> int:
    try:
        return min(8, max(1, int(os.getenv("IA_TECNICA_AUTO_WORKERS", "4"))))
    except ValueError:
        return 4




def _has_minimum_identity(name: str | None, payload: dict[str, Any]) -> bool:
    values = [name, payload.get("nome"), payload.get("modelo"), payload.get("mpn"), payload.get("gtin"), payload.get("ean")]
    texts = [str(value or "").strip() for value in values]
    useful = [value for value in texts if value and value.casefold() not in {"hardware", "produto", "nao informado", "não informado"}]
    return bool(useful)

def _coverage_state(category: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, float, list[str]]:
    category = str(category or "").strip().upper()
    safe = normalize_hardware_payload_for_backend(category, payload or {})
    schema = SCHEMAS.get(category)
    spec_field = schema[1] if schema else None
    if not spec_field:
        return safe, None, 1.0, []
    specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
    state = {"categoriaDetectada": category, "especificacoesEncontradas": specs}
    return safe, spec_field, technical_coverage(state), technical_missing_fields(state)


def maybe_auto_enrich_hardware(
    *,
    category: str,
    name: str | None,
    payload: dict[str, Any],
    provider_name: str | None = None,
    hardware_id: int | str | None = None,
) -> dict[str, Any]:
    """Tenta IA externa sem nunca transformar falha do provider em falha do fluxo.

    O retorno usa uma estrutura próxima de ``enrich_hardware_with_external_ai``
    para facilitar diagnóstico, mas sempre contém ``payload`` seguro.
    """
    category = str(category or "").strip().upper()
    safe_before, spec_field, coverage_before, missing_before = _coverage_state(category, payload)
    threshold = automatic_technical_ai_threshold()
    selected_provider = (provider_name or os.getenv("IA_TECNICA_PROVIDER", "GEMINI") or "GEMINI").strip().upper()

    base: dict[str, Any] = {
        "automatico": True,
        "utilizado": False,
        "provedor": selected_provider,
        "categoria": category,
        "nome": name or safe_before.get("nome"),
        "somentePreencheLacunas": True,
        "coberturaAntes": round(coverage_before, 4),
        "coberturaDepois": round(coverage_before, 4),
        "limiarCobertura": round(threshold, 4),
        "camposPreenchidos": [],
        "camposAusentes": missing_before,
        "payload": safe_before,
    }
    if hardware_id is not None:
        base["hardwareId"] = hardware_id

    if not spec_field:
        base["motivo"] = "CATEGORIA_SEM_FICHA_TECNICA_ESTRUTURADA"
        return base
    if not _has_minimum_identity(name, safe_before):
        base["motivo"] = "IDENTIDADE_INSUFICIENTE"
        return base
    if not automatic_technical_ai_enabled():
        base["motivo"] = "IA_TECNICA_AUTOMATICA_DESABILITADA"
        return base
    if coverage_before >= threshold:
        base["motivo"] = "COBERTURA_NORMAL_SUFICIENTE"
        return base
    if not missing_before:
        base["motivo"] = "FICHA_SEM_LACUNAS"
        return base

    try:
        provider = get_technical_ai_provider(selected_provider)
    except TechnicalAIProviderError as exc:
        base["motivo"] = exc.code
        base["erro"] = {"codigo": exc.code, "mensagem": exc.message}
        return base
    if not provider.configured:
        base["motivo"] = "PROVEDOR_NAO_CONFIGURADO"
        return base

    try:
        enriched = enrich_hardware_with_external_ai(
            provider_name=selected_provider,
            category=category,
            name=name,
            payload=safe_before,
            hardware_id=hardware_id,
            only_fill_gaps=True,
        )
    except TechnicalAIProviderError as exc:
        base["motivo"] = exc.code
        base["erro"] = {"codigo": exc.code, "mensagem": exc.message}
        return base
    except Exception as exc:  # defesa: a busca/link não pode cair por provider externo
        base["motivo"] = "ERRO_IA_TECNICA_AUTOMATICA"
        base["erro"] = {"codigo": "ERRO_IA_TECNICA_AUTOMATICA", "mensagem": str(exc)}
        return base

    safe_after, _, coverage_after, missing_after = _coverage_state(
        category, enriched.get("payload") if isinstance(enriched.get("payload"), dict) else safe_before
    )
    enriched = dict(enriched)
    enriched["automatico"] = True
    enriched["payload"] = safe_after
    enriched["coberturaAntes"] = round(coverage_before, 4)
    enriched["coberturaDepois"] = round(coverage_after, 4)
    enriched["limiarCobertura"] = round(threshold, 4)
    enriched["camposAusentes"] = missing_after
    return enriched


def auto_enrich_discovery_result(category: str, result: dict[str, Any]) -> dict[str, Any]:
    """Enriquece automaticamente cards de descoberta com baixa cobertura.

    Mantém ordem e formato externo. O frontend continua recebendo os mesmos
    ``itens``; apenas ``payload``/``payloadHardware``/ficha podem voltar mais
    completos. Erros do Gemini ficam em diagnóstico e não derrubam a busca.
    """
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    spec_field = schema[1] if schema else None
    items = result.get("itens") if isinstance(result, dict) else None
    if not spec_field or not isinstance(items, list) or not items:
        return result

    threshold = automatic_technical_ai_threshold()
    provider_name = (os.getenv("IA_TECNICA_PROVIDER", "GEMINI") or "GEMINI").strip().upper()
    if not automatic_technical_ai_enabled():
        result["iaTecnicaAutomatica"] = {
            "habilitada": False,
            "provedor": provider_name,
            "limiarCobertura": round(threshold, 4),
            "tentados": 0,
            "enriquecidos": 0,
        }
        return result

    try:
        provider = get_technical_ai_provider(provider_name)
        configured = bool(provider.configured)
    except TechnicalAIProviderError:
        configured = False
    if not configured:
        result["iaTecnicaAutomatica"] = {
            "habilitada": True,
            "provedor": provider_name,
            "provedorConfigurado": False,
            "limiarCobertura": round(threshold, 4),
            "tentados": 0,
            "enriquecidos": 0,
        }
        return result

    eligible: list[tuple[int, dict[str, Any], dict[str, Any], float]] = []
    max_items = automatic_technical_ai_max_items()
    for idx, item in enumerate(items):
        if len(eligible) >= max_items or not isinstance(item, dict):
            continue
        raw = item.get("payload") if isinstance(item.get("payload"), dict) else item.get("payloadHardware")
        if not isinstance(raw, dict):
            continue
        safe, _, coverage, missing = _coverage_state(category, raw)
        if coverage < threshold and missing:
            eligible.append((idx, item, safe, coverage))

    if not eligible:
        result["iaTecnicaAutomatica"] = {
            "habilitada": True,
            "provedor": provider_name,
            "provedorConfigurado": True,
            "limiarCobertura": round(threshold, 4),
            "tentados": 0,
            "enriquecidos": 0,
        }
        return result

    workers = min(automatic_technical_ai_workers(), len(eligible))
    outcomes: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="technical-ai") as executor:
        futures = {}
        for idx, item, safe, _coverage in eligible:
            display_name = str(
                safe.get("nome")
                or item.get("nome")
                or (item.get("identidade") or {}).get("nome")
                or "hardware"
            )
            future = executor.submit(
                maybe_auto_enrich_hardware,
                category=category,
                name=display_name,
                payload=safe,
                provider_name=provider_name,
                hardware_id=item.get("hardwareId"),
            )
            futures[future] = idx
        for future in as_completed(futures):
            idx = futures[future]
            try:
                outcomes[idx] = future.result()
            except Exception as exc:  # nunca derrubar descoberta por worker
                outcomes[idx] = {
                    "automatico": True,
                    "utilizado": False,
                    "provedor": provider_name,
                    "motivo": "ERRO_IA_TECNICA_AUTOMATICA",
                    "erro": {"codigo": "ERRO_IA_TECNICA_AUTOMATICA", "mensagem": str(exc)},
                }

    enriched_count = 0
    errors = 0
    for idx, outcome in outcomes.items():
        item = items[idx]
        item["iaTecnicaEnriquecimentoAutomatico"] = {
            key: value
            for key, value in outcome.items()
            if key not in {"payload", "payloadOriginal", "especificacoesInterpretadas", "promptUtilizado"}
        }
        if outcome.get("erro"):
            errors += 1
        if outcome.get("utilizado") and isinstance(outcome.get("payload"), dict):
            safe = normalize_hardware_payload_for_backend(category, outcome["payload"])
            specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
            item["payload"] = safe
            item["payloadHardware"] = safe
            item["especificacoesEncontradas"] = specs
            item["coberturaTecnica"] = round(float(outcome.get("coberturaDepois") or 0), 4)
            item["qualidade"] = int(round(item["coberturaTecnica"] * 100))
            item["camposAusentes"] = list(outcome.get("camposAusentes") or [])
            item["camposAindaAusentes"] = list(outcome.get("camposAusentes") or [])
            item["statusFicha"] = outcome.get("statusFicha") or technical_status(
                {"categoriaDetectada": category, "especificacoesEncontradas": specs},
                conflicts=outcome.get("conflitos") or [],
            )
            item["camposObrigatoriosAusentes"] = required_missing_fields(
                {"categoriaDetectada": category, "especificacoesEncontradas": specs}
            )
            sources = list(item.get("fontes") or [])
            label = str(outcome.get("provedor") or provider_name)
            if label and label not in sources:
                sources.append(label)
            item["fontes"] = sources
            enriched_count += 1

    result["itens"] = items
    result["iaTecnicaAutomatica"] = {
        "habilitada": True,
        "provedor": provider_name,
        "provedorConfigurado": True,
        "limiarCobertura": round(threshold, 4),
        "limiteItensPorBusca": max_items,
        "concorrencia": workers,
        "tentados": len(eligible),
        "enriquecidos": enriched_count,
        "falhasPreservadas": errors,
    }
    return result


def auto_enrich_link_result(result: dict[str, Any]) -> dict[str, Any]:
    """Aplica a mesma regra ao fluxo histórico ``/analisar`` por URL.

    O bloco comercial/oferta nunca é alterado. O payload de Hardware é sempre
    normalizado antes de sair, mesmo se o Gemini estiver indisponível.
    """
    if not isinstance(result, dict):
        return result
    category = str(result.get("categoriaDetectada") or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or schema[0] != "HARDWARE" or not schema[1]:
        return result

    spec_field = schema[1]
    raw_payload = result.get("payloadParcialBackend") if isinstance(result.get("payloadParcialBackend"), dict) else {}
    safe_before = normalize_hardware_payload_for_backend(category, raw_payload)
    result["payloadParcialBackend"] = safe_before
    specs_before = safe_before.get(spec_field) if isinstance(safe_before.get(spec_field), dict) else {}
    result["especificacoesEncontradas"] = specs_before
    state_before = {"categoriaDetectada": category, "especificacoesEncontradas": specs_before}
    result["camposObrigatoriosAusentes"] = required_missing_fields(state_before)

    outcome = maybe_auto_enrich_hardware(
        category=category,
        name=str(safe_before.get("nome") or result.get("nome") or "hardware"),
        payload=safe_before,
        provider_name=os.getenv("IA_TECNICA_PROVIDER", "GEMINI"),
    )
    result["iaTecnicaAutomatica"] = {
        key: value
        for key, value in outcome.items()
        if key not in {"payload", "payloadOriginal", "especificacoesInterpretadas", "promptUtilizado"}
    }

    if outcome.get("utilizado") and isinstance(outcome.get("payload"), dict):
        safe_after = normalize_hardware_payload_for_backend(category, outcome["payload"])
        specs_after = safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {}
        state_after = {"categoriaDetectada": category, "especificacoesEncontradas": specs_after}
        result["payloadParcialBackend"] = safe_after
        result["especificacoesEncontradas"] = specs_after
        result["camposObrigatoriosAusentes"] = required_missing_fields(state_after)
        result["enriquecimentoIaTecnica"] = {
            "automatico": True,
            "utilizado": True,
            "provedor": outcome.get("provedor"),
            "modelo": outcome.get("modelo"),
            "coberturaAntes": outcome.get("coberturaAntes"),
            "coberturaDepois": outcome.get("coberturaDepois"),
            "camposPreenchidos": list(outcome.get("camposPreenchidos") or []),
            "camposAusentes": list(outcome.get("camposAusentes") or []),
            "conflitos": list(outcome.get("conflitos") or []),
            "fontesDeclaradas": list(outcome.get("fontesDeclaradas") or []),
        }
    else:
        result["enriquecimentoIaTecnica"] = {
            "automatico": True,
            "utilizado": False,
            "provedor": outcome.get("provedor"),
            "motivo": outcome.get("motivo"),
            "coberturaAntes": outcome.get("coberturaAntes"),
            "coberturaDepois": outcome.get("coberturaDepois"),
            "erro": outcome.get("erro"),
        }
    return result
