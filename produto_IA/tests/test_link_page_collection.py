"""Regressões da coleta por link: dados, identidade, limites e isolamento da API."""
import socket
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from src import api
from src.scrapers.generic_scraper import GenericScraper
from src.scrapers.link_page_details import complement_link_page
from src.scrapers.product_page_crawler import ProductPageCrawler
from src.utils.public_http import get_public_page, origin, validate_public_url


URL = "https://loja.example/pc/cb5600"
HTML = '''<link rel="canonical" href="/pc/cb5600"><h1>PC Gamer CB5600</h1>
<meta name="description" content="PC Gamer">
<div id="descricao">Computador com Ryzen 5 5600G, 16 GB DDR4 e SSD NVMe 1 TB.</div>
<div class="specs"><div><span>Modelo</span><span>CB5600</span></div>
<div><b>Memória RAM</b><span>16 GB DDR4</span></div></div>
<meta itemprop="price" content="2999.90"><img itemprop="image" src="/pc.jpg">
<aside class="related"><h1>Outro produto</h1><table><tr><td>RAM</td><td>8 GB</td></tr></table></aside>'''


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("REQUEST_MIN_DELAY_SECONDS", "0")
    monkeypatch.setenv("REQUEST_JITTER_SECONDS", "0")


def response(url, html="", status=200, headers=None):
    value = requests.Response()
    value.url, value.status_code = url, status
    value.headers.update(headers or {"Content-Type": "text/html; charset=utf-8"})
    value._content = html.encode()
    value._content_consumed = True
    value.encoding = "utf-8"
    return value


def test_reads_visible_description_microdata_and_paired_specifications():
    raw = GenericScraper()._parse_html(URL, URL, HTML)
    assert raw["title"] == "PC Gamer CB5600"
    assert "Ryzen 5 5600G" in raw["description"]
    assert raw["model"] == "CB5600"
    assert "Memória RAM: 16 GB DDR4" in raw["attributes_text"]
    assert "RAM: 8 GB" not in raw["attributes_text"]
    assert raw["price"] == 2999.9
    assert raw["image_url"] == "https://loja.example/pc.jpg"


def test_title_alone_triggers_dynamic_details_and_result_is_cached(monkeypatch):
    collector = GenericScraper()
    http = MagicMock(return_value=(response(URL, '<h1>PC Gamer CB5600</h1><meta name="description" content="PC">'), None))
    monkeypatch.setattr(collector, "_http_get", http)
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch", return_value={"html": HTML, "final_url": URL}) as browser:
        raw = collector.collect(URL, crawl=True)
        again = collector.collect(URL, crawl=True)
    assert raw["model"] == "CB5600"
    assert "Ryzen" in raw["description"]
    assert raw["page_scraping_attempted"] is True
    browser.assert_called_once_with(URL, public_only=True, product_details=True)
    assert http.call_count == 1
    assert again["cache_hit"] is True


@pytest.mark.parametrize("no_browser,crawl", [(True, True), (False, False)])
def test_price_only_and_no_browser_do_not_launch_browser(monkeypatch, no_browser, crawl):
    collector = GenericScraper()
    monkeypatch.setattr(collector, "_http_get", lambda *_: (response(URL, "<h1>PC Gamer CB5600</h1>"), None))
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch") as browser:
        assert collector.collect(URL, no_browser=no_browser, crawl=crawl)["title"]
    browser.assert_not_called()


def test_failed_dynamic_read_preserves_static_product(monkeypatch):
    collector = GenericScraper()
    monkeypatch.setattr(collector, "_http_get", lambda *_: (response(URL, "<h1>PC Gamer CB5600</h1>"), None))
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch", side_effect=RuntimeError("browser unavailable")):
        raw = collector.collect(URL, crawl=True)
    assert raw["ok"] is True
    assert raw["collection_attempts"][-1]["erro"] == "RuntimeError"


def test_verification_page_is_not_product_data():
    raw = GenericScraper()._parse_html(URL, URL, "<title>Access denied</title><h1>Captcha</h1>")
    assert not raw["ok"] and raw["blocked"] and raw["requires_local_capture"]
    assert not raw.get("title")


def crawler_for(pages, max_pages=2):
    calls = []
    def fetch(url, same_origin):
        calls.append(url)
        assert same_origin == origin(URL)
        return response(url, pages[url], headers={"Content-Type": "text/plain"} if url.endswith("robots.txt") else None), None
    return ProductPageCrawler(fetch, GenericScraper()._parse_html, time.monotonic() + 30, max_pages), calls


