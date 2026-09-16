from src.research_agent.quality_gate import evaluate_research_quality
from src.research_agent.verification import verify_questionable_fields


def _motherboard_payload(chipset=None):
    specs = {"socket": "AM4"}
    if chipset is not None:
        specs["chipset"] = chipset
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": specs,
    }


def _simplify_quality_gate(monkeypatch):
    module = __import__("src.research_agent.quality_gate", fromlist=["COVERAGE_WEIGHT_TIERS"])
    monkeypatch.setitem(
        module.COVERAGE_WEIGHT_TIERS,
        "PLACA_MAE",
        {"essenciais": ["chipset"]},
    )
    monkeypatch.setattr("src.research_agent.quality_gate.technical_coverage", lambda _state: 1.0)
    monkeypatch.setattr("src.research_agent.quality_gate.technical_missing_fields", lambda _state: [])
    monkeypatch.setattr("src.research_agent.quality_gate.required_missing_fields", lambda _state: [])


def test_third_independent_source_can_close_automatic_conflict(monkeypatch):
    _simplify_quality_gate(monkeypatch)
    captured = {}

    def fake_verify(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "executado": True,
            "motivoIgnorado": None,
            "camposSolicitados": ["chipset"],
            "confirmacoes": {
                "chipset": {
                    "campo": "chipset",
                    "valor": "B550",
                    "fonte": "FABRICANTE_OFICIAL",
                    "url": "https://example.com/msi",
                    "score": 0.98,
                }
            },
            "conflitos": [],
            "fontesConsultadas": [{"fonte": "FABRICANTE_OFICIAL", "ok": True}],
        }

    monkeypatch.setattr("src.research_agent.quality_gate.verify_questionable_fields", fake_verify)

    audit = evaluate_research_quality(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        final_payload=_motherboard_payload("B550"),
        confidence_by_field={"chipset": {"fonte": "PC_KOMBO", "score": 0.82}},
        conflicts=[
            {
                "campo": "chipset",
                "valorPrincipal": "B550",
                "valorExterno": "X570",
                "fonte": "GEIZHALS",
            }
        ],
        registration_issues=[],
    )

    assert audit["status"] == "APROVADO"
    assert audit["conflitosNaoResolvidos"] == []
    assert audit["camposParaRevisao"] == []
    assert audit["conflitosResolvidosPorVerificacao"][0]["campo"] == "chipset"
    assert captured["excluded_sources_by_field"]["chipset"] == ["PC_KOMBO", "GEIZHALS"]


def test_conflict_on_original_value_is_never_auto_closed(monkeypatch):
    _simplify_quality_gate(monkeypatch)
    monkeypatch.setattr(
        "src.research_agent.quality_gate.verify_questionable_fields",
        lambda *_args, **_kwargs: {
            "executado": False,
            "motivoIgnorado": "SEM_CAMPOS_PARA_VERIFICAR",
            "camposSolicitados": [],
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        },
    )

    audit = evaluate_research_quality(
        "PLACA_MAE",
        original_payload=_motherboard_payload("B550"),
        final_payload=_motherboard_payload("B550"),
        confidence_by_field={},
        conflicts=[
            {
                "campo": "chipset",
                "valorPrincipal": "B550",
                "valorExterno": "X570",
                "fonte": "GEIZHALS",
            }
        ],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert "CONFLITOS_NAO_RESOLVIDOS" in audit["motivos"]
    assert audit["conflitosResolvidosPorVerificacao"] == []
    assert audit["conflitosNaoResolvidos"][0]["campo"] == "chipset"


def test_third_source_disagreement_keeps_conflict_visible(monkeypatch):
    _simplify_quality_gate(monkeypatch)
    monkeypatch.setattr(
        "src.research_agent.quality_gate.verify_questionable_fields",
        lambda *_args, **_kwargs: {
            "executado": True,
            "motivoIgnorado": None,
            "camposSolicitados": ["chipset"],
            "confirmacoes": {},
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B550",
                    "valorExterno": "B450",
                    "fonte": "FABRICANTE_OFICIAL",
                }
            ],
            "fontesConsultadas": [{"fonte": "FABRICANTE_OFICIAL", "ok": True}],
        },
    )

    audit = evaluate_research_quality(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        final_payload=_motherboard_payload("B550"),
        confidence_by_field={"chipset": {"fonte": "PC_KOMBO", "score": 0.82}},
        conflicts=[
            {
                "campo": "chipset",
                "valorPrincipal": "B550",
                "valorExterno": "X570",
                "fonte": "GEIZHALS",
            }
        ],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert "chipset" in audit["camposParaRevisao"]
    assert len(audit["conflitosNaoResolvidos"]) == 2


def test_verifier_excludes_origin_and_previous_conflict_sources(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_LOW_CONFIDENCE", "true")
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_MAX_FIELDS", "3")
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_MAX_SOURCES", "4")

    captured = {}
    monkeypatch.setattr("src.research_agent.verification.identity_is_strong", lambda _identity: True)

    def fake_build_providers(source_names, **_kwargs):
        captured["sources"] = list(source_names)
        return []

    monkeypatch.setattr("src.research_agent.verification.build_providers", fake_build_providers)

    result = verify_questionable_fields(
        "PLACA_MAE",
        payload=_motherboard_payload("B550"),
        fields=["chipset"],
        origin_by_field={"chipset": {"fonte": "PC_KOMBO"}},
        excluded_sources_by_field={"chipset": ["GEIZHALS"]},
    )

    assert result["executado"] is True
    assert "PC_KOMBO" not in captured["sources"]
    assert "GEIZHALS" not in captured["sources"]
    assert captured["sources"] == ["FABRICANTE_OFICIAL", "ICECAT"]
