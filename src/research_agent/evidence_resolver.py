from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .confidence import source_confidence


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def resolve_cache_conflicts(
    category: str,
    *,
    original_payload: dict[str, Any],
    researched_payload: dict[str, Any],
    info: dict[str, Any],
    cached_fields: list[str] | tuple[str, ...] | set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Permite que evidencia nova mais forte corrija somente valores vindos do cache.

    Regras de seguranca:
    - nunca altera um campo que ja existia no payload recebido do frontend;
    - nunca usa um conflito sem valor externo concreto;
    - so troca o valor do cache quando a fonte atual tem confianca maior;
    - conflitos que nao podem ser resolvidos continuam marcados para revisao.
    """
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return researched_payload, info

    spec_field = schema[1]
    safe_original = normalize_hardware_payload_for_backend(category, original_payload or {})
    safe_after = normalize_hardware_payload_for_backend(category, researched_payload or {})
    original_specs = safe_original.get(spec_field) if isinstance(safe_original.get(spec_field), dict) else {}
    specs = deepcopy(safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {})

    cached = {str(field) for field in (cached_fields or []) if field}
    out = deepcopy(info or {})
    origins = deepcopy(out.get("origemPorCampo") or {})
    unresolved: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = list(out.get("conflitosResolvidos") or [])
    replaced: list[str] = []

    for conflict in out.get("conflitos") or []:
        if not isinstance(conflict, dict):
            continue
        field = str(conflict.get("campo") or "").strip()
        external_value = conflict.get("valorExterno")
        external_source = str(conflict.get("fonte") or "").strip().upper()

        # Valor que veio do usuario/descoberta original sempre vence automaticamente.
        if (
            not field
            or field not in cached
            or not _missing(original_specs.get(field))
            or _missing(external_value)
        ):
            unresolved.append(conflict)
            continue

        current_origin = origins.get(field) if isinstance(origins.get(field), dict) else {}
        current_source = str(current_origin.get("fonte") or "").strip().upper()
        current_score = source_confidence(current_source)
        external_score = source_confidence(external_source)

        if external_score <= current_score:
            unresolved.append(conflict)
            continue

        previous_value = specs.get(field)
        specs[field] = external_value
        origins[field] = {
            "fonte": external_source or None,
            "url": conflict.get("url"),
            "metodo": "CONFLITO_CACHE_RESOLVIDO_POR_FONTE_MAIS_FORTE",
            "confiancaAnterior": round(current_score, 2),
            "confiancaNova": round(external_score, 2),
        }
        replaced.append(field)
        resolved.append(
            {
                **conflict,
                "valorSubstituido": previous_value,
                "valorEscolhido": external_value,
                "fonteAnterior": current_source or None,
                "fonteEscolhida": external_source or None,
                "motivoResolucao": "FONTE_ATUAL_MAIS_CONFIAVEL_QUE_CACHE",
            }
        )

    safe_after[spec_field] = specs
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    out["origemPorCampo"] = origins
    out["conflitos"] = unresolved
    out["conflitosResolvidos"] = resolved
    out["camposCacheSubstituidosPorEvidenciaAtual"] = list(dict.fromkeys(replaced))
    return safe_after, out
