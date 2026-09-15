from src.research_agent.evidence_resolver import resolve_live_research_conflicts


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


def test_stronger_official_source_can_replace_weak_automatic_value(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "true")
    monkeypatch.setenv("TECH_RESEARCH_CONSENSUS_MIN_DELTA", "0.08")

    payload, info = resolve_live_research_conflicts(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        researched_payload=_motherboard_payload("B450"),
        info={
            "origemPorCampo": {
                "chipset": {
                    "fonte": "PC_KOMBO",
                    "url": "https://example.com/pc-kombo",
                }
            },
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B450",
                    "valorExterno": "B550",
                    "fonte": "FABRICANTE_OFICIAL",
                    "url": "https://example.com/msi",
                }
            ],
        },
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert info["camposSubstituidosPorConsenso"] == ["chipset"]
    assert info["conflitos"] == []
    assert info["origemPorCampo"]["chipset"]["fonte"] == "FABRICANTE_OFICIAL"


def test_original_value_is_never_replaced(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "true")

    payload, info = resolve_live_research_conflicts(
        "PLACA_MAE",
        original_payload=_motherboard_payload("B450"),
        researched_payload=_motherboard_payload("B450"),
        info={
            "origemPorCampo": {
                "chipset": {"fonte": "PC_KOMBO"}
            },
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B450",
                    "valorExterno": "B550",
                    "fonte": "FABRICANTE_OFICIAL",
                }
            ],
        },
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B450"
    assert info["camposSubstituidosPorConsenso"] == []
    assert len(info["conflitos"]) == 1


def test_two_independent_sources_can_confirm_current_automatic_value(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "true")
    monkeypatch.setenv("TECH_RESEARCH_CONSENSUS_MIN_SOURCES", "2")
    monkeypatch.setenv("TECH_RESEARCH_CONSENSUS_MIN_DELTA", "0.08")

    payload, info = resolve_live_research_conflicts(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        researched_payload=_motherboard_payload("B550"),
        info={
            "origemPorCampo": {
                "chipset": {"fonte": "GEIZHALS"}
            },
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B550",
                    "valorExterno": "B550",
                    "fonte": "PC_KOMBO",
                },
                {
                    "campo": "chipset",
                    "valorPrincipal": "B550",
                    "valorExterno": "X570",
                    "fonte": "DESCONHECIDA",
                },
            ],
        },
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert info["conflitos"] == []
    assert info["resolucaoConflitosPesquisa"]["camposResolvidos"] == ["chipset"]
    assert info["origemPorCampo"]["chipset"]["apoiosIndependentes"] == 2


def test_close_confidence_disagreement_stays_for_review(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "true")
    monkeypatch.setenv("TECH_RESEARCH_CONSENSUS_MIN_DELTA", "0.08")

    payload, info = resolve_live_research_conflicts(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        researched_payload=_motherboard_payload("B550"),
        info={
            "origemPorCampo": {
                "chipset": {"fonte": "GEIZHALS"}
            },
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B550",
                    "valorExterno": "X570",
                    "fonte": "TECHPOWERUP",
                }
            ],
        },
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B550"
    assert info["camposSubstituidosPorConsenso"] == []
    assert len(info["conflitos"]) == 1
    assert info["resolucaoConflitosPesquisa"]["conflitosRestantes"] == 1


def test_live_conflict_resolution_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS", "false")

    payload, info = resolve_live_research_conflicts(
        "PLACA_MAE",
        original_payload=_motherboard_payload(),
        researched_payload=_motherboard_payload("B450"),
        info={
            "origemPorCampo": {"chipset": {"fonte": "PC_KOMBO"}},
            "conflitos": [
                {
                    "campo": "chipset",
                    "valorPrincipal": "B450",
                    "valorExterno": "B550",
                    "fonte": "FABRICANTE_OFICIAL",
                }
            ],
        },
    )

    assert payload["especificacaoPlacaMae"]["chipset"] == "B450"
    assert info["resolucaoConflitosPesquisa"]["executado"] is False
    assert info["resolucaoConflitosPesquisa"]["motivoIgnorado"] == "TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS_FALSE"
