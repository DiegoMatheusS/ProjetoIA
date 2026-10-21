from __future__ import annotations

import os
from typing import Any

from ..enrichment.identity import build_identity, identity_is_strong
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..utils.rate_limiter import JsonDiskCache


# V9: namespace novo para impedir que caches antigos, gravados antes das regras de
# confianca/proveniencia, sejam reutilizados silenciosamente.
_CACHE_NAMESPACE = "technical-research-agent-v2"


def _enabled() -> bool:
    return os.getenv("TECH_RESEARCH_CACHE_ENABLED", "true").strip().casefold() in {
        "1", "true", "sim", "yes", "on"
    }


def _ttl_seconds() -> int:
    try:
        value = int(os.getenv("TECH_RESEARCH_CACHE_TTL_SECONDS", "86400"))
    except (TypeError, ValueError):
        value = 86400
    return min(7 * 86400, max(300, value))


def _min_confidence() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_CACHE_MIN_CONFIDENCE", "0.80"))
    except (TypeError, ValueError):
        value = 0.80
    return min(0.99, max(0.50, value))


def _require_provenance() -> bool:
    return os.getenv("TECH_RESEARCH_CACHE_REQUIRE_PROVENANCE", "true").strip().casefold() in {
        "1", "true", "sim", "yes", "on"
    }


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _score(info: Any) -> float:
    if not isinstance(info, dict):
        return 0.0
    try:
        return float(info.get("score"))
    except (TypeError, ValueError):
        return 0.0


def _identity_for(category: str, payload: dict[str, Any]) -> dict[str, Any]:
    return build_identity({
        "categoriaDetectada": category,
        "payloadParcialBackend": payload,
    })


def _cache_url(category: str, identity: dict[str, Any]) -> str | None:
    if not identity_is_strong(identity):
        return None
    key = str(identity.get("chave") or "").strip()
    if not key:
        return None
    return f"research://{category}/{key}"


def filter_cached_entry_for_reuse(category: str, cached: dict[str, Any]) -> dict[str, Any]:
    """Mantem no cache reutilizavel somente campos com evidencia suficiente.

    Regras V9:
    - conflito nao resolvido nunca volta como verdade pelo cache;
    - sem proveniencia/confianca o campo nao e reutilizado por padrao;
    - score abaixo do limiar fica como lacuna para nova pesquisa;
    - a filtragem nunca altera o valor recebido do frontend, pois o merge posterior
      continua aplicando cache apenas em campos vazios.
    """
    if not isinstance(cached, dict) or not isinstance(cached.get("payload"), dict):
        return cached if isinstance(cached, dict) else {}

    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return cached

    spec_field = schema[1]
    safe = normalize_hardware_payload_for_backend(category, cached.get("payload") or {})
    specs = safe.get(spec_field) if isinstance(safe.get(spec_field), dict) else {}
    origins = cached.get("origemPorCampo") if isinstance(cached.get("origemPorCampo"), dict) else {}
    confidence = cached.get("confiancaPorCampo") if isinstance(cached.get("confiancaPorCampo"), dict) else {}
    conflicts = [
        item for item in (cached.get("conflitos") or cached.get("conflitosNaoResolvidos") or [])
        if isinstance(item, dict)
    ]
    conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in conflicts
        if item.get("campo")
    }

    threshold = _min_confidence()
    require_provenance = _require_provenance()
    reusable_specs: dict[str, Any] = {}
    reusable_origins: dict[str, Any] = {}
    reusable_confidence: dict[str, Any] = {}
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []

    for field in schema[2] or []:
        value = specs.get(field)
        if _missing(value):
            continue

        field_confidence = confidence.get(field)
        field_origin = origins.get(field)
        score = _score(field_confidence)
        source = ""
        if isinstance(field_confidence, dict):
            source = str(field_confidence.get("fonte") or "").strip()
        if not source and isinstance(field_origin, dict):
            source = str(field_origin.get("fonte") or "").strip()

        reason = None
        if field in conflict_fields or (isinstance(field_confidence, dict) and field_confidence.get("comConflito")):
            reason = "CONFLITO_NAO_RESOLVIDO"
        elif require_provenance and (not isinstance(field_confidence, dict) or not source):
            reason = "SEM_PROVENIENCIA"
        elif score < threshold:
            reason = "CONFIANCA_ABAIXO_DO_LIMIAR"

        if reason:
            rejected.append(
                {
                    "campo": field,
                    "motivo": reason,
                    "score": round(score, 2),
                    "fonte": source or None,
                }
            )
            continue

        reusable_specs[field] = value
        if isinstance(field_origin, dict):
            reusable_origins[field] = field_origin
        if isinstance(field_confidence, dict):
            reusable_confidence[field] = field_confidence
        accepted.append(field)

    safe[spec_field] = reusable_specs
    safe = normalize_hardware_payload_for_backend(category, safe)
    out = dict(cached)
    out["payload"] = safe
    out["origemPorCampo"] = reusable_origins
    out["confiancaPorCampo"] = reusable_confidence
    out["cacheQualidade"] = {
        "versao": 2,
        "limiarConfianca": round(threshold, 2),
        "exigeProveniencia": require_provenance,
        "camposReutilizaveis": accepted,
        "camposIgnorados": rejected,
    }
    return out


def merge_cached_gaps(category: str, current: dict[str, Any], cached: dict[str, Any]) -> dict[str, Any]:
    """Aplica cache somente em lacunas; nunca substitui valor ja presente."""
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return normalize_hardware_payload_for_backend(category, current or {})
    spec_field = schema[1]
    safe_current = normalize_hardware_payload_for_backend(category, current or {})
    safe_cached = normalize_hardware_payload_for_backend(category, cached or {})
    current_specs = dict(safe_current.get(spec_field) or {})
    cached_specs = dict(safe_cached.get(spec_field) or {})
    for field in schema[2] or []:
        if _missing(current_specs.get(field)) and not _missing(cached_specs.get(field)):
            current_specs[field] = cached_specs[field]
    safe_current[spec_field] = current_specs
    return normalize_hardware_payload_for_backend(category, safe_current)


class ResearchCache:
    def __init__(self, cache: JsonDiskCache | None = None):
        self.cache = cache or JsonDiskCache()
        self.enabled = _enabled()

    def get(self, category: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        safe = normalize_hardware_payload_for_backend(category, payload or {})
        identity = _identity_for(category, safe)
        url = _cache_url(category, identity)
        if not url:
            return None
        cached = self.cache.get(
            url,
            params={"identity": identity.get("chave")},
            namespace=_CACHE_NAMESPACE,
            ttl_seconds=_ttl_seconds(),
        )
        if not isinstance(cached, dict):
            return None
        return filter_cached_entry_for_reuse(category, cached)

    def set(self, category: str, payload: dict[str, Any], info: dict[str, Any]) -> None:
        if not self.enabled:
            return
        safe = normalize_hardware_payload_for_backend(category, payload or {})
        identity = _identity_for(category, safe)
        url = _cache_url(category, identity)
        if not url:
            return
        self.cache.set(
            url,
            {
                "payload": safe,
                "origemPorCampo": info.get("origemPorCampo") or {},
                "confiancaPorCampo": info.get("confiancaPorCampo") or {},
                "conflitos": info.get("conflitos") or [],
            },
            params={"identity": identity.get("chave")},
            namespace=_CACHE_NAMESPACE,
        )
