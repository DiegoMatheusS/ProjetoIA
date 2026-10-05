"""HTML de lojas, dados dinâmicos e isolamento dos campos comerciais."""
import json
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.scrapers.generic_scraper import GenericScraper
from src.scrapers.link_page_details import complement_link_page
from src.scrapers.storefront_html import storefront_fields


AMAZON = "https://www.amazon.com.br/dp/B0TEST1234"
ML = "https://produto.mercadolivre.com.br/MLB-123456-placa"
MAGALU = "https://www.magazineluiza.com.br/placa/p/123456/"


def parse(url, html):
    return GenericScraper()._parse_html(url, url, html)


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("REQUEST_MIN_DELAY_SECONDS", "0")
    monkeypatch.setenv("REQUEST_JITTER_SECONDS", "0")


def test_amazon_reads_current_html_without_old_price_selector():
    raw = parse(AMAZON, '''
      <span id="productTitle">Placa Zotac RTX 4060</span>
      <div id="corePriceDisplay_desktop_feature_div">
        <span class="a-price a-text-price"><span class="a-offscreen">R$ 2.299,90</span></span>
        <span class="a-price"><span class="a-offscreen">R$ 1.999,90</span></span>
      </div>
      <img id="landingImage" src="/thumb.jpg" data-old-hires="https://cdn.test/foto.jpg?width=1500">
      <aside><span class="priceToPay"><span class="a-offscreen">R$ 99,90</span></span></aside>
    ''')
    assert raw["title"] == "Placa Zotac RTX 4060"
    assert raw["price"] == 1999.9
    assert raw["price_source"] == "HTML_AMAZON"
    assert raw["image_url"] == "https://cdn.test/foto.jpg?width=1500"


def test_amazon_chooses_largest_dynamic_image():
    raw = parse(AMAZON, '''<span id="productTitle">Produto</span>
      <img id="landingImage" src="data:image/gif;base64,x"
        data-a-dynamic-image='{"https://cdn.test/small.jpg":[200,200],"https://cdn.test/large.jpg":[1200,900]}'>''')
    assert raw["image_url"] == "https://cdn.test/large.jpg"


def test_legacy_amazon_price_remains_supported():
    assert parse(AMAZON, '<span id="productTitle">Produto</span><span id="priceblock_ourprice">R$ 129,90</span>')["price"] == 129.9


def test_mercado_livre_reads_fraction_cents_and_lazy_image():
    raw = parse(ML, '''<h1 class="ui-pdp-title">Placa Zotac RTX 4060</h1>
      <div class="ui-pdp-price__second-line"><span class="andes-money-amount">
        <span class="andes-money-amount__fraction">1.999</span><span class="andes-money-amount__cents">90</span>
      </span></div><div class="ui-pdp-gallery"><img src="/tiny.jpg" data-zoom="//http2.mlstatic.com/foto.webp"></div>''')
    assert raw["price"] == 1999.9
    assert raw["price_source"] == "HTML_MERCADO_LIVRE"
    assert raw["image_url"] == "https://http2.mlstatic.com/foto.webp"


def test_magalu_reads_the_main_price_and_image():
    raw = parse(MAGALU, '''<h1 data-testid="heading-product-title">Samsung Galaxy S25</h1>
      <p data-testid="price-value">R$ 3.599,00</p>
      <div data-testid="image-selected-thumbnail"><img data-src="/celular.jpg"></div>''')
    assert raw["price"] == 3599
    assert raw["image_url"] == "https://www.magazineluiza.com.br/celular.jpg"


def test_structured_price_and_image_keep_priority_over_html():
    product = {"@type": "Product", "name": "Produto", "image": "https://cdn.test/oficial.jpg", "offers": {"price": 1299.9}}
    raw = parse(AMAZON, '<script type="application/ld+json">' + json.dumps(product) + '</script><span id="priceblock_ourprice">R$ 999,90</span><img id="landingImage" src="/outra.jpg">')
    assert raw["price"] == 1299.9
    assert raw["price_source"] == "JSON_LD"
    assert raw["image_url"] == "https://cdn.test/oficial.jpg"


