from src.technical_ai import iterative_research
from src.technical_ai.iterative_research import run_iterative_external_research
from src.technical_ai.providers import TechnicalAIResponse


class FakeProvider:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def enrich_with_budget(self, prompt, *, budget_seconds):
        self.prompts.append((prompt, budget_seconds))
        return TechnicalAIResponse(
            provider="OPENAI",
            model="teste",
            text=self.text,
            sources=[{"url": "https://www.msi.com/Motherboard/B550-A-PRO", "titulo": "MSI B550-A PRO"}],
        )


def _payload():
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": {},
    }


def _official(value):
    return {
        "chipset": {
            "fonte": "FABRICANTE_OFICIAL",
            "url": "https://www.msi.com/Motherboard/B550-A-PRO",
            "trecho": f"Chipset: {value}",
            "valor": value,
            "metodo": "CITACAO_OFICIAL_REEXTRAIDA_DETERMINISTICAMENTE",
        }
    }


def test_official_evidence_divergence_becomes_explicit_conflict(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_RECORD_OFFICIAL_EVIDENCE_CONFLICTS", "true")
    monkeypatch.setattr(
        iterative_research,
        "collect_cited_sources",
        lambda *args, **kwargs: _official("X570"),
    )

    result = run_iterative_external_research(
        provider=FakeProvider("chipset: B550"),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_payload(),
        local_info={},
    )

    conflicts = [item for item in result.conflicts if item.get("campo") == "chipset"]
    assert len(conflicts) == 1
    assert conflicts[0]["valorAtual"] == "B550"
    assert conflicts[0]["valorExterno"] == "X570"
    assert conflicts[0]["fonte"] == "FABRICANTE_OFICIAL"
    assert conflicts[0]["metodo"] == "CITACAO_OFICIAL_DIVERGIU_DA_RESPOSTA_OPENAI"
    assert result.rounds[0]["camposComConflitoEvidenciaOficial"] == ["chipset"]
    assert result.provenance["chipset"]["evidenciaCampoConfirmada"] is False


def test_matching_official_evidence_confirms_field_without_conflict(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_RECORD_OFFICIAL_EVIDENCE_CONFLICTS", "true")
    monkeypatch.setattr(
        iterative_research,
        "collect_cited_sources",
        lambda *args, **kwargs: _official("B550"),
    )

    result = run_iterative_external_research(
        provider=FakeProvider("chipset: B550"),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_payload(),
        local_info={},
    )

    assert not [item for item in result.conflicts if item.get("campo") == "chipset"]
    assert result.rounds[0]["camposComEvidenciaOficialConfirmada"] == ["chipset"]
    assert result.rounds[0]["camposComConflitoEvidenciaOficial"] == []
    assert result.provenance["chipset"]["fonte"] == "FABRICANTE_OFICIAL"
    assert result.provenance["chipset"]["evidenciaCampoConfirmada"] is True


def test_official_conflict_recording_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_RECORD_OFFICIAL_EVIDENCE_CONFLICTS", "false")
    monkeypatch.setattr(
        iterative_research,
        "collect_cited_sources",
        lambda *args, **kwargs: _official("X570"),
    )

    result = run_iterative_external_research(
        provider=FakeProvider("chipset: B550"),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_payload(),
        local_info={},
    )

    assert not [item for item in result.conflicts if item.get("campo") == "chipset"]
    assert result.rounds[0]["camposComConflitoEvidenciaOficial"] == []


def test_list_values_compare_independent_of_order(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_RECORD_OFFICIAL_EVIDENCE_CONFLICTS", "true")
    monkeypatch.setattr(
        iterative_research,
        "collect_cited_sources",
        lambda *args, **kwargs: {
            "tiposMemoriaSuportados": {
                "fonte": "FABRICANTE_OFICIAL",
                "url": "https://www.msi.com/Motherboard/B550-A-PRO",
                "trecho": "Memory: DDR4, DDR5",
                "valor": ["DDR5", "DDR4"],
            }
        },
    )

    result = run_iterative_external_research(
        provider=FakeProvider("tiposMemoriaSuportados: DDR4, DDR5"),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_payload(),
        local_info={},
    )

    assert not [item for item in result.conflicts if item.get("campo") == "tiposMemoriaSuportados"]
