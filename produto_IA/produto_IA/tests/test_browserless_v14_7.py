import os
from unittest.mock import patch

from src.scrapers.browser_scraper import BrowserScraper
from src.scrapers.magazine_scraper import MagazineScraper


def test_browserless_configured_depends_on_token():
    with patch.dict(os.environ, {}, clear=True):
        assert BrowserScraper().browserless_configured() is False
    with patch.dict(os.environ, {"BROWSERLESS_TOKEN": "abc"}, clear=True):
        assert BrowserScraper().browserless_configured() is True


def test_magalu_uses_browserless_after_cloud_block(monkeypatch):
    scraper = MagazineScraper()
    url = "https://www.magazinevoce.com.br/loja/produto/p/abc123/in/pcvd/?seller_id=kabum"

    monkeypatch.setattr(scraper, "_try_http_product", lambda *a, **k: (None, None, True))
    monkeypatch.setattr(scraper, "_try_browser_product", lambda *a, **k: (None, None, True))
    monkeypatch.setattr(scraper, "_magazineluiza_candidate_urls", lambda _u: [])
    expected = {
        "ok": True,
        "title": "Placa de Video XFX RX 9070 XT",
        "source": "MAGALU_BROWSERLESS_RESIDENCIAL",
        "url_original": url,
        "url_final": url,
        "price": 5694.10,
    }
    monkeypatch.setattr(scraper, "_try_browserless_product", lambda *a, **k: (dict(expected), None, False))
    monkeypatch.setattr(scraper, "_cacheable_result", lambda result: bool(result and result.get("ok")))
    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper.cache, "set", lambda *a, **k: None)

    result = scraper.collect(url)
    assert result["ok"] is True
    assert result["source"] == "MAGALU_BROWSERLESS_RESIDENCIAL"
    assert result["tentativasColeta"][-1]["modo"] == "BROWSERLESS_ORIGINAL"


def test_magalu_does_not_call_browserless_when_no_browser(monkeypatch):
    scraper = MagazineScraper()
    url = "https://www.magazinevoce.com.br/loja/produto/p/abc123/in/pcvd/"
    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper, "_try_http_product", lambda *a, **k: (None, None, True))
    monkeypatch.setattr(scraper, "_magazineluiza_candidate_urls", lambda _u: [])
    called = {"value": False}
    def remote(*a, **k):
        called["value"] = True
        return None, None, True
    monkeypatch.setattr(scraper, "_try_browserless_product", remote)
    result = scraper.collect(url, no_browser=True)
    assert called["value"] is False
    assert result["error"] == "MAGALU_COLETA_BLOQUEADA"
