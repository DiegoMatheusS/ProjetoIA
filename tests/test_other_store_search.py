import base64
import threading
import time

import pytest

from src.enrichment.search import WebSearchResolver
from src.offers import identical_product_router as offers
from src.offers.store_candidates import StoreCandidates, is_product_url, listing_candidates


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ML_ACCESS_TOKEN", "")


@pytest.mark.parametrize("url", [
    "https://www.magazineluiza.com.br/placa/p/123456/",
    "https://produto.mercadolivre.com.br/MLB-123456789-placa",
])
def test_bing_redirect_is_decoded_before_domain_filter(url):
    encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    html = f'<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1{encoded}&amp;ntb=1">RTX 4060</a></h2></li>'
    resolver = WebSearchResolver()
    domain = "magazineluiza.com.br" if "magazineluiza" in url else "mercadolivre.com.br"
    assert resolver._candidates_from_html(html, [domain]) == [{"url": url, "title": "RTX 4060"}]
    assert resolver._decode_ddg_url(f"/ck/a?u=a1{encoded}") == url


@pytest.mark.parametrize("href", [
    "https://www.bing.com/ck/a?u=a1!!!",
    "https://www.bing.com/ck/a?u=javascript:alert(1)",
    "https://duckduckgo.com/l/?uddg=javascript:alert(1)",
    "https://magazineluiza.com.br.evil.example/placa/p/123/",
])
def test_redirects_and_foreign_hosts_cannot_be_product_candidates(href):
    assert WebSearchResolver()._candidates_from_html(f'<a href="{href}">Produto</a>', ["magazineluiza.com.br"]) == []


def test_search_cache_does_not_truncate_larger_subsequent_search(monkeypatch):
    resolver = WebSearchResolver()
    calls = []
    def search(query, domains, limit):
        calls.append(limit)
        return [{"url": f"https://www.magazineluiza.com.br/p/{i}/", "title": str(i)} for i in range(limit)]
    monkeypatch.setattr(resolver, "_results_uncached", search)
    assert len(resolver.results("RTX4060", ["magazineluiza.com.br"], 1)) == 1
    assert len(resolver.results("RTX4060", ["magazineluiza.com.br"], 6)) == 6
    resolver.results("RTX4060", ["magazineluiza.com.br"], 6)
    assert calls == [3, 6]


def test_queries_keep_model_and_sku_after_sixth_word():
    payload = offers.IdenticalProductOffersRequest(nome="Placa de vídeo Zotac Gaming Twin Edge RTX 4060 8GB", marca="Zotac", modelo="RTX 4060", mpn="ZT-D40600E-10M", gtin="4895173627130")
    queries = offers._identity_queries(payload)
    assert queries[0] == "Zotac ZT-D40600E-10M"
    assert "Zotac RTX 4060" in queries
    assert "4895173627130" in queries
    assert offers._query(payload) in queries


@pytest.mark.parametrize("store,base,url", [
    ("MAGALU", "https://www.magazineluiza.com.br/busca/ssd/", "https://www.magazineluiza.com.br/ssd/p/123456/"),
    ("MERCADO_LIVRE", "https://lista.mercadolivre.com.br/ssd", "https://produto.mercadolivre.com.br/MLB-123456789-ssd"),
])
def test_native_listing_discovers_products_without_trusting_snippet_prices(store, base, url):
    html = f'<a href="{url}">Produto R$ 1</a><a href="{url}#top">Duplicado</a><a href="https://evil.example/p/123/">Outro</a><a href="/busca/ssd/">Busca</a>'
    assert listing_candidates(html, base, store, 6) == [{"url": url}]


def test_magalu_next_data_product_links_are_supported():
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"products":[{"url":"/ssd/p/123456/"}]}}</script>'
    assert listing_candidates(html, "https://www.magazineluiza.com.br/busca/ssd/", "MAGALU", 3)[0]["url"] == "https://www.magazineluiza.com.br/ssd/p/123456/"


def test_mercado_livre_id_in_search_query_does_not_make_it_a_product_page():
    assert not is_product_url("MERCADO_LIVRE", "https://lista.mercadolivre.com.br/busca?q=MLB123456789")
    assert is_product_url("MERCADO_LIVRE", "https://www.mercadolivre.com.br/ssd/p/MLB123456789")


def test_mercado_livre_api_uses_authenticated_search_and_normalizes_identity(monkeypatch):
    discovery = StoreCandidates("MERCADO_LIVRE", time.monotonic() + 30)
    discovery.ml.token = "test-token"
    calls = []
    def request(path, params=None, use_auth=True):
        calls.append((path, params, use_auth))
        return {"results": [{"id": "MLB123456789", "permalink": "https://produto.mercadolivre.com.br/MLB-123456789-ssd", "title": "SSD Kingston NV3 1TB", "price": 399.9, "currency_id": "BRL", "available_quantity": 2, "seller": {"id": 77}, "attributes": [{"id": "BRAND", "value_name": "Kingston"}, {"id": "MPN", "value_name": "SNV3S/1000G"}]}]}, None
    monkeypatch.setattr(discovery.ml, "_request_get", request)
    candidates, status = discovery.api_results("Kingston SNV3S/1000G", 3)
    assert calls == [("/sites/MLB/search", {"q": "Kingston SNV3S/1000G", "limit": 20}, True)]
    assert status == "ENCONTRADO"
    raw = candidates[0]["raw"]
    assert raw["mpn"] == "SNV3S/1000G" and raw["price"] == 399.9
    assert raw["api_used"] and raw["seller_id"] == 77


