from src.main import build_result
from src.scrapers.magazine_scraper import MagazineScraper


URL = (
    "https://www.magazinevoce.com.br/magazinecriabyte/"
    "placa-de-video-xfx-swift-rx-9070-xt/p/ea444h39dd/in/pcvd/?seller_id=kabum"
)


def test_v14_4_detecta_az_request_verify_e_texto_real():
    assert MagazineScraper._is_access_error_page(
        "Verificação",
        "Parece que você acessou nosso site de uma forma um pouco diferente do comum. "
        "Para sua segurança precisamos de uma verificação rápida.",
        "https://www.magazinevoce.com.br/az-request-verify?url=x",
    )


def test_v14_4_monta_url_publica_equivalente_magazineluiza():
    converted = MagazineScraper._magazineluiza_equivalent_url(URL)
    assert converted.startswith("https://www.magazineluiza.com.br/placa-de-video-xfx-swift-rx-9070-xt/")
    assert "/p/ea444h39dd/in/pcvd/" in converted
    assert "seller_id=kabum" in converted


def test_v14_4_resultado_bloqueado_nao_transforma_verificacao_em_produto():
    raw = {
        "ok": False,
        "blocked": True,
        "requires_local_capture": True,
        "source": "MAGALU_BLOQUEADO",
        "url_original": URL,
        "url_final": URL,
        "title": "Parece que você acessou nosso site de uma forma um pouco diferente do comum",
        "brand": None,
        "model": None,
        "error": "MAGALU_COLETA_BLOQUEADA",
        "collection_attempts": [{"modo": "HTTP_ORIGINAL", "bloqueado": True}],
    }
    result = build_result(raw, "PLACA_VIDEO")
    assert result["payloadParcialBackend"]["nome"] is None
    assert result["payloadParcialBackend"]["marca"] is None
    assert result["erro"] == "MAGALU_COLETA_BLOQUEADA"
    assert result["marketplace"]["plataforma"] == "MAGALU"
    assert result["marketplace"]["bloqueadoNoNavegador"] is True
    assert result["marketplace"]["capturaLocalNecessaria"] is True


def test_v14_4_coleta_tenta_url_alternativa_quando_original_bloqueia(monkeypatch):
    scraper = MagazineScraper()
    monkeypatch.setattr(scraper.cache, "get", lambda *a, **k: None)
    monkeypatch.setattr(scraper.cache, "set", lambda *a, **k: None)

    calls = []

    def fake_http(original_url, candidate_url, source):
        calls.append(("http", candidate_url, source))
        if "magazinevoce.com.br" in candidate_url:
            return None, None, True
        return {
            "ok": True,
            "title": "Placa de Vídeo XFX RX 9070 XT",
            "brand": "XFX",
            "model": "RX 9070 XT",
            "mpn": "RX-97TSWF3W9",
            "url_original": original_url,
            "url_final": candidate_url,
            "source": source,
            "blocked": False,
            "description": "Produto",
        }, None, False

    def fake_browser(original_url, candidate_url, source):
        calls.append(("browser", candidate_url, source))
        return None, None, True

    monkeypatch.setattr(scraper, "_try_http_product", fake_http)
    monkeypatch.setattr(scraper, "_try_browser_product", fake_browser)

    result = scraper.collect(URL, no_browser=False)
    assert result["ok"] is True
    assert result["source"] == "MAGALU_URL_ALTERNATIVA_HTTP"
    assert "magazineluiza.com.br" in result["url_final"]
    assert [c[0] for c in calls] == ["http", "browser", "http"]
