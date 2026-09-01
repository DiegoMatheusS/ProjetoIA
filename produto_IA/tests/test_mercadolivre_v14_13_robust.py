from src.main import build_result
from src.scrapers.mercadolivre_scraper import MercadoLivreScraper


def test_meli_short_link_is_recognized():
    assert MercadoLivreScraper.is_mercadolivre("https://meli.la/abc123") is True


def test_ml_rendered_html_parser_reads_price_and_specs():
    html = r'''
    <html>
      <head>
        <meta property="og:title" content="Processador Intel Core i5-9400F 2.9GHz LGA1151" />
        <meta property="og:image" content="https://http2.mlstatic.com/D_NQ_NP_123.jpg" />
      </head>
      <body>
        <h1 class="ui-pdp-title">Processador Intel Core i5-9400F 2.9GHz LGA1151</h1>
        <div class="ui-pdp-price__main-container">
          <s class="ui-pdp-price__original-value">
            <span class="andes-money-amount andes-money-amount--previous">
              <span class="andes-money-amount__fraction">1.099</span>
              <span class="andes-money-amount__cents">90</span>
            </span>
          </s>
          <div class="ui-pdp-price__second-line">
            <span class="andes-money-amount">
              <span class="andes-money-amount__fraction">899</span>
              <span class="andes-money-amount__cents">90</span>
            </span>
          </div>
        </div>
        <section class="ui-vpp-striped-specs">
          <div class="ui-vpp-striped-specs__row"><div>Marca</div><div>Intel</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Modelo</div><div>Core i5-9400F</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Socket</div><div>LGA1151</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Número de núcleos</div><div>6</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Número de threads</div><div>6</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Frequência base</div><div>2.9 GHz</div></div>
          <div class="ui-vpp-striped-specs__row"><div>Frequência turbo máxima</div><div>4.1 GHz</div></div>
        </section>
        <button>Comprar agora</button>
      </body>
    </html>
    '''
    raw = MercadoLivreScraper._parse_ml_browser_page(
        "https://www.mercadolivre.com.br/processador-intel/p/MLB12345678",
        {
            "html": html,
            "text": "Comprar agora",
            "final_url": "https://www.mercadolivre.com.br/processador-intel/p/MLB12345678",
            "blocked": False,
        },
    )
    assert raw["title"].startswith("Processador Intel Core i5-9400F")
    assert raw["price"] == 899.90
    assert raw["previous_price"] == 1099.90
    assert raw["brand"] == "Intel"
    assert raw["model"] == "Core i5-9400F"
    assert len(raw["attributes"]) >= 7

    result = build_result(raw)
    specs = result["especificacoesEncontradas"]
    assert result["categoriaDetectada"] == "PROCESSADOR"
    assert specs["socket"] == "LGA1151"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 6
    assert specs["frequenciaBaseMhz"] == 2900
    assert specs["frequenciaTurboMhz"] == 4100


class _PartialApiML(MercadoLivreScraper):
    def __init__(self):
        self.token = "fake"
        self.api_debug = []

    def _api_get(self, path, params=None, allow_public_fallback=False):
        if path == "/items/MLB9999999999":
            return {
                "id": "MLB9999999999",
                "title": "Processador Intel Core i5-9400F",
                "price": 899.90,
                "currency_id": "BRL",
                "status": "active",
                "attributes": [
                    {"id": "BRAND", "name": "Marca", "value_name": "Intel"},
                    {"id": "MODEL", "name": "Modelo", "value_name": "Core i5-9400F"},
                ],
            }, None
        if path.endswith("/sale_price") or path.endswith("/prices"):
            return None, "restrito"
        return None, "sem catalogo"


def test_partial_api_is_completed_by_surfsky(monkeypatch):
    monkeypatch.setenv("SURFSKY_TOKEN", "fake")
    html = r'''
    <html><head>
      <meta property="og:title" content="Processador Intel Core i5-9400F" />
      <meta property="og:image" content="https://http2.mlstatic.com/D_NQ_NP_cpu.jpg" />
    </head><body>
      <h1>Processador Intel Core i5-9400F</h1>
      <div class="ui-vpp-striped-specs__row"><div>Socket</div><div>LGA1151</div></div>
      <div class="ui-vpp-striped-specs__row"><div>Número de núcleos</div><div>6</div></div>
      <div class="ui-vpp-striped-specs__row"><div>Número de threads</div><div>6</div></div>
    </body></html>
    '''

    def fake_fetch(self, url, interaction_profile=None):
        assert interaction_profile == "mercadolivre"
        return {
            "html": html,
            "text": "Processador Intel Core i5-9400F Comprar agora",
            "final_url": url,
            "blocked": False,
            "surfsky": True,
            "error": None,
        }

    monkeypatch.setattr("src.scrapers.browser_scraper.BrowserScraper.fetch_surfsky", fake_fetch)
    raw = _PartialApiML().collect(
        "https://produto.mercadolivre.com.br/MLB-9999999999-processador-intel-core-i5-9400f-_JM"
    )
    assert raw["source"] == "MERCADO_LIVRE_API_SURFSKY"
    assert raw["price"] == 899.90
    assert raw["image_url"].endswith("cpu.jpg")
    assert len(raw["attributes"]) >= 5
    assert raw["collection_attempts"][0]["modo"] == "SURFSKY_ORIGINAL"
    assert raw["collection_attempts"][0]["erro"] is None
