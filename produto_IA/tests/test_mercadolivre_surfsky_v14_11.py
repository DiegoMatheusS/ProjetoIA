from src.scrapers.mercadolivre_scraper import MercadoLivreScraper


def test_ml_uses_surfsky_when_api_has_no_data(monkeypatch):
    monkeypatch.delenv("ML_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SURFSKY_TOKEN", "fake-token")

    def fake_fetch(self, url, interaction_profile=None):
        return {
            "html": '''
            <html><head>
              <meta property="og:title" content="Processador AMD Ryzen 5 7600" />
              <meta property="og:image" content="https://example.com/cpu.jpg" />
              <script type="application/ld+json">
              {"@type":"Product","name":"Processador AMD Ryzen 5 7600","brand":{"name":"AMD"},"model":"Ryzen 5 7600","mpn":"100-100001015BOX","offers":{"price":"1299.90","priceCurrency":"BRL","availability":"https://schema.org/InStock"}}
              </script>
            </head><body><h1>Processador AMD Ryzen 5 7600</h1></body></html>
            ''',
            "final_url": url,
            "blocked": False,
            "surfsky": True,
            "error": None,
        }

    monkeypatch.setattr("src.scrapers.browser_scraper.BrowserScraper.fetch_surfsky", fake_fetch)

    raw = MercadoLivreScraper().collect(
        "https://www.mercadolivre.com.br/processador-amd-ryzen-5-7600/p/MLB12345678"
    )

    assert raw["source"] == "MERCADO_LIVRE_SURFSKY_CLOUD"
    assert raw["title"] == "Processador AMD Ryzen 5 7600"
    assert raw["brand"] == "AMD"
    assert raw["model"] == "Ryzen 5 7600"
    assert raw["mpn"] == "100-100001015BOX"
    assert raw["price"] == 1299.90
    assert raw["available"] is True
    assert raw["collection_attempts"][0]["modo"] == "SURFSKY_ORIGINAL"
    assert raw["collection_attempts"][0]["erro"] is None


def test_ml_reports_surfsky_not_configured(monkeypatch):
    monkeypatch.delenv("ML_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SURFSKY_TOKEN", raising=False)

    def fake_generic(self, url, no_browser=False):
        return {
            "ok": False,
            "source": "NAVEGADOR_GENERICO",
            "url_original": url,
            "url_final": url,
            "blocked": True,
            "error": "blocked",
        }

    monkeypatch.setattr("src.scrapers.generic_scraper.GenericScraper.collect", fake_generic)

    raw = MercadoLivreScraper().collect("https://produto.mercadolivre.com.br/MLB-6740306774-produto-_JM")
    assert raw["collection_attempts"][0]["modo"] == "SURFSKY_CONFIG"
    assert raw["collection_attempts"][0]["erro"] == "SURFSKY_NAO_CONFIGURADO"
