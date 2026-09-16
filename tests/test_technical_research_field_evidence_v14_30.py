import src.enrichment.providers as enrichment_providers
import src.technical_ai.iterative_research as iterative

from src.research_agent.confidence import annotate_field_confidence
from src.technical_ai.evidence import collect_cited_sources
from src.technical_ai.providers import TechnicalAIResponse


class FakeProvider:
    def __init__(self, text="chipset: B550", sources=None):
        self.text = text
        self.sources = sources or [{"url": "https://www.msi.com/Motherboard/B550-A-PRO/Specification", "titulo": "MSI"}]

    def enrich(self, prompt):
        return TechnicalAIResponse(
            provider="OPENAI",
            model="teste",
            text=self.text,
            sources=self.sources,
        )


def _motherboard_payload(**specs):
    return {
        "categoria": "PLACA_MAE",
        "nome": "MSI B550-A Pro",
        "marca": "MSI",
        "modelo": "B550-A Pro",
        "especificacaoPlacaMae": dict(specs),
    }


def test_openai_web_search_without_field_evidence_is_conservative(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setenv("TECH_RESEARCH_REQUIRE_FIELD_EVIDENCE_FOR_WEB_CONFIDENCE", "true")
    monkeypatch.setattr(iterative, "collect_cited_sources", lambda *args, **kwargs: {})

    result = iterative.run_iterative_external_research(
        provider=FakeProvider(),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
        local_info={},
    )

    origin = result.provenance["chipset"]
    assert origin["fonte"] == "OPENAI_WEB_SEARCH"
    assert origin["evidenciaCampoConfirmada"] is False

    confidence = annotate_field_confidence(
        {"origemPorCampo": result.provenance, "conflitos": []}
    )
    assert confidence["confiancaPorCampo"]["chipset"]["score"] == 0.74


def test_official_field_evidence_promotes_provenance(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_OPENAI_ROUNDS", "1")
    monkeypatch.setattr(
        iterative,
        "collect_cited_sources",
        lambda *args, **kwargs: {
            "chipset": {
                "fonte": "FABRICANTE_OFICIAL",
                "url": "https://www.msi.com/Motherboard/B550-A-PRO/Specification",
                "trecho": "Chipset: AMD B550",
                "valor": "B550",
            }
        },
    )

    result = iterative.run_iterative_external_research(
        provider=FakeProvider(),
        category="PLACA_MAE",
        name="MSI B550-A Pro",
        payload=_motherboard_payload(),
        local_info={},
    )

    origin = result.provenance["chipset"]
    assert origin["fonte"] == "FABRICANTE_OFICIAL"
    assert origin["evidenciaCampoConfirmada"] is True
    assert origin["metodo"] == "OPENAI_COM_CITACAO_OFICIAL_REVALIDADA"
    assert result.rounds[0]["camposComEvidenciaOficialConfirmada"] == ["chipset"]

    confidence = annotate_field_confidence(
        {"origemPorCampo": result.provenance, "conflitos": []}
    )
    assert confidence["confiancaPorCampo"]["chipset"]["score"] == 0.98


def test_web_search_legacy_confidence_can_be_restored_by_flag(monkeypatch):
    monkeypatch.setenv("TECH_RESEARCH_REQUIRE_FIELD_EVIDENCE_FOR_WEB_CONFIDENCE", "false")
    info = annotate_field_confidence(
        {
            "origemPorCampo": {
                "chipset": {
                    "fonte": "OPENAI_WEB_SEARCH",
                    "urls": ["https://example.com/spec"],
                    "evidenciaCampoConfirmada": False,
                }
            },
            "conflitos": [],
        }
    )
    assert info["confiancaPorCampo"]["chipset"]["score"] == 0.80


def test_collect_cited_sources_returns_field_level_official_evidence(monkeypatch):
    class FakeManufacturerProvider:
        name = "FABRICANTE_OFICIAL"

        def __init__(self):
            self.timeout = None
            self.allow_browser_fallback = True

        def search_domains(self, identity):
            return ["msi.com"]

        def fetch_candidate(self, url, identity):
            return {
                "ok": True,
                "url": url,
                "attributes": [
                    {"name": "Chipset", "value_name": "AMD B550"},
                ],
                "context_text": "Chipset: AMD B550",
            }

    monkeypatch.setattr(
        enrichment_providers,
        "ManufacturerProvider",
        FakeManufacturerProvider,
    )

    local_info = {}
    verified = collect_cited_sources(
        "PLACA_MAE",
        _motherboard_payload(),
        [{"url": "https://www.msi.com/Motherboard/B550-A-PRO/Specification"}],
        local_info,
    )

    assert verified["chipset"]["fonte"] == "FABRICANTE_OFICIAL"
    assert verified["chipset"]["valor"] == "B550"
    assert local_info["evidenciaPorCampo"]["chipset"]["valor"] == "B550"
