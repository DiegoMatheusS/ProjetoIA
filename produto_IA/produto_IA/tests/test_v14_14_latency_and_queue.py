from src.enrichment.core import TechnicalEnricher, should_auto_enrich
from src.extractors.backend_schemas import SCHEMAS, REQUIRED
from src.scrapers.magazine_scraper import MagazineScraper


MAGALU_URL = (
    "https://www.magazinevoce.com.br/magazinecriabyte/"
    "placa-de-video-xfx-swift-rx-9070-xt/p/ea444h39dd/in/pcvd/?seller_id=kabum"
)


def test_v14_14_auto_enrichment_is_bounded_and_does_not_open_extra_cloud_browsers(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_AUTO_MAX_SOURCES", "3")
    enricher = TechnicalEnricher(auto_mode=True)
    assert enricher.max_sources == 3
    assert all(getattr(provider, "allow_browser_fallback", True) is False for provider in enricher.providers)
    assert all(getattr(provider.resolver, "allow_browser_fallback", True) is False for provider in enricher.providers)


def test_v14_14_does_not_auto_enrich_high_coverage_when_required_fields_present(monkeypatch):
    category = "PLACA_VIDEO"
    expected = list(SCHEMAS[category][2])
    required = list(REQUIRED.get(category, []))
    specs = {name: 1 for name in expected}
    # Deixa uma lacuna opcional, mantendo cobertura alta e obrigatórios presentes.
    optional = next((name for name in expected if name not in required), None)
    if optional:
        specs.pop(optional, None)
    result = {
        "categoriaDetectada": category,
        "payloadParcialBackend": {
            "nome": "Placa de Video XFX Swift RX 9070 XT",
            "marca": "XFX",
            "modelo": "Swift RX 9070 XT",
            "mpn": "RX-97TSWF3W9",
        },
        "especificacoesEncontradas": specs,
    }
    monkeypatch.setenv("ENRICHMENT_AUTO_MIN_COVERAGE", "0.45")
    assert should_auto_enrich(result) is False


def test_v14_14_magalu_tries_surfsky_before_railway_browser(monkeypatch):
    scraper = MagazineScraper()
    monkeypatch.setenv("SURFSKY_TOKEN", "fake")
    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper.cache, "set", lambda *a, **k: None)

    order = []

    def fake_http(original_url, candidate_url, source):
        order.append("http")
        return None, None, True

    def fake_surfsky(original_url, candidate_url, source):
        order.append("surfsky")
        return {
            "ok": True,
            "title": "Placa de Video XFX Swift RX 9070 XT",
            "brand": "XFX",
            "model": "Swift RX 9070 XT",
            "mpn": "RX-97TSWF3W9",
            "description": "Produto",
            "url_original": original_url,
            "url_final": candidate_url,
            "source": source,
            "blocked": False,
        }, None, False

    def fake_browser(*args, **kwargs):
        order.append("railway_browser")
        raise AssertionError("Chromium da Railway não deve vir antes do Surfsky")

    monkeypatch.setattr(scraper, "_try_http_product", fake_http)
    monkeypatch.setattr(scraper, "_try_surfsky_product", fake_surfsky)
    monkeypatch.setattr(scraper, "_try_browser_product", fake_browser)

    result = scraper.collect(MAGALU_URL)
    assert result["ok"] is True
    assert order[:2] == ["http", "surfsky"]
    assert "railway_browser" not in order
