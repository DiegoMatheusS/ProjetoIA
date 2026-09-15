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
from .verification import verify_questionable_fields


def _missing(value: Any) -> bool:
    return value in (None, "", [])


def _min_essential_confidence() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_MIN_ESSENTIAL_CONFIDENCE", "0.80"))
    except (TypeError, ValueError):
        value = 0.80
    return min(0.99, max(0.50, value))


def _score(info: Any) -> float:
    if not isinstance(info, dict):
        return 0.0
    try:
        return float(info.get("score"))
    except (TypeError, ValueError):
        return 0.0


def evaluate_research_quality(
    category: str,
    *,
    original_payload: dict[str, Any],
    final_payload: dict[str, Any],
    confidence_by_field: dict[str, Any] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    registration_issues: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Audita a ficha final e, opcionalmente, tenta confirmar campos duvidosos.

    Valores que ja estavam no payload original continuam considerados confirmados.
    Para campos essenciais preenchidos automaticamente, a auditoria exige
    proveniencia/confianca minima. Quando a verificacao independente esta ativada,
    campos de baixa confianca ou sem proveniencia recebem uma ultima tentativa em
    outra fonte tecnica antes de serem enviados para revisao manual.
    """
    category = str(category or "").strip().upper()
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return {
            "status": "SEM_SCHEMA",
            "podeMarcarPronto": False,
            "motivos": ["CATEGORIA_SEM_SCHEMA_TECNICO"],
            "camposParaRevisao": [],
            "verificacaoIndependente": {
                "executado": False,
                "motivoIgnorado": "CATEGORIA_SEM_SCHEMA_TECNICO",
            },
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
    base_conflicts = [item for item in (conflicts or []) if isinstance(item, dict)]
    base_conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in base_conflicts
        if item.get("campo")
    }
    registration_issues = list(registration_issues or [])
    threshold = _min_essential_confidence()
    essentials = list((COVERAGE_WEIGHT_TIERS.get(category) or {}).get("essenciais") or [])

    # Primeiro identifica apenas os campos que podem se beneficiar de uma segunda
    # fonte. Campos ja em conflito continuam para revisao e nao gastam outra busca.
    questionable_fields: list[str] = []
    for field in essentials:
        value = final_specs.get(field)
        if _missing(value) or not _missing(original_specs.get(field)) or field in base_conflict_fields:
            continue
        field_confidence = confidence.get(field)
        if not isinstance(field_confidence, dict) or _score(field_confidence) < threshold:
            questionable_fields.append(field)

    try:
        verification = verify_questionable_fields(
            category,
            payload=final,
            fields=questionable_fields,
            origin_by_field={
                field: {
                    "fonte": (confidence.get(field) or {}).get("fonte")
                }
                for field in questionable_fields
                if isinstance(confidence.get(field), dict)
            },
        )
    except Exception as exc:
        # A verificacao e uma tentativa extra; nunca pode derrubar o Completar com IA.
        verification = {
            "executado": False,
            "motivoIgnorado": "ERRO_VERIFICACAO_INDEPENDENTE",
            "erro": f"{type(exc).__name__}: {exc}",
            "camposSolicitados": questionable_fields,
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        }

    confirmations = verification.get("confirmacoes") if isinstance(verification, dict) else {}
    confirmations = confirmations if isinstance(confirmations, dict) else {}
    verification_conflicts = verification.get("conflitos") if isinstance(verification, dict) else []
    verification_conflicts = [
        item for item in (verification_conflicts or []) if isinstance(item, dict)
    ]
    all_conflicts = base_conflicts + verification_conflicts
    conflict_fields = {
        str(item.get("campo") or "").strip()
        for item in all_conflicts
        if item.get("campo")
    }

    missing_essential: list[str] = []
    low_confidence_essential: list[dict[str, Any]] = []
    no_provenance_essential: list[str] = []
    review_fields: list[str] = []
    original_confirmed: list[str] = []
    automatically_confirmed: list[dict[str, Any]] = []

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
        confirmation = confirmations.get(field) if isinstance(confirmations.get(field), dict) else None
        base_score = _score(field_confidence)
        confirmation_score = _score(confirmation)
        effective_score = max(base_score, confirmation_score)

        if confirmation is not None and confirmation_score >= threshold:
            automatically_confirmed.append(
                {
                    "campo": field,
                    "scoreOriginal": round(base_score, 2),
                    "scoreConfirmacao": round(confirmation_score, 2),
                    "fonteConfirmacao": confirmation.get("fonte"),
                    "urlConfirmacao": confirmation.get("url"),
                }
            )

        if not isinstance(field_confidence, dict) and confirmation is None:
            no_provenance_essential.append(field)
            review_fields.append(field)
        elif effective_score < threshold:
            low_confidence_essential.append(
                {
                    "campo": field,
                    "score": round(effective_score, 2),
                    "fonte": (
                        confirmation.get("fonte")
                        if confirmation_score >= base_score and confirmation is not None
                        else (field_confidence or {}).get("fonte")
                    ),
                    "limiar": round(threshold, 2),
                    "confirmacaoIndependente": bool(confirmation),
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
        "camposConfirmadosAutomaticamente": automatically_confirmed,
        "conflitosNaoResolvidos": all_conflicts,
        "problemasPayload": registration_issues,
        "verificacaoIndependente": verification,
    }
