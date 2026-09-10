from src import api


def _raw_offer():
    return {
        "ok": True,
        "blocked": False,
        "source": "TESTE",
        "url_original": "https://example.com/produto",
        "url_final": "https://example.com/produto",
        "title": "Produto Teste",
        "brand": "Marca",
        "model": "Modelo",
        "mpn": "MPN-1",
        "gtin": None,
        "image_url": None,
        "description": "Produto de teste",
        "price": 1234.56,
        "previous_price": 1500.00,
        "price_source": "TESTE",
        "currency": "BRL",
        "available": True,
        "attributes": [],
        "product_attributes": [],
    }


def test_price_style_analisar_does_not_call_gemini(monkeypatch):
    """Contrato usado pela consulta de preço: categoria ausente + enrich=false."""
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("ENRICHMENT_AUTO", "false")
    monkeypatch.setattr(api.GenericScraper, "collect", lambda self, url, no_browser=False: _raw_offer())

    calls = []
    monkeypatch.setattr(api, "auto_enrich_link_result", lambda result: calls.append(True) or result)

    out = api._analyze_sync(api.AnalyzeRequest(
        url="https://example.com/produto",
        categoria=None,
        enrich=False,
        criabytePlan=False,
        noBrowser=False,
    ))

    assert calls == []
    assert out["ofertaColetada"]["preco"] == 1234.56
    assert out["ofertaColetada"]["precoAnterior"] == 1500.0
    assert out["ofertaColetada"]["disponivel"] is True


def test_hardware_link_with_explicit_category_still_calls_gemini(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("ENRICHMENT_AUTO", "false")
    raw = _raw_offer()
    raw.update({
        "title": "AMD Ryzen 5 Teste",
        "brand": "AMD",
        "model": "Ryzen 5 Teste",
        "description": "Processador AM5",
    })
    monkeypatch.setattr(api.GenericScraper, "collect", lambda self, url, no_browser=False: dict(raw))

    calls = []
    def fake_auto(result):
        calls.append(True)
        result["iaTecnicaAutomatica"] = {"utilizado": False, "motivo": "TESTE"}
        return result
    monkeypatch.setattr(api, "auto_enrich_link_result", fake_auto)

    out = api._analyze_sync(api.AnalyzeRequest(
        url="https://example.com/cpu",
        categoria="PROCESSADOR",
        enrich=False,
    ))

    assert calls == [True]
    assert out["ofertaColetada"]["preco"] == 1234.56


def test_explicit_enrich_allows_detected_hardware_even_without_category(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("ENRICHMENT_AUTO", "false")
    raw = _raw_offer()
    raw.update({"title": "AMD Ryzen 5 Teste", "description": "Processador AM5 DDR5"})
    monkeypatch.setattr(api.GenericScraper, "collect", lambda self, url, no_browser=False: dict(raw))

    calls = []
    monkeypatch.setattr(api, "auto_enrich_link_result", lambda result: calls.append(True) or result)
    api._analyze_sync(api.AnalyzeRequest(
        url="https://example.com/cpu",
        categoria=None,
        enrich=True,
    ))
    assert calls == [True]


def test_link_enrichment_gate_rules():
    assert api._should_auto_enrich_link_request(None, False) is False
    assert api._should_auto_enrich_link_request("", False) is False
    assert api._should_auto_enrich_link_request("PROCESSADOR", False) is True
    assert api._should_auto_enrich_link_request("PLACA_VIDEO", False) is True
    assert api._should_auto_enrich_link_request(None, True) is True
