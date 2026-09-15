from __future__ import annotations

from copy import deepcopy
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


def source_confidence(source: str | None) -> float:
    return SOURCE_CONFIDENCE.get(str(source or "").strip().upper(), 0.65)


def annotate_field_confidence(info: dict[str, Any]) -> dict[str, Any]:
    """Anota confiança por campo sem inventar nem substituir valores confirmados."""
    out = deepcopy(info or {})
    origins = out.get("origemPorCampo") or {}
    conflicts = out.get("conflitos") or []
    conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in conflicts
        if isinstance(item, dict) and item.get("campo")
    }

    confidence_by_field: dict[str, dict[str, Any]] = {}
    for field, origin in origins.items():
        if not isinstance(origin, dict):
            continue
        source = str(origin.get("fonte") or "").strip().upper()
        score = source_confidence(source)
        if field in conflict_fields:
            score = max(0.40, score - 0.12)
        confidence_by_field[field] = {
            "nivel": "MUITO_ALTA" if score >= 0.95 else "ALTA" if score >= 0.85 else "MEDIA" if score >= 0.70 else "BAIXA",
            "score": round(score, 2),
            "fonte": source or None,
            "url": origin.get("url"),
            "comConflito": field in conflict_fields,
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
