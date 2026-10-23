from copy import deepcopy

import pytest

from src import api
from src.extension.router import _product_payload_for_backend
from src.extractors.backend_schemas import SCHEMAS
from src.main import build_result
from src.technical_ai import auto


PRODUCT_CASES = [
    ("CELULAR", {"nfc": False}, {"ramGb": 8, "armazenamentoGb": 256,
                                "tamanhoTelaPolegadas": 6.7, "bateriaMah": 5000,
                                "cameraPrincipalMp": 50}),
    ("MONITOR", {"hdr": False}, {"tamanhoPolegadas": 27, "taxaAtualizacaoHz": 144}),
    ("MOUSE", {"wireless": False}, {"dpiMaximo": 16000}),
    ("TECLADO", {"abnt2": False}, {"tipo": "MECANICO", "layout": "ANSI"}),
    ("HEADSET", {"wireless": False}, {"driverMm": 50}),
]


@pytest.mark.parametrize("category,current,found", PRODUCT_CASES)
def test_automatic_link_research_reaches_every_structured_product(monkeypatch, category, current, found):
    spec_key = SCHEMAS[category][1]
    original = {
        "categoriaDetectada": category,
        "tipoCadastro": "PRODUTO",
        "descricaoAnuncio": "Descrição antes da pesquisa",
        "payloadParcialBackend": {
            "nome": "Produto Teste", "marca": "Teste", "modelo": "T1",
            "descricao": "Descrição original da loja",
            "metadados": {"asin": "B0TEST0000", "especificacoesEncontradas": current},
            spec_key: current,
        },
        "ofertaColetada": {"preco": 199.9, "urlOriginal": "https://loja.example/produto"},
    }
    before = deepcopy(original)
    calls = []

    def research(**kwargs):
        calls.append(kwargs)
        safe = deepcopy(kwargs["payload"])
        safe[spec_key].update(found)
        return {"utilizado": True, "payload": safe, "camposPreenchidos": list(found)}

    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setattr(auto, "enrich_hardware_with_external_ai", research)
    result = auto.auto_enrich_link_result(original)
    assert len(calls) == 1
    assert calls[0]["category"] == category and calls[0]["only_fill_gaps"] is True
    product = _product_payload_for_backend(category, result, result["payloadParcialBackend"])
    assert product[spec_key] == {**current, **found}
    assert product["metadados"]["especificacoesEncontradas"] == product[spec_key]
    assert product["metadados"]["asin"] == "B0TEST0000"
    assert result["ofertaColetada"] == before["ofertaColetada"]
    if category == "CELULAR":
        assert len(product["descricao"].split(" · ")) == 4
        assert result["descricaoAnuncio"] == before["descricaoAnuncio"]
        assert "mAh" in product["descricao"] and "NFC" not in product["descricao"]
        assert "Câmera" not in product["descricao"]
    else:
        assert product["descricao"] == before["payloadParcialBackend"]["descricao"]


@pytest.mark.parametrize("category", ["FONE", "TABLET", "MOUSEPAD", "ROTEADOR"])
def test_products_without_specific_table_keep_collected_information_in_registration(category):
    attributes = [{"name": "Conexão", "value_name": "Bluetooth 5.3"},
                  {"name": "Modelo", "value_name": "T1"}]
    result = build_result({"title": "Produto Teste", "brand": "Teste", "model": "T1",
                           "attributes": attributes, "product_attributes": attributes},
                          forced_category=category)
    product = _product_payload_for_backend(category, result, result["payloadParcialBackend"])
    assert product["metadados"]["informacoesProdutoEncontradas"] == attributes
    assert product["metadados"]["especificacoesEncontradas"] == result["especificacoesEncontradas"]
    assert not any(key.startswith("especificacao") for key in product)


def test_phone_registration_analyzes_page_and_enriches_before_returning_preview(monkeypatch):
    raw = {"ok": True, "title": "Samsung Galaxy Teste", "brand": "Samsung", "model": "T1",
           "mpn": "T1-256", "description": "NFC: Não", "price": 999.9,
           "url_original": "https://loja.example/telefone", "attributes": []}
    monkeypatch.setenv("ENRICHMENT_DISABLE", "false")
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    monkeypatch.setattr(api.GenericScraper, "collect", lambda *args, **kwargs: deepcopy(raw))
    monkeypatch.setattr(api, "complement_link_page", lambda raw, *args, **kwargs: raw)

    def research(**kwargs):
        safe = deepcopy(kwargs["payload"])
        safe["especificacaoCelular"]["bateriaMah"] = 5000
        return {"utilizado": True, "payload": safe, "camposPreenchidos": ["bateriaMah"]}

    monkeypatch.setattr(auto, "enrich_hardware_with_external_ai", research)
    result = api._analyze_sync(api.AnalyzeRequest(url=raw["url_original"], categoria="CELULAR", detalharPagina=True))
    product = _product_payload_for_backend("CELULAR", result, result["payloadParcialBackend"])
    assert product["especificacaoCelular"] == {"nfc": False, "bateriaMah": 5000}
    assert "mAh" in product["descricao"]
    assert result["ofertaColetada"]["preco"] == 999.9


def test_explicit_product_categories_enable_research_but_commercial_price_checks_do_not():
    for category, _, _ in PRODUCT_CASES:
        assert api._should_auto_enrich_link_request(category, False) is True
    assert api._should_auto_enrich_link_request(None, False) is False


def test_research_failure_preserves_product_specs_and_metadata(monkeypatch):
    original = {"categoriaDetectada": "CELULAR", "payloadParcialBackend": {
        "nome": "Celular Teste", "especificacaoCelular": {"nfc": False},
        "metadados": {"asin": "B0TEST0000"}, "descricao": "Descrição existente"}}
    monkeypatch.setenv("IA_TECNICA_AUTO", "true")
    def unavailable(**kwargs):
        raise RuntimeError("Pesquisa indisponível")
    monkeypatch.setattr(auto, "enrich_hardware_with_external_ai", unavailable)
    result = auto.auto_enrich_link_result(deepcopy(original))
    assert result["payloadParcialBackend"] == original["payloadParcialBackend"]
    assert result["enriquecimentoIaTecnica"]["utilizado"] is False
