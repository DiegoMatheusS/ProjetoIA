from src.research_agent.quality_gate import evaluate_research_quality


def _cpu_payload(*, with_pcie=True):
    specs = {
        "socket": "AM4",
        "nucleos": 6,
        "threads": 12,
        "frequenciaBaseMhz": 3600,
        "frequenciaTurboMhz": 4200,
        "tdpWatts": 65,
        "cacheL3Mb": 32,
        "tiposMemoriaSuportados": ["DDR4"],
    }
    if with_pcie:
        specs["versaoPcie"] = "4.0"
    return {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 5 3600",
        "marca": "AMD",
        "modelo": "Ryzen 5 3600",
        "especificacaoProcessador": specs,
    }


def _ignore_coverage_noise(monkeypatch):
    monkeypatch.setattr(
        "src.research_agent.quality_gate.technical_coverage",
        lambda _state: 0.95,
    )
    monkeypatch.setattr(
        "src.research_agent.quality_gate.technical_missing_fields",
        lambda _state: [],
    )
    monkeypatch.setattr(
        "src.research_agent.quality_gate.required_missing_fields",
        lambda _state: [],
    )


def test_essential_field_from_openai_without_web_requires_review(monkeypatch):
    _ignore_coverage_noise(monkeypatch)
    original = _cpu_payload(with_pcie=False)
    final = _cpu_payload(with_pcie=True)

    audit = evaluate_research_quality(
        "PROCESSADOR",
        original_payload=original,
        final_payload=final,
        confidence_by_field={
            "versaoPcie": {
                "score": 0.72,
                "fonte": "OPENAI",
            }
        },
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert audit["podeMarcarPronto"] is False
    assert "versaoPcie" in audit["camposParaRevisao"]
    assert "CAMPOS_ESSENCIAIS_COM_CONFIANCA_BAIXA" in audit["motivos"]


def test_essential_field_with_web_search_at_threshold_can_pass(monkeypatch):
    _ignore_coverage_noise(monkeypatch)
    monkeypatch.setenv("TECH_RESEARCH_MIN_ESSENTIAL_CONFIDENCE", "0.80")
    original = _cpu_payload(with_pcie=False)
    final = _cpu_payload(with_pcie=True)

    audit = evaluate_research_quality(
        "PROCESSADOR",
        original_payload=original,
        final_payload=final,
        confidence_by_field={
            "versaoPcie": {
                "score": 0.80,
                "fonte": "OPENAI_WEB_SEARCH",
            }
        },
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "APROVADO"
    assert audit["podeMarcarPronto"] is True
    assert audit["camposParaRevisao"] == []


def test_original_values_do_not_require_research_provenance(monkeypatch):
    _ignore_coverage_noise(monkeypatch)
    original = _cpu_payload(with_pcie=True)

    audit = evaluate_research_quality(
        "PROCESSADOR",
        original_payload=original,
        final_payload=original,
        confidence_by_field={},
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "APROVADO"
    assert "versaoPcie" in audit["camposOriginaisConsideradosConfirmados"]
    assert not audit["camposEssenciaisSemProveniencia"]


def test_unresolved_conflict_forces_review_even_for_original_field(monkeypatch):
    _ignore_coverage_noise(monkeypatch)
    original = _cpu_payload(with_pcie=True)

    audit = evaluate_research_quality(
        "PROCESSADOR",
        original_payload=original,
        final_payload=original,
        confidence_by_field={},
        conflicts=[
            {
                "campo": "versaoPcie",
                "valorPrincipal": "4.0",
                "valorExterno": "3.0",
                "fonte": "CPU_WORLD",
            }
        ],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert "versaoPcie" in audit["camposParaRevisao"]
    assert "CONFLITOS_NAO_RESOLVIDOS" in audit["motivos"]


def test_registration_problem_blocks_quality_gate(monkeypatch):
    _ignore_coverage_noise(monkeypatch)
    original = _cpu_payload(with_pcie=True)

    audit = evaluate_research_quality(
        "PROCESSADOR",
        original_payload=original,
        final_payload=original,
        confidence_by_field={},
        conflicts=[],
        registration_issues=["payload invalido"],
    )

    assert audit["status"] == "BLOQUEADO_POR_PAYLOAD"
    assert audit["podeMarcarPronto"] is False
    assert "PAYLOAD_INVALIDO_PARA_CADASTRO" in audit["motivos"]
