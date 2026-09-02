from src.enrichment.core import TechnicalEnricher
from src.enrichment.identity import build_identity, identity_is_strong, text_matches_identity
from src.main import build_result


class DummyProvider:
    def __init__(self, name, attributes=None, text="", ok=True, url="https://example.com/p"):
        self.name = name
        self.attributes = attributes or []
        self.text = text
        self.ok = ok
        self.url = url
        self.calls = 0

    def collect(self, identity, category):
        self.calls += 1
        if not self.ok:
            return {"ok": False, "fonte": self.name, "erro": "NAO_ENCONTRADO"}
        return {
            "ok": True,
            "fonte": self.name,
            "url": self.url,
            "attributes": self.attributes,
            "context_text": self.text,
        }


def raw_product(**overrides):
    raw = {
        "ok": True,
        "title": "AMD Ryzen 7 7800X3D",
        "brand": "AMD",
        "model": "7800X3D",
        "mpn": "100-100000910WOF",
        "gtin": None,
        "description": "Processador AMD Ryzen 7 7800X3D",
        "attributes": [],
        "attributes_text": "",
        "product_attributes": [],
        "url_original": "https://www.magazineluiza.com.br/produto/p/abc123/",
        "url_final": "https://www.magazineluiza.com.br/produto/p/abc123/",
        "price": 2000.0,
        "previous_price": None,
        "available": True,
        "source": "TESTE",
    }
    raw.update(overrides)
    return raw


def test_identity_gtin_has_priority():
    result = build_result(raw_product(gtin="7891234567895"), "PROCESSADOR")
    identity = build_identity(result)
    assert identity["metodo"] == "GTIN"
    assert identity_is_strong(identity)


def test_identity_brand_mpn_is_strong():
    result = build_result(raw_product(), "PROCESSADOR")
    identity = build_identity(result)
    assert identity["metodo"] == "MARCA_MPN"
    assert identity["confianca"] == "MUITO_ALTA"


def test_identity_generic_model_without_mpn_is_not_enough():
    result = build_result(raw_product(model="Gaming", mpn=None), "PROCESSADOR")
    identity = build_identity(result)
    assert identity["metodo"] is None
    assert not identity_is_strong(identity)


def test_identity_match_requires_mpn_when_method_is_brand_mpn():
    result = build_result(raw_product(), "PROCESSADOR")
    identity = build_identity(result)
    assert text_matches_identity(identity, "AMD Ryzen 7 7800X3D MPN 100-100000910WOF")
    assert not text_matches_identity(identity, "AMD Ryzen 7 7800X3D outro part number")


def test_enrichment_fills_missing_fields_and_records_provenance():
    result = build_result(raw_product(), "PROCESSADOR")
    provider = DummyProvider("FABRICANTE_OFICIAL", [
        {"name": "Socket", "value_name": "AM5"},
        {"name": "TDP", "value_name": "120 W"},
        {"name": "Tipos de memória RAM suportados", "value_name": "DDR5"},
    ])
    enriched = TechnicalEnricher([provider]).enrich(result)
    specs = enriched["especificacoesEncontradas"]
    assert specs["socket"] == "AM5"
    assert specs["tdpWatts"] == 120
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert enriched["enriquecimentoTecnico"]["origemPorCampo"]["socket"]["fonte"] == "FABRICANTE_OFICIAL"
    assert "socket" not in enriched["camposObrigatoriosAusentes"]


def test_enrichment_does_not_overwrite_conflicting_primary_value():
    raw = raw_product(attributes=[
        {"name": "Socket", "value_name": "AM5"},
        {"name": "Tipos de memória RAM suportados", "value_name": "DDR5"},
    ], attributes_text="Socket: AM5\nTipos de memória RAM suportados: DDR5")
    result = build_result(raw, "PROCESSADOR")
    provider = DummyProvider("GEIZHALS", [
        {"name": "Socket", "value_name": "AM4"},
    ])
    enriched = TechnicalEnricher([provider]).enrich(result)
    assert enriched["especificacoesEncontradas"]["socket"] == "AM5"
    conflicts = enriched["enriquecimentoTecnico"]["conflitos"]
    assert any(c["campo"] == "socket" and c["valorExterno"] == "AM4" for c in conflicts)


def test_first_source_wins_for_missing_field_and_later_difference_is_conflict():
    result = build_result(raw_product(), "PROCESSADOR")
    official = DummyProvider("FABRICANTE_OFICIAL", [{"name": "TDP", "value_name": "120 W"}])
    secondary = DummyProvider("PC_KOMBO", [{"name": "TDP", "value_name": "105 W"}])
    enriched = TechnicalEnricher([official, secondary]).enrich(result)
    assert enriched["especificacoesEncontradas"]["tdpWatts"] == 120
    assert enriched["enriquecimentoTecnico"]["origemPorCampo"]["tdpWatts"]["fonte"] == "FABRICANTE_OFICIAL"
    assert any(c["campo"] == "tdpWatts" and c["fonte"] == "PC_KOMBO" for c in enriched["enriquecimentoTecnico"]["conflitos"])


def test_enrichment_skips_when_identity_is_insufficient():
    result = build_result(raw_product(brand=None, model=None, mpn=None, gtin=None), "PROCESSADOR")
    provider = DummyProvider("FABRICANTE_OFICIAL", [{"name": "Socket", "value_name": "AM5"}])
    enriched = TechnicalEnricher([provider]).enrich(result)
    assert enriched["enriquecimentoTecnico"]["executado"] is False
    assert enriched["enriquecimentoTecnico"]["motivoIgnorado"] == "IDENTIDADE_INSUFICIENTE"
    assert provider.calls == 0