def test_crawl_is_one_level_same_origin_and_preserves_commercial_data():
    linked = "https://loja.example/pc/cb5600/specs"
    crawler, calls = crawler_for({"https://loja.example/robots.txt": "User-agent: *\nAllow: /",
        linked: '<link rel="canonical" href="/pc/cb5600"><dl><dt>Memória</dt><dd>16 GB</dd></dl>'
        '<meta itemprop="price" content="1"><a href="/next">Especificações</a>'})
    html = f'''<a href="{linked}">Ficha técnica</a><a href="https://outra.example/specs">Especificações</a>
        <a href="/search">Descrição</a><a href="#descricao">Descrição</a>
        <div class="related"><a href="/other">Ficha técnica</a></div>'''
    raw = {"title": "PC Gamer CB5600", "url_final": URL, "price": 2999.9, "affiliate_url": "https://afiliado.example/link"}
    result = crawler.collect(raw, html)
    assert calls == ["https://loja.example/robots.txt", linked]
    assert result["crawl"]["urlsAproveitadas"] == [linked]
    assert "Memória: 16 GB" in result["attributes_text"]
    assert result["price"] == 2999.9 and result["affiliate_url"] == raw["affiliate_url"]


def test_different_sku_is_rejected_even_with_same_canonical():
    linked = URL + "/specs"
    crawler, _ = crawler_for({"https://loja.example/robots.txt": "", linked:
        '<link rel="canonical" href="/pc/cb5600"><h1>PC Gamer CB5600</h1><dl><dt>Modelo</dt><dd>CB5700</dd></dl>'})
    result = crawler.collect({"title": "PC Gamer CB5600", "model": "CB5600", "url_final": URL}, f'<a href="{linked}">Ficha técnica</a>')
    assert not result.get("attributes")
    assert result["crawl"]["erros"][-1]["motivo"] == "PRODUTO_NAO_CONFIRMADO"


def test_robots_denial_prevents_link_request():
    crawler, calls = crawler_for({"https://loja.example/robots.txt": "User-agent: *\nDisallow: /pc/"})
    raw = crawler.collect({"title": "PC", "url_final": URL}, '<a href="/pc/specs">Ficha técnica</a>')
    assert calls == ["https://loja.example/robots.txt"]
    assert raw["crawl"]["erros"][0]["motivo"] == "ROBOTS_NAO_PERMITE"


def test_candidate_limit_invalid_urls_and_expired_budget():
    crawler, calls = crawler_for({}, max_pages=1)
    html = '<a href="https://loja.example:invalid/specs">Ficha técnica</a><a href="/a">Descrição</a><a href="/b">Ficha técnica</a>'
    assert crawler.candidates(html, URL) == ["https://loja.example/a"]
    crawler.deadline = time.monotonic() - 1
    assert not crawler.collect({"title": "PC", "url_final": URL}, html)["crawl"]["urlsVisitadas"]
    assert not calls


@pytest.fixture
def public_dns(monkeypatch):
    def resolve(host, port, **_):
        address = host if host in {"127.0.0.1", "169.254.169.254"} else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/x", "https://u:p@loja.example/x", "http://127.0.0.1/x", "http://169.254.169.254/x", "https://loja.example:8080/x"])
def test_public_url_guards(public_dns, url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_redirect_to_private_host_is_never_requested(public_dns):
    session = MagicMock()
    session.get.return_value = response(URL, status=302, headers={"Location": "http://127.0.0.1/admin"})
    with pytest.raises(ValueError, match="ENDERECO_NAO_PUBLICO"):
        get_public_page(session, URL, timeout=2, deadline=time.monotonic() + 5, rate_limiter=MagicMock())
    assert session.get.call_count == 1


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_, **__: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
    ])
    with pytest.raises(ValueError, match="ENDERECO_NAO_PUBLICO"):
        validate_public_url(URL)


def test_extra_page_redirect_cannot_leave_original_origin(public_dns):
    session = MagicMock()
    session.get.return_value = response(URL, status=302, headers={"Location": "https://outra.example/specs"})
    with pytest.raises(ValueError, match="REDIRECIONAMENTO_FORA_DA_ORIGEM"):
        get_public_page(session, URL, timeout=2, deadline=time.monotonic() + 5, rate_limiter=MagicMock(), same_origin=origin(URL))
    assert session.get.call_count == 1


def test_missing_robots_allows_details_but_unavailable_robots_does_not():
    collector = GenericScraper()
    def collect_with_status(status):
        calls = []
        def fetch(url, *_):
            calls.append(url)
            if url.endswith("robots.txt"):
                return None, requests.HTTPError(response=response(url, status=status))
            return response(url, '<link rel="canonical" href="/pc/cb5600"><dl><dt>RAM</dt><dd>16 GB</dd></dl>'), None
        crawler = ProductPageCrawler(fetch, collector._parse_html, time.monotonic() + 5)
        result = crawler.collect({"title": "PC", "url_final": URL}, '<a href="/specs">Ficha técnica</a>')
        return result, calls
    allowed, calls = collect_with_status(404)
    assert len(calls) == 2 and allowed["attributes"]
    unavailable, calls = collect_with_status(503)
    assert len(calls) == 1 and not unavailable.get("attributes")


@pytest.mark.parametrize("headers,html,max_bytes,reason", [
    ({"Content-Type": "application/pdf"}, "data", 100, "CONTEUDO_NAO_HTML"),
    ({"Content-Type": "text/html"}, "a" * 101, 100, "PAGINA_MUITO_GRANDE"),
])
def test_http_content_and_size_limits(public_dns, headers, html, max_bytes, reason):
    session = MagicMock()
    session.get.return_value = response(URL, html, headers=headers)
    with pytest.raises(ValueError, match=reason):
        get_public_page(session, URL, timeout=2, deadline=time.monotonic() + 5, rate_limiter=MagicMock(), max_bytes=max_bytes)


