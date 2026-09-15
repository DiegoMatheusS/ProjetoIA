from __future__ import annotations

import os
from typing import Any

from ..enrichment.core import (
    COVERAGE_WEIGHT_TIERS,
    required_missing_fields,
    technical_coverage,
    technical_missing_fields,
)
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _min_essential_confidence() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_MIN_ESSENTIAL_CONFIDENCE", "0.80"))
    except (TypeError, ValueError):
        value = 0.80
    return min(0.99, max(0.50, value))


def evaluate_research_quality(
    category: str,
    *,
    original_payload: dict[str, Any],
    final_payload: dict[str, Any],
    confidence_by_field: dict[str, Any] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    registration_issues: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Audita a ficha final sem bloquear o fluxo de cadastro.

    A regra principal e conservadora: valores que ja estavam no payload original
    sao tratados como previamente confirmados pelo fluxo atual. Para campos
    essenciais preenchidos automaticamente, exige proveniencia/confiança minima.
    Assim uma ficha completa apenas por fonte fraca ou por OpenAI sem web search
    nao vira PRONTO silenciosamente.
    """
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {
            "status": "SEM_SCHEMA",
            "podeMarcarPronto": False,
            "motivos": ["CATEGORIA_SEM_SCHEMA_TECNICO"],
            "camposParaRevisao": [],
        }

    spec_field = schema[1]
    original = normalize_hardware_payload_for_backend(category, original_payload or {})
    final = normalize_hardware_payload_for_backend(category, final_payload or {})
    original_specs = original.get(spec_field) if isinstance(original.get(spec_field), dict) else {}
    final_specs = final.get(spec_field) if isinstance(final.get(spec_field), dict) else {}
    state = {
        "categoriaDetectada": category,
        "especificacoesEncontradas": final_specs,
    }

    confidence = confidence_by_field or {}
    conflicts = [item for item in (conflicts or []) if isinstance(item, dict)]
    conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in conflicts
        if item.get("campo")
    }
    registration_issues = list(registration_issues or [])
    threshold = _min_essential_confidence()
    essentials = list((COVERAGE_WEIGHT_TIERS.get(category) or {}).get("essenciais") or [])

    missing_essential: list[str] = []
    low_confidence_essential: list[dict[str, Any]] = []
    no_provenance_essential: list[str] = []
    review_fields: list[str] = []
    original_confirmed: list[str] = []

    for field in essentials:
        value = final_specs.get(field)
        if _missing(value):
            missing_essential.append(field)
            review_fields.append(field)
            continue

        # Dado que ja existia antes do agente nao depende da proveniencia da pesquisa.
        if not _missing(original_specs.get(field)):
            original_confirmed.append(field)
            if field in conflict_fields:
                review_fields.append(field)
            continue

        field_confidence = confidence.get(field)
        if not isinstance(field_confidence, dict):
            no_provenance_essential.append(field)
            review_fields.append(field)
            continue

        try:
            score = float(field_confidence.get("score"))
        except (TypeError, ValueError):
            score = 0.0
        if score < threshold:
            low_confidence_essential.append(
                {
                    "campo": field,
                    "score": round(score, 2),
                    "fonte": field_confidence.get("fonte"),
                    "limiar": round(threshold, 2),
                }
            )
            review_fields.append(field)
        if field in conflict_fields:
            review_fields.append(field)

    missing_required = required_missing_fields(state)
    missing_all = technical_missing_fields(state)
    coverage = technical_coverage(state)

    reasons: list[str] = []
    if registration_issues:
        reasons.append("PAYLOAD_INVALIDO_PARA_CADASTRO")
    if missing_required:
        reasons.append("CAMPOS_OBRIGATORIOS_AUSENTES")
    if missing_essential:
        reasons.append("CAMPOS_ESSENCIAIS_AUSENTES")
    if no_provenance_essential:
        reasons.append("CAMPOS_ESSENCIAIS_SEM_PROVENIENCIA")
    if low_confidence_essential:
        reasons.append("CAMPOS_ESSENCIAIS_COM_CONFIANCA_BAIXA")
    if conflict_fields:
        reasons.append("CONFLITOS_NAO_RESOLVIDOS")
    if coverage < 0.80:
        reasons.append("COBERTURA_TECNICA_INSUFICIENTE")

    if registration_issues or missing_required:
        status = "BLOQUEADO_POR_PAYLOAD"
    elif reasons:
        status = "PRECISA_REVISAO"
    else:
        status = "APROVADO"

    return {
        "status": status,
        "podeMarcarPronto": status == "APROVADO",
        "limiarConfiancaEssencial": round(threshold, 2),
        "coberturaTecnica": round(coverage, 4),
        "motivos": reasons,
        "camposParaRevisao": list(dict.fromkeys(review_fields)),
        "camposEssenciaisAusentes": missing_essential,
        "camposObrigatoriosAusentes": missing_required,
        "camposAusentes": missing_all,
        "camposEssenciaisSemProveniencia": no_provenance_essential,
        "camposEssenciaisBaixaConfianca": low_confidence_essential,
        "camposOriginaisConsideradosConfirmados": original_confirmed,
        "conflitosNaoResolvidos": conflicts,
        "problemasPayload": registration_issues,
    }
