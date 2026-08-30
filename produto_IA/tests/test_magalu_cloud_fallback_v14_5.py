from src.scrapers.magazine_scraper import MagazineScraper

URL = (
    "https://www.magazinevoce.com.br/magazinecriabyte/"
    "placa-de-video-xfx-swift-rx-9070-xt/p/ea444h39dd/in/pcvd/?seller_id=kabum"
)


def test_v14_5_gera_variantes_publicas_magalu():
    candidates = MagazineScraper._magazineluiza_candidate_urls(URL)
    modes = [mode for mode, _ in candidates]
    urls = dict(candidates)
    assert "MAGAZINELUIZA" in modes
    assert "MAGAZINELUIZA_SEM_SELLER" in modes
    assert "MAGAZINELUIZA_MOBILE" in modes
    assert "MAGAZINELUIZA_MOBILE_SEM_SELLER" in modes
    assert "seller_id=kabum" in urls["MAGAZINELUIZA"]
    assert "seller_id=" not in urls["MAGAZINELUIZA_SEM_SELLER"]
    assert urls["MAGAZINELUIZA_MOBILE"].startswith("https://m.magazineluiza.com.br/")


def test_v14_5_tenta_mobile_quando_desktop_falha(monkeypatch):
    scraper = MagazineScraper()
    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper.cache, "set", lambda *a, **k: None)

    calls = []

    def fake_http(original_url, candidate_url, source):
        calls.append(("http", candidate_url, source))
        if candidate_url.startswith("https://m.magazineluiza.com.br/"):
            return {
                "ok": True,
                "title": "Placa de Vídeo XFX RX 9070 XT",
                "brand": "XFX",
                "model": "RX 9070 XT",
                "url_original": original_url,
                "url_final": candidate_url,
                "source": source,
                "blocked": False,
                "description": "Produto",
            }, None, False
        return None, None, "magazinevoce.com.br" in candidate_url

    def fake_browser(*args, **kwargs):
        calls.append(("browser", args[1], args[2]))
        return None, None, True

    monkeypatch.setattr(scraper, "_try_http_product", fake_http)
    monkeypatch.setattr(scraper, "_try_browser_product", fake_browser)

    result = scraper.collect(URL, no_browser=False)
    assert result["ok"] is True
    assert result["url_final"].startswith("https://m.magazineluiza.com.br/")
    assert any(c[1].startswith("https://m.magazineluiza.com.br/") for c in calls if c[0] == "http")
