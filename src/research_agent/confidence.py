from __future__ import annotations

from copy import deepcopy
import os
from typing import Any


SOURCE_CONFIDENCE = {
    "FABRICANTE_OFICIAL": 0.98,
    "ICECAT": 0.94,
    "TECHPOWERUP": 0.93,
    "CPU_MONKEY": 0.91,
    "CPU_WORLD": 0.90,
    "WIKICHIP": 0.88,
    "GEIZHALS": 0.86,
    "PC_KOMBO": 0.78,
    "OPENAI_WEB_SEARCH": 0.80,
    "OPENAI": 0.72,
}


def _require_field_evidence_for_web_confidence() -> bool:
    return os.getenv(
        "TECH_RESEARCH_REQUIRE_FIELD_EVIDENCE_FOR_WEB_CONFIDENCE",
        "true",
    ).strip().casefold() in {"1", "true", "sim", "yes", "on"}


def source_confidence(source: str | None) -> float:
    return SOURCE_CONFIDENCE.get(str(source or "").strip().upper(), 0.65)


def annotate_field_confidence(info: dict[str, Any]) -> dict[str, Any]:
    """Anota confiança por campo sem inventar nem substituir valores confirmados.

    V12: ter URLs de Web Search na mesma rodada não prova, por si só, que cada valor
    veio dessas páginas. Quando a evidência específica por campo é exigida, um valor
    apenas associado à rodada da busca recebe confiança conservadora até ser confirmado
    por uma fonte independente ou por extração determinística de uma página oficial.
    """
    out = deepcopy(info or {})
    origins = out.get("origemPorCampo") or {}
    conflicts = out.get("conflitos") or []
    conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in conflicts
        if isinstance(item, dict) and item.get("campo")
    }

    confidence_by_field: dict[str, dict[str, Any]] = {}
    require_field_evidence = _require_field_evidence_for_web_confidence()
    for field, origin in origins.items():
        if not isinstance(origin, dict):
            continue
        source = str(origin.get("fonte") or "").strip().upper()
        score = source_confidence(source)
        evidence_confirmed = bool(origin.get("evidenciaCampoConfirmada"))

        # OPENAI_WEB_SEARCH significa que a rodada usou busca web. Sem uma evidência
        # vinculada ao campo, o valor continua útil, mas não deve ganhar confiança de
        # confirmação documental automaticamente.
        if (
            source == "OPENAI_WEB_SEARCH"
            and require_field_evidence
            and not evidence_confirmed
        ):
            score = min(score, 0.74)

        if field in conflict_fields:
            score = max(0.40, score - 0.12)
        confidence_by_field[field] = {
            "nivel": "MUITO_ALTA" if score >= 0.95 else "ALTA" if score >= 0.85 else "MEDIA" if score >= 0.70 else "BAIXA",
            "score": round(score, 2),
            "fonte": source or None,
            "url": origin.get("url"),
            "comConflito": field in conflict_fields,
            "evidenciaCampoConfirmada": evidence_confirmed,
            "metodo": origin.get("metodo"),
        }

    out["confiancaPorCampo"] = confidence_by_field
    out["conflitosNaoResolvidos"] = [
        item for item in conflicts if isinstance(item, dict)
    ]
    if confidence_by_field:
        average = sum(item["score"] for item in confidence_by_field.values()) / len(confidence_by_field)
        out["confiancaMediaPesquisa"] = round(average, 2)
    else:
        out["confiancaMediaPesquisa"] = None
    return out
