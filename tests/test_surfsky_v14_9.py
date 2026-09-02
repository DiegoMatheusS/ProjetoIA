import os
from unittest.mock import patch

from src.scrapers.browser_scraper import BrowserScraper
from src.scrapers.magazine_scraper import MagazineScraper


URL = "https://www.magazinevoce.com.br/magazinecriabyte/produto/p/abc123/in/pcvd/"


def test_surfsky_configured_depends_on_token():
    with patch.dict(os.environ, {}, clear=True):
        assert BrowserScraper().surfsky_configured() is False
    with patch.dict(os.environ, {"SURFSKY_TOKEN": "abc"}, clear=True):
        assert BrowserScraper().surfsky_configured() is True


def test_surfsky_missing_token_is_explicit():
    with patch.dict(os.environ, {}, clear=True):
        r = BrowserScraper().fetch_surfsky("https://example.com")
    assert r["error"] == "SURFSKY_NAO_CONFIGURADO"
    assert r["surfsky"] is True


def test_surfsky_401_is_reported_without_token(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = '{"success":false,"msg":"Invalid API token"}'

    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers or {}
        return FakeResponse()

    monkeypatch.setattr("src.scrapers.browser_scraper.requests.post", fake_post)
    with patch.dict(
        os.environ,
        {
            "SURFSKY_TOKEN": "segredo-teste",
            "SURFSKY_API_URL": "https://api-de2.surfsky.io",
            "SURFSKY_PROXY_COUNTRY": "br",
        },
        clear=True,
    ):
        r = BrowserScraper().fetch_surfsky("https://example.com")

    assert r["error"].startswith("Surfsky API HTTP 401")
    assert "segredo-teste" not in r["error"]
    assert seen["url"] == "https://api-de2.surfsky.io/profiles/one_time"
    assert seen["headers"]["X-Cloud-Api-Token"] == "segredo-teste"


def test_magalu_uses_surfsky_after_cloud_block(monkeypatch):
    scraper = MagazineScraper()

    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper.cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(scraper, "_try_http_product", lambda *a, **k: (None, None, True))
    monkeypatch.setattr(scraper, "_try_browser_product", lambda *a, **k: (None, None, True))
    monkeypatch.setattr(scraper, "_magazineluiza_candidate_urls", lambda *a, **k: [])
    monkeypatch.setattr(BrowserScraper, "surfsky_configured", lambda self: True)
    monkeypatch.setattr(BrowserScraper, "browserless_configured", lambda self: False)

    expected = {
        "ok": True,
        "source": "MAGALU_SURFSKY_CLOUD",
        "title": "Placa de Video XFX",
        "price": 5694.10,
    }
    monkeypatch.setattr(scraper, "_try_surfsky_product", lambda *a, **k: (dict(expected), None, False))

    result = scraper.collect(URL)
    assert result["ok"] is True
    assert result["source"] == "MAGALU_SURFSKY_CLOUD"
    assert result["tentativasColeta"][-1]["modo"] == "SURFSKY_ORIGINAL"
