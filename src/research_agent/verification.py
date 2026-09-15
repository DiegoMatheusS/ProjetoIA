from __future__ import annotations

import os
import time
from typing import Any

from ..enrichment.identity import build_identity, identity_is_strong
from ..enrichment.quality import evidence_for_specs, validate_specs
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..extractors.ml_specs import extract_specs
from .confidence import source_confidence
from .planner import CATEGORY_SOURCE_ORDER
from .source_router import build_providers


def _enabled() -> bool:
    return os.getenv("TECH_RESEARCH_VERIFY_LOW_CONFIDENCE", "false").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _normalized(value: Any):
    if isinstance(value, list):
        return sorted(str(item).strip().casefold() for item in value)
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    return value


def _source_names(category: str, origin_by_field: dict[str, Any], fields: list[str]) -> list[str]:
    category = str(category or "").strip().upper()
    ordered = list(
        CATEGORY_SOURCE_ORDER.get(
            category,
            ("FABRICANTE_OFICIAL", "ICECAT", "GEIZHALS", "PC_KOMBO"),
        )
    )
    original_sources = {
        str((origin_by_field.get(field) or {}).get("fonte") or "").strip().upper()
        for field in fields
        if isinstance(origin_by_field.get(field), dict)
    }
    original_sources.discard("")

    # A verificação precisa ser independente. Evita reutilizar a mesma fonte que
    # originou o valor questionado; fontes externas como OPENAI nem fazem parte
    # deste roteador local, mas o filtro também cobre PC_KOMBO/Geizhals etc.
    independent = [source for source in ordered if source not in original_sources]
    return independent or ordered


def verify_questionable_fields(
    category: str,
    *,
    payload: dict[str, Any],
    fields: list[str] | tuple[str, ...],
    origin_by_field: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tenta confirmar campos essenciais em uma segunda fonte independente.

    A função nunca altera o payload. Ela apenas devolve confirmações/conflitos
    para a auditoria de qualidade decidir se um campo pode sair da revisão.
    Browser fallback fica desligado nesta etapa para limitar latência.
    """
    targets = list(dict.fromkeys(str(field) for field in fields if field))
    if not targets:
        return {
            "executado": False,
            "motivoIgnorado": "SEM_CAMPOS_PARA_VERIFICAR",
            "camposSolicitados": [],
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }
    if not _enabled():
        return {
            "executado": False,
            "motivoIgnorado": "TECH_RESEARCH_VERIFY_LOW_CONFIDENCE_FALSE",
            "camposSolicitados": targets,
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }

    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {
            "executado": False,
            "motivoIgnorado": "CATEGORIA_SEM_SCHEMA_TECNICO",
            "camposSolicitados": targets,
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }

    safe = normalize_hardware_payload_for_backend(category, payload or {})
    spec_field = schema[1]
    specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
    targets = [field for field in targets if not _missing(specs.get(field))]
    if not targets:
        return {
            "executado": False,
            "motivoIgnorado": "CAMPOS_SEM_VALOR_PARA_CONFIRMAR",
            "camposSolicitados": [],
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }

    identity = build_identity({"payloadParcialBackend": safe})
    if not identity_is_strong(identity):
        return {
            "executado": False,
            "motivoIgnorado": "IDENTIDADE_INSUFICIENTE",
            "camposSolicitados": targets,
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }

    origin_by_field = origin_by_field or {}
    max_fields = _int_env("TECH_RESEARCH_VERIFY_MAX_FIELDS", 3, 1, 6)
    max_sources = _int_env("TECH_RESEARCH_VERIFY_MAX_SOURCES", 2, 1, 4)
    total_timeout = _float_env("TECH_RESEARCH_VERIFY_TOTAL_TIMEOUT_SECONDS", 8.0, 2.0, 20.0)
    source_timeout = _int_env("TECH_RESEARCH_VERIFY_SOURCE_TIMEOUT_SECONDS", 3, 1, 6)
    targets = targets[:max_fields]
    sources = _source_names(category, origin_by_field, targets)[:max_sources]
    providers = build_providers(sources, category=category, missing_fields=targets)

    confirmations: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    consulted: list[dict[str, Any]] = []
    started = time.monotonic()

    for provider in providers:
        if time.monotonic() - started >= total_timeout:
            break

        provider_name = str(getattr(provider, "name", provider.__class__.__name__) or "").strip().upper()
        if hasattr(provider, "allow_browser_fallback"):
            provider.allow_browser_fallback = False
        if hasattr(provider, "timeout"):
            try:
                provider.timeout = min(int(provider.timeout), source_timeout)
            except (TypeError, ValueError):
                provider.timeout = source_timeout
        resolver = getattr(provider, "resolver", None)
        if resolver is not None:
            if hasattr(resolver, "allow_browser_fallback"):
                resolver.allow_browser_fallback = False
            if hasattr(resolver, "timeout"):
                try:
                    resolver.timeout = min(int(resolver.timeout), source_timeout)
                except (TypeError, ValueError):
                    resolver.timeout = source_timeout

        try:
            source = provider.collect(identity, category)
        except Exception as exc:
            consulted.append(
                {
                    "fonte": provider_name,
                    "ok": False,
                    "erro": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        consulted.append(
            {
                "fonte": provider_name,
                "ok": bool(source.get("ok")),
                "url": source.get("url"),
                "erro": source.get("erro"),
            }
        )
        if not source.get("ok"):
            continue

        extracted = extract_specs(
            category,
            source.get("attributes") or [],
            context_text=source.get("context_text") or "",
        )
        extracted, _issues = validate_specs(category, extracted, source.get("attributes"))
        evidence = evidence_for_specs(category, source, extracted)
        source_score = source_confidence(provider_name)

        for field in targets:
            candidate = extracted.get(field)
            current = specs.get(field)
            if _missing(candidate) or _missing(current):
                continue

            if _normalized(candidate) == _normalized(current):
                previous = confirmations.get(field)
                if previous and float(previous.get("score") or 0.0) >= source_score:
                    continue
                confirmations[field] = {
                    "campo": field,
                    "valor": current,
                    "fonte": provider_name,
                    "url": source.get("url"),
                    "score": round(source_score, 2),
                    "metodo": "CONFIRMADO_POR_FONTE_INDEPENDENTE",
                    "evidencia": evidence.get(field),
                }
                continue

            # Divergência de fonte técnica forte precisa continuar visível para revisão.
            if source_score >= 0.85:
                conflicts.append(
                    {
                        "campo": field,
                        "valorPrincipal": current,
                        "valorExterno": candidate,
                        "fonte": provider_name,
                        "url": source.get("url"),
                        "metodo": "CONFLITO_ENCONTRADO_NA_VERIFICACAO_INDEPENDENTE",
                        "evidencia": evidence.get(field),
                    }
                )

    return {
        "executado": True,
        "motivoIgnorado": None,
        "camposSolicitados": targets,
        "confirmacoes": confirmations,
        "conflitos": conflicts,
        "fontesConsultadas": consulted,
        "duracaoMs": int((time.monotonic() - started) * 1000),
        "limiteSegundos": total_timeout,
    }
