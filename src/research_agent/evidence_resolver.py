from __future__ import annotations

from copy import deepcopy
import json
import os
from typing import Any

from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .confidence import source_confidence


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _live_resolution_enabled() -> bool:
    return os.getenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "true").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


def _consensus_min_sources() -> int:
    try:
        value = int(os.getenv("TECH_RESEARCH_CONSENSUS_MIN_SOURCES", "2"))
    except (TypeError, ValueError):
        value = 2
    return min(4, max(2, value))


def _consensus_min_delta() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_CONSENSUS_MIN_DELTA", "0.08"))
    except (TypeError, ValueError):
        value = 0.08
    return min(0.50, max(0.02, value))


def _value_key(value: Any) -> str:
    """Normaliza somente para comparar consenso; nunca altera o valor persistido."""
    if isinstance(value, str):
        normalized = " ".join(value.split()).casefold()
        return f"str:{normalized}"
    if isinstance(value, list):
        normalized = sorted(_value_key(item) for item in value)
        return "list:" + json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    if isinstance(value, dict):
        normalized = {str(key): _value_key(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
        return "dict:" + json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return f"scalar:{value!r}"


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


def resolve_live_research_conflicts(
    category: str,
    *,
    original_payload: dict[str, Any],
    researched_payload: dict[str, Any],
    info: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve conflitos da pesquisa atual sem tocar em valores originais.

    O enriquecedor historicamente usa o primeiro valor encontrado e transforma os
    valores seguintes em conflitos. Esta etapa compara todas as alegacoes do campo
    antes de aceitar esse primeiro valor como vencedor.

    Um conflito so e resolvido automaticamente quando:
    - pelo menos duas fontes independentes apoiam o mesmo valor e ele domina as
      alternativas; ou
    - uma fonte claramente mais confiavel domina a fonte que sustentava o valor
      atual por uma margem configuravel.

    Campos que ja existiam no payload recebido do frontend nunca sao alterados.
    Quando nao existe vencedor claro, o conflito permanece para a auditoria/revisao.
    """
    out = deepcopy(info or {})
    if not _live_resolution_enabled():
        out["resolucaoConflitosPesquisa"] = {
            "executado": False,
            "motivoIgnorado": "TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS_FALSE",
            "camposResolvidos": [],
            "camposSubstituidos": [],
        }
        return researched_payload, out

    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        out["resolucaoConflitosPesquisa"] = {
            "executado": False,
            "motivoIgnorado": "CATEGORIA_SEM_SCHEMA_TECNICO",
            "camposResolvidos": [],
            "camposSubstituidos": [],
        }
        return researched_payload, out

    spec_field = schema[1]
    safe_original = normalize_hardware_payload_for_backend(category, original_payload or {})
    safe_after = normalize_hardware_payload_for_backend(category, researched_payload or {})
    original_specs = safe_original.get(spec_field) if isinstance(safe_original.get(spec_field), dict) else {}
    specs = deepcopy(safe_after.get(spec_field) if isinstance(safe_after.get(spec_field), dict) else {})
    origins = deepcopy(out.get("origemPorCampo") or {})
    conflicts = [item for item in (out.get("conflitos") or []) if isinstance(item, dict)]

    by_field: dict[str, list[dict[str, Any]]] = {}
    untouched: list[dict[str, Any]] = []
    for conflict in conflicts:
        field = str(conflict.get("campo") or "").strip()
        if not field:
            untouched.append(conflict)
            continue
        by_field.setdefault(field, []).append(conflict)

    min_sources = _consensus_min_sources()
    min_delta = _consensus_min_delta()
    resolved_records = list(out.get("conflitosResolvidos") or [])
    resolved_live = list(out.get("conflitosResolvidosPesquisaAtual") or [])
    replaced_fields: list[str] = []
    resolved_fields: list[str] = []
    unresolved: list[dict[str, Any]] = list(untouched)

    for field, field_conflicts in by_field.items():
        current_value = specs.get(field)
        # Qualquer valor original e imutavel nesta etapa.
        if _missing(current_value) or not _missing(original_specs.get(field)):
            unresolved.extend(field_conflicts)
            continue

        current_origin = origins.get(field) if isinstance(origins.get(field), dict) else {}
        current_source = str(current_origin.get("fonte") or "").strip().upper()
        candidates: dict[str, dict[str, Any]] = {}

        def add_candidate(value: Any, source: str | None, url: str | None, *, is_current: bool = False) -> None:
            if _missing(value):
                return
            key = _value_key(value)
            candidate = candidates.setdefault(
                key,
                {
                    "valor": value,
                    "fontes": {},
                    "urls": [],
                    "incluiAtual": False,
                },
            )
            source_name = str(source or "").strip().upper() or "DESCONHECIDA"
            candidate["fontes"][source_name] = max(
                float(candidate["fontes"].get(source_name, 0.0)),
                source_confidence(source_name),
            )
            if url and url not in candidate["urls"]:
                candidate["urls"].append(url)
            candidate["incluiAtual"] = bool(candidate["incluiAtual"] or is_current)

        add_candidate(
            current_value,
            current_source,
            current_origin.get("url") if isinstance(current_origin, dict) else None,
            is_current=True,
        )
        for conflict in field_conflicts:
            add_candidate(
                conflict.get("valorExterno"),
                conflict.get("fonte"),
                conflict.get("url"),
            )

        ranked: list[dict[str, Any]] = []
        for candidate in candidates.values():
            scores = list(candidate["fontes"].values())
            ranked.append(
                {
                    **candidate,
                    "apoios": len(candidate["fontes"]),
                    "scoreTotal": round(sum(scores), 4),
                    "scoreMaximo": round(max(scores) if scores else 0.0, 4),
                }
            )
        ranked.sort(
            key=lambda item: (item["scoreTotal"], item["apoios"], item["scoreMaximo"]),
            reverse=True,
        )
        if not ranked:
            unresolved.extend(field_conflicts)
            continue

        winner = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        runner_total = float(runner_up["scoreTotal"]) if runner_up else 0.0
        runner_max = float(runner_up["scoreMaximo"]) if runner_up else 0.0
        winner_total = float(winner["scoreTotal"])
        winner_max = float(winner["scoreMaximo"])

        consensus_win = (
            int(winner["apoios"]) >= min_sources
            and winner_total >= runner_total + min_delta
        )
        strong_source_win = (
            winner_max >= 0.85
            and winner_max >= runner_max + min_delta
        )

        if not (consensus_win or strong_source_win):
            unresolved.extend(field_conflicts)
            continue

        previous_value = current_value
        chosen_value = winner["valor"]
        chosen_sources = sorted(
            winner["fontes"],
            key=lambda source: winner["fontes"][source],
            reverse=True,
        )
        primary_source = chosen_sources[0] if chosen_sources else None
        changed = _value_key(previous_value) != _value_key(chosen_value)
        if changed:
            specs[field] = chosen_value
            replaced_fields.append(field)

        origins[field] = {
            "fonte": primary_source,
            "fontes": chosen_sources,
            "urls": list(winner["urls"]),
            "url": winner["urls"][0] if winner["urls"] else None,
            "metodo": "CONSENSO_MULTIFONTE" if consensus_win else "FONTE_MAIS_FORTE_PESQUISA_ATUAL",
            "apoiosIndependentes": int(winner["apoios"]),
            "scoreAgregado": round(winner_total, 2),
        }
        resolved_fields.append(field)
        record = {
            "campo": field,
            "valorAnterior": previous_value,
            "valorEscolhido": chosen_value,
            "alterouValor": changed,
            "fontesEscolhidas": chosen_sources,
            "apoiosIndependentes": int(winner["apoios"]),
            "scoreAgregadoVencedor": round(winner_total, 2),
            "scoreAgregadoSegundo": round(runner_total, 2),
            "motivoResolucao": (
                "CONSENSO_MULTIFONTE"
                if consensus_win
                else "FONTE_CLARAMENTE_MAIS_CONFIAVEL"
            ),
        }
        resolved_live.append(record)
        resolved_records.append(record)

    safe_after[spec_field] = specs
    safe_after = normalize_hardware_payload_for_backend(category, safe_after)
    out["origemPorCampo"] = origins
    out["conflitos"] = unresolved
    out["conflitosResolvidos"] = resolved_records
    out["conflitosResolvidosPesquisaAtual"] = resolved_live
    out["camposSubstituidosPorConsenso"] = list(dict.fromkeys(replaced_fields))
    out["resolucaoConflitosPesquisa"] = {
        "executado": bool(by_field),
        "camposAnalisados": sorted(by_field),
        "camposResolvidos": list(dict.fromkeys(resolved_fields)),
        "camposSubstituidos": list(dict.fromkeys(replaced_fields)),
        "conflitosRestantes": len(unresolved),
        "minimoFontesConsenso": min_sources,
        "margemMinima": round(min_delta, 2),
    }
    return safe_after, out
