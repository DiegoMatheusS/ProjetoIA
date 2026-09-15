from __future__ import annotations

import os
from typing import Any

from ..enrichment.identity import build_identity, identity_is_strong
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from ..utils.rate_limiter import JsonDiskCache


_CACHE_NAMESPACE = "technical-research-agent-v1"


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


def _missing(value: Any) -> bool:
    return value in (None, "", [])


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


def merge_cached_gaps(category: str, current: dict[str, Any], cached: dict[str, Any]) -> dict[str, Any]:
    """Aplica cache somente em lacunas; nunca substitui valor já presente."""
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
        return cached if isinstance(cached, dict) else None

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
            },
            params={"identity": identity.get("chave")},
            namespace=_CACHE_NAMESPACE,
        )