def test_denied_api_is_reported_without_anonymous_retry(monkeypatch):
    discovery = StoreCandidates("MERCADO_LIVRE", time.monotonic() + 30)
    discovery.ml.token = "test-token"
    calls = []
    monkeypatch.setattr(discovery.ml, "_request_get", lambda *args, **kwargs: (calls.append(kwargs.get("use_auth")) or None, "HTTP 403"))
    assert discovery.api_results("SSD", 3) == ([], "BLOQUEADO")
    assert calls == [True]


@pytest.mark.parametrize("store", ["MAGALU", "MERCADO_LIVRE"])
def test_native_store_search_returns_confirmed_offer_even_without_web_results(monkeypatch, store):
    url = "https://www.magazineluiza.com.br/ssd/p/123456/" if store == "MAGALU" else "https://produto.mercadolivre.com.br/MLB-123456789-ssd"
    calls = []
    class Discovery:
        def __init__(self, *args):
            pass
        def api_results(self, *args):
            return [], "NAO_CONFIGURADA"
        def listing_results(self, query, limit):
            calls.append(query)
            return [{"url": url}], "ENCONTRADO"
        def collect(self, requested):
            assert requested == url
            return {"ok": True, "url_final": url, "title": "SSD Kingston NV3 1TB", "brand": "Kingston", "mpn": "SNV3S/1000G", "price": 399.9, "currency": "BRL", "available": True}
    monkeypatch.setattr(offers, "StoreCandidates", Discovery)
    monkeypatch.setattr(WebSearchResolver, "results", lambda *args, **kwargs: pytest.fail("Confirmed native offer does not need web search"))
    payload = offers.IdenticalProductOffersRequest(nome="SSD Kingston NV3 1TB", marca="Kingston", mpn="SNV3S/1000G")
    found, diag = offers._search_web_store(payload, store, [], 1)
    assert found[0]["preco"] == 399.9 and found[0]["criterioIdentidade"] == "MPN_MARCA"
    assert calls == ["Kingston SNV3S/1000G"]
    assert diag["encontrados"] == 1 and diag["statusBusca"] == "ENCONTRADO"


@pytest.mark.parametrize("raw", [
    {"price": float("nan")}, {"price": float("inf")}, {"price": -10},
    {"price": 10, "available": False}, {"price": 10, "currency": "USD"},
    {"price": 10, "url_final": "https://evil.example/ssd/p/123456/"},
])
def test_invalid_prices_unavailable_products_and_foreign_redirects_are_rejected(raw):
    assert offers._normalize_web_offer("MAGALU", raw, "GTIN", "https://www.magazineluiza.com.br/ssd/p/123456/") is None


def test_timeout_preserves_completed_and_partial_store_offers(monkeypatch):
    done = threading.Event()
    monkeypatch.setenv("IDENTICAL_OFFERS_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr(offers, "_validate_api_key", lambda key: None)
    def search(payload, store, domains, limit, deadline, progress):
        offer = {"marketplace": store, "urlOriginal": f"https://example.com/{store}", "preco": 100}
        if store == "MAGALU":
            progress.update(ofertas=[offer], diagnostico={"encontrados": 1, "verificados": 1})
            done.wait(2)
        return [offer], {"encontrados": 1}
    monkeypatch.setattr(offers, "_search_web_store", search)
    monkeypatch.setattr(offers, "_search_shopee", lambda *args: ([], {"encontrados": 0}))
    started = time.monotonic()
    try:
        result = offers.find_identical_product_offers(offers.IdenticalProductOffersRequest(nome="SSD Kingston NV3", modelo="SNV3S/1000G"))
        assert time.monotonic() - started < 1.8
        assert result["quantidade"] == 2
        assert result["fontes"]["magalu"]["statusBusca"] == "TEMPO_LIMITE"
        assert result["fontes"]["magalu"]["encontrados"] == 1
    finally:
        done.set()


def test_late_store_error_preserves_already_confirmed_offers(monkeypatch):
    monkeypatch.setattr(offers, "_validate_api_key", lambda key: None)
    def search(payload, store, domains, limit, deadline, progress):
        if store == "MAGALU":
            progress.update(ofertas=[{"marketplace": store, "urlOriginal": "https://www.magazineluiza.com.br/ssd/p/123456/", "preco": 100}], diagnostico={"encontrados": 1})
            raise ValueError("unexpected response")
        return [], {"encontrados": 0}
    monkeypatch.setattr(offers, "_search_web_store", search)
    monkeypatch.setattr(offers, "_search_shopee", lambda *args: ([], {"encontrados": 0}))
    result = offers.find_identical_product_offers(offers.IdenticalProductOffersRequest(nome="SSD Kingston NV3", modelo="SNV3S/1000G"))
    assert result["quantidade"] == 1
    assert result["fontes"]["magalu"]["statusBusca"] == "ERRO"
    assert result["fontes"]["magalu"]["encontrados"] == 1
