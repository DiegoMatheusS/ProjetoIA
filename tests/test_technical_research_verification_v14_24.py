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
    monkeypatch.setitem(
        __import__("src.research_agent.quality_gate", fromlist=["COVERAGE_WEIGHT_TIERS"]).COVERAGE_WEIGHT_TIERS,
        "PLACA_MAE",
        {"essenciais": ["chipset"]},
    )
    monkeypatch.setattr("src.research_agent.quality_gate.technical_coverage", lambda _state: 1.0)
    monkeypatch.setattr("src.research_agent.quality_gate.technical_missing_fields", lambda _state: [])
    monkeypatch.setattr("src.research_agent.quality_gate.required_missing_fields", lambda _state: [])


def test_independent_confirmation_removes_low_confidence_review(monkeypatch):
    _simplify_quality_gate(monkeypatch)
    monkeypatch.setattr(
        "src.research_agent.quality_gate.verify_questionable_fields",
        lambda *_args, **_kwargs: {
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
        },
    )

    audit = evaluate_research_quality(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        final_payload=_motherboard_payload("B550"),
        confidence_by_field={
            "chipset": {"fonte": "OPENAI", "score": 0.72}
        },
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "APROVADO"
    assert audit["podeMarcarPronto"] is True
    assert audit["camposParaRevisao"] == []
    assert audit["camposConfirmadosAutomaticamente"][0]["campo"] == "chipset"
    assert audit["camposConfirmadosAutomaticamente"][0]["fonteConfirmacao"] == "FABRICANTE_OFICIAL"


def test_without_independent_confirmation_low_confidence_still_requires_review(monkeypatch):
    _simplify_quality_gate(monkeypatch)
    monkeypatch.setattr(
        "src.research_agent.quality_gate.verify_questionable_fields",
        lambda *_args, **_kwargs: {
            "executado": False,
            "motivoIgnorado": "TECH_RESEARCH_VERIFY_LOW_CONFIDENCE_FALSE",
            "camposSolicitados": ["chipset"],
            "confirmacoes": {},
            "conflitos": [],
            "fontesConsultadas": [],
        },
    )

    audit = evaluate_research_quality(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        final_payload=_motherboard_payload("B550"),
        confidence_by_field={
            "chipset": {"fonte": "OPENAI", "score": 0.72}
        },
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert "chipset" in audit["camposParaRevisao"]
    assert "CAMPOS_ESSENCIAIS_COM_CONFIANCA_BAIXA" in audit["motivos"]


def test_verification_conflict_keeps_field_in_review(monkeypatch):
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
                    "valorExterno": "X570",
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
        confidence_by_field={
            "chipset": {"fonte": "OPENAI", "score": 0.72}
        },
        conflicts=[],
        registration_issues=[],
    )

    assert audit["status"] == "PRECISA_REVISAO"
    assert "CONFLITOS_NAO_RESOLVIDOS" in audit["motivos"]
    assert audit["conflitosNaoResolvidos"][0]["valorExterno"] == "X570"


def test_verifier_confirms_same_value_from_independent_source(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_LOW_CONFIDENCE", "true")
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_MAX_FIELDS", "2")
    monkeypatch.setenv("TECH_RESEARCH_VERIFY_MAX_SOURCES", "1")

    class FakeProvider:
        name = "FABRICANTE_OFICIAL"
        allow_browser_fallback = False
        timeout = 3
        resolver = None

        def collect(self, _identity, _category):
            return {
                "ok": True,
                "fonte": self.name,
                "url": "https://example.com/msi-b550-a-pro",
                "attributes": [],
                "context_text": "chipset B550",
            }

    monkeypatch.setattr("src.research_agent.verification.identity_is_strong", lambda _identity: True)
    monkeypatch.setattr(
        "src.research_agent.verification.build_providers",
        lambda *_args, **_kwargs: [FakeProvider()],
    )
    monkeypatch.setattr(
        "src.research_agent.verification.extract_specs",
        lambda *_args, **_kwargs: {"chipset": "B550"},
    )
    monkeypatch.setattr(
        "src.research_agent.verification.validate_specs",
        lambda _category, specs, *_args, **_kwargs: (specs, []),
    )
    monkeypatch.setattr(
        "src.research_agent.verification.evidence_for_specs",
        lambda *_args, **_kwargs: {"chipset": {"trecho": "chipset B550"}},
    )

    result = verify_questionable_fields(
        "PLACA_MAE",
        payload=_motherboard_payload("B550"),
        fields=["chipset"],
        origin_by_field={"chipset": {"fonte": "OPENAI"}},
    )

    assert result["executado"] is True
    assert result["confirmacoes"]["chipset"]["fonte"] == "FABRICANTE_OFICIAL"
    assert result["confirmacoes"]["chipset"]["score"] == 0.98
    assert result["conflitos"] == []