@pytest.mark.parametrize("price", ["12x de R$ 99,90 sem juros", "R$ 1.299,90 ou R$ 1.199,90", "", "R$ 0,00"])
def test_installments_ambiguous_and_invalid_prices_are_not_totals(price):
    assert parse(AMAZON, f'<span id="productTitle">Produto</span><span id="priceblock_ourprice">{price}</span>')["price"] is None


def test_invalid_image_and_malformed_dynamic_json_are_ignored():
    raw = parse(AMAZON, '<span id="productTitle">Produto</span><img id="landingImage" src="javascript:alert(1)" data-a-dynamic-image="broken">')
    assert raw["image_url"] is None


def test_does_not_use_store_selectors_on_lookalike_domains():
    soup = BeautifulSoup('<span id="priceblock_ourprice">R$ 99,90</span>', "html.parser")
    assert storefront_fields(soup, "https://amazon.com.br.evil.test/produto") == {}


def test_blocked_page_does_not_become_a_product():
    raw = parse(AMAZON, '<h1>Robot Check</h1><span id="productTitle">Produto</span><span id="priceblock_ourprice">R$ 99,90</span>')
    assert raw["ok"] is False
    assert raw["blocked"] is True
    assert raw.get("price") is None


def test_browser_completes_missing_image_and_price_on_same_product(monkeypatch):
    scraper = GenericScraper()
    static = '<h1>Produto CB5600</h1><div id="description">Descrição do produto.</div><table><tr><th>Modelo</th><td>CB5600</td></tr></table>'
    dynamic = static + '<meta itemprop="price" content="1999.90"><img itemprop="image" src="/foto.jpg">'
    monkeypatch.setattr(scraper, "_http_get", lambda *_: (None, None))
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch", return_value={"html": dynamic, "final_url": ML}) as browser:
        raw = scraper.collect(ML, crawl=True, initial_page={"html": static, "final_url": ML})
    assert raw["price"] == 1999.9
    assert raw["image_url"] == "https://produto.mercadolivre.com.br/foto.jpg"
    browser.assert_called_once()


def test_browser_never_overwrites_price_from_initial_page(monkeypatch):
    scraper = GenericScraper()
    static = '<h1>Produto CB5600</h1><meta itemprop="price" content="1599.90">'
    dynamic = '<h1>Produto CB5600</h1><meta itemprop="price" content="2999.90"><img itemprop="image" src="/foto.jpg">'
    monkeypatch.setattr(scraper, "_http_get", lambda *_: (None, None))
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch", return_value={"html": dynamic, "final_url": ML}):
        raw = scraper.collect(ML, crawl=True, initial_page={"html": static, "final_url": ML})
    assert raw["price"] == 1599.9


def test_browser_does_not_fill_price_from_a_different_product(monkeypatch):
    scraper = GenericScraper()
    monkeypatch.setattr(scraper, "_http_get", lambda *_: (None, None))
    with patch("src.scrapers.browser_scraper.BrowserScraper.fetch", return_value={"html": '<h1>Outro Produto</h1><meta itemprop="price" content="99.90">', "final_url": ML}):
        raw = scraper.collect(ML, crawl=True, initial_page={"html": '<h1>Produto CB5600</h1>', "final_url": ML})
    assert raw["price"] is None


def test_complete_specs_still_collect_missing_image_without_changing_api_price():
    seed = {"ok": True, "title": "Placa Zotac RTX 4060", "description": "Ficha completa",
            "attributes": [{"name": "Modelo", "value_name": "RTX 4060"}],
            "price": 1999.9, "api_used": True, "source": "API_OFICIAL", "url_final": ML}
    page = {"ok": True, "title": seed["title"], "image_url": "https://cdn.test/foto.jpg",
            "price": 2999.9, "url_final": ML}
    with patch("src.scrapers.link_page_details.GenericScraper.collect", return_value=page) as collect:
        result = complement_link_page(seed, ML)
    collect.assert_called_once()
    assert result["image_url"] == page["image_url"]
    assert result["price"] == 1999.9
    assert result["source"] == "API_OFICIAL"