def official_shopee():
    return {"ok": True, "source": "SHOPEE_AFFILIATE_API", "api_used": True,
        "title": "PC Gamer", "description": None, "attributes": [], "url_original": "https://shopee.com.br/product/123/456",
        "url_final": "https://shopee.com.br/product/123/456", "price": 2999.9,
        "affiliate_url": "https://shopee.com.br/afiliado", "item_id": "456", "shop_id": "123"}


def test_api_keeps_official_price_and_affiliate_while_page_supplies_specs(monkeypatch):
    seed = official_shopee()
    monkeypatch.setattr(api, "_shopee_api_raw", lambda _: (seed, []))
    monkeypatch.setattr(api, "auto_enrich_link_result", lambda value: value)
    page = {"ok": True, "url_final": seed["url_final"], "title": "PC Gamer CB5600", "description": "PC Gamer Ryzen 5 5600G com SSD 1 TB",
        "attributes": [{"name": "Memória", "value_name": "16 GB DDR4"}], "price": 1,
        "image_url": "https://loja.example/pc.jpg", "affiliate_url": "https://evil.example/link", "page_scraping_attempted": True}
    with patch.object(GenericScraper, "collect", return_value=page) as collect:
        result = api._analyze_sync(api.AnalyzeRequest(url=seed["url_final"], categoria="PC_MONTADO", detalharPagina=True))
    collect.assert_called_once_with(seed["url_final"], no_browser=False, crawl=True)
    assert result["ofertaColetada"]["preco"] == 2999.9
    assert result["ofertaColetada"]["urlAfiliada"] == seed["affiliate_url"]
    assert "Ryzen 5 5600G" in result["payloadParcialBackend"]["descricao"]
    assert result["politicaColeta"]["scrapingComplementarExecutado"]


@pytest.mark.parametrize("page", [
    {"ok": False, "blocked": True},
    {"ok": True, "url_final": "https://shopee.com.br/product/123/999", "description": "Dados de outro produto"},
])
def test_blocked_or_wrong_shopee_product_keeps_official_partial_data(page):
    seed = official_shopee()
    with patch.object(GenericScraper, "collect", return_value=page):
        result = complement_link_page(seed, seed["url_final"])
    assert result["price"] == seed["price"] and result["title"] == seed["title"]
    assert not result.get("description")
    assert result["page_scraping_attempted"]


def test_commercial_api_does_not_run_complementary_scraping(monkeypatch):
    seed = official_shopee()
    monkeypatch.setattr(api, "_shopee_api_raw", lambda _: (seed, []))
    with patch.object(GenericScraper, "collect") as collect:
        result = api._analyze_sync(api.AnalyzeRequest(url=seed["url_final"]))
    collect.assert_not_called()
    assert not result["politicaColeta"]["scrapingComplementarExecutado"]


def test_generic_admin_link_is_collected_only_once():
    page = GenericScraper()._parse_html(URL, URL, HTML)
    page["page_scraping_attempted"] = True
    with patch.object(GenericScraper, "collect", return_value=page) as collect:
        result = api._analyze_sync(api.AnalyzeRequest(url=URL, noBrowser=True, detalharPagina=True))
    collect.assert_called_once_with(URL, no_browser=True, crawl=True)
    assert result["payloadParcialBackend"]["nome"] == page["title"]


def test_browser_validates_requests_and_only_clicks_product_detail_controls(public_dns):
    from src.scrapers.browser_scraper import BrowserScraper
    page = MagicMock()
    page.url = URL
    page.title.return_value = "PC Gamer CB5600"
    page.content.return_value = HTML
    page.locator.return_value.inner_text.return_value = "PC Gamer"
    control = MagicMock()
    control.is_visible.return_value = True
    page.get_by_role.return_value.all.return_value = [control]
    context = MagicMock()
    context.new_page.return_value = page
    browser = MagicMock()
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch.return_value = browser
    collector = BrowserScraper()
    collector.rate_limiter = MagicMock()
    with patch("src.scrapers.browser_scraper.sync_playwright") as launch:
        launch.return_value.__enter__.return_value = playwright
        assert collector.fetch(URL, public_only=True, product_details=True)["html"] == HTML
    route_handler = context.route.call_args.args[1]
    route = SimpleNamespace(request=SimpleNamespace(url="http://127.0.0.1/admin", resource_type="document"), abort=MagicMock(), continue_=MagicMock())
    route_handler(route)
    route.abort.assert_called_once()
    route.continue_.assert_not_called()
    assert browser.new_context.call_args.kwargs["service_workers"] == "block"
    assert control.click.called
    assert page.get_by_role.call_args_list[0].kwargs["name"].fullmatch("Ficha técnica")
    assert not page.get_by_role.call_args_list[0].kwargs["name"].fullmatch("Comprar")
    context.close.assert_called_once()
    browser.close.assert_called_once()
