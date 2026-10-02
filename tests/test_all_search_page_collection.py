"""Integração da coleta complementar nos cadastros e nas fichas de Hardware."""
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.discovery import core
from src.discovery.core import HardwareDiscoveryService, infer_identity
from src.discovery.sources import DiscoveryCandidate
from src.enrichment.providers import PCKomboProvider
from src.scrapers.generic_scraper import GenericScraper


URL = "https://www.pc-kombo.com/us/product/cpu/5600X"
SPECS = URL + "/specs"
IDENTITY = infer_identity("AMD Ryzen 5 5600X", "PROCESSADOR")
HTML = '''<link rel="canonical" href="/us/product/cpu/5600X">
<script type="application/ld+json">{"@type":"Product","name":"AMD Ryzen 5 5600X",
"brand":{"name":"AMD"},"model":"Ryzen 5 5600X","mpn":"100-100000065BOX",
"offers":{"price":"999","priceCurrency":"BRL"}}</script>
<h1>AMD Ryzen 5 5600X</h1><dl><dt>Socket</dt><dd>AM4</dd></dl>
<a href="/us/product/cpu/5600X/specs">Specifications</a>'''
DETAIL_HTML = '''<link rel="canonical" href="/us/product/cpu/5600X">
<div id="description">Processador AMD Ryzen 5 5600X para computadores desktop.</div>
<img itemprop="image" src="/cpu.png">
<dl><dt>Cores</dt><dd>6</dd><dt>Threads</dt><dd>12</dd>
<dt>Memory Types</dt><dd>DDR4</dd></dl>'''


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ENRICHMENT_DISABLE", "true")
    monkeypatch.setenv("REQUEST_MIN_DELAY_SECONDS", "0")
    monkeypatch.setenv("REQUEST_JITTER_SECONDS", "0")


def response(url, html):
    result = requests.Response()
    result.url, result.status_code = url, 200
    result._content, result._content_consumed = html.encode(), True
    result.encoding = "utf-8"
    result.headers["Content-Type"] = "text/html"
    return result


@pytest.mark.parametrize("version", [1, 2])
def test_extension_new_registration_requests_full_page_collection(monkeypatch, version):
    from src.extension import router, router_v2
    captured = []
    class AnalysisReached(Exception):
        pass
    def analyze(request):
        captured.append(request)
        raise AnalysisReached()
    if version == 1:
        monkeypatch.setattr(router, "_analyze_sync", analyze)
        invoke = lambda: router._import_sync(router.ImportAffiliateOfferRequest(
            urlProduto="https://shopee.com.br/product/123/456",
            urlAfiliada="https://shopee.com.br/affiliate", categoria="PC_MONTADO"))
    else:
        monkeypatch.setattr(router_v2, "_analyze_sync", analyze)
        invoke = lambda: router_v2._import_new_with_ai(router_v2.ImportAffiliateOfferV2Request(
            urlProduto="https://shopee.com.br/product/123/456",
            urlAfiliada="https://shopee.com.br/affiliate", categoria="PC_MONTADO"), "NAO_ENCONTRADO")
    with pytest.raises(AnalysisReached):
        invoke()
    assert captured[0].detalharPagina is True
    assert captured[0].urlAfiliada == "https://shopee.com.br/affiliate"
    assert captured[0].categoria == "PC_MONTADO"


def provider_with_pages(monkeypatch):
    provider = PCKomboProvider()
    provider.rate_limiter.wait = lambda *_: None
    provider.session.get = MagicMock(return_value=response(URL, HTML))
    def extra_page(url, *_):
        if url.endswith("robots.txt"):
            return response(url, "User-agent: *\nAllow: /"), None
        assert url == SPECS
        return response(url, DETAIL_HTML), None
    monkeypatch.setattr(provider.generic, "_http_get", MagicMock(side_effect=extra_page))
    monkeypatch.setattr(core, "_provider_for_candidate", lambda _: provider)
    return provider


def candidate():
    return DiscoveryCandidate(nome="AMD Ryzen 5 5600X", marca="AMD", url=URL, fonte="PC_KOMBO", resumo={})


def test_hardware_detail_reuses_html_crawls_specs_and_keeps_field_provenance(monkeypatch):
    provider = provider_with_pages(monkeypatch)
    service = HardwareDiscoveryService()
    result = service._detail_candidate(candidate(), "PROCESSADOR", False, True, True, time.monotonic() + 8)
    assert provider.page_collection_no_browser is True
    assert provider.session.get.call_count == 1
    assert provider.generic._http_get.call_count == 2  # robots e ficha adicional
    assert result["coletaPagina"]["executado"]
    assert result["coletaPagina"]["crawlingLimitado"]["urlsAproveitadas"] == [SPECS]
    assert result["payloadHardware"]["nome"] == "AMD Ryzen 5 5600X"
    assert result["payloadHardware"]["descricao"].startswith("Processador AMD")
    assert result["payloadHardware"]["imagemUrl"] == "https://www.pc-kombo.com/cpu.png"
    assert result["especificacoesEncontradas"]["nucleos"] == 6
    assert result["especificacoesEncontradas"]["tiposMemoriaSuportados"] == ["DDR4"]
    assert result["origemPorCampo"]["nucleos"]["url"] == SPECS
    assert result["preco"] is None
    assert "preco" not in result["payloadHardware"]


def test_hardware_search_activates_collection_and_passes_global_deadline(monkeypatch):
    provider = provider_with_pages(monkeypatch)
    catalog = MagicMock()
    catalog.discover.return_value = ([candidate()], [])
    service = HardwareDiscoveryService(catalog=catalog)
    started = time.monotonic()
    result = service.discover("PROCESSADOR", limite=1, enriquecer=False)
    assert result["itens"][0]["coletaPagina"]["executado"]
    assert provider.page_collection_enabled
    assert provider.page_collection_no_browser
    assert started + service.request_budget <= provider.page_collection_deadline <= time.monotonic() + service.request_budget


@pytest.mark.parametrize("no_browser", [True, False])
def test_individual_hardware_detail_honors_browser_option(monkeypatch, no_browser):
    provider = provider_with_pages(monkeypatch)
    raw = GenericScraper()._parse_html(URL, URL, HTML)
    with patch.object(provider.generic, "collect", return_value=raw) as collect:
        HardwareDiscoveryService().detail("PROCESSADOR", "AMD Ryzen 5 5600X", URL, "PC_KOMBO", enriquecer=False, no_browser=no_browser)
    assert collect.call_args.kwargs["no_browser"] is no_browser
    assert collect.call_args.kwargs["crawl"] is True
    assert collect.call_args.kwargs["initial_page"]["html"] == HTML


def test_expired_hardware_budget_preserves_primary_specs_without_more_requests(monkeypatch):
    provider = provider_with_pages(monkeypatch)
    with patch.object(provider.generic, "collect") as collect:
        result = HardwareDiscoveryService()._detail_candidate(candidate(), "PROCESSADOR", False, True, True, time.monotonic() - 1)
    collect.assert_not_called()
    assert result["especificacoesEncontradas"]["socket"] == "AM4"
    assert result["coletaPagina"]["motivo"] == "ORCAMENTO_COLETA_ESGOTADO"


@pytest.mark.parametrize("wrong_url,wrong_model", [(URL, "Ryzen 7 5700X"), ("https://outra.example/cpu", "Ryzen 5 5600X")])
def test_hardware_rejects_other_model_or_source_without_losing_primary(monkeypatch, wrong_url, wrong_model):
    provider = provider_with_pages(monkeypatch)
    raw = {"ok": True, "url_final": wrong_url, "title": "AMD " + wrong_model, "brand": "AMD", "model": wrong_model,
        "description": "Descrição não autorizada", "attributes": [{"name": "Cores", "value_name": "99"}]}
    with patch.object(provider.generic, "collect", return_value=raw):
        result = HardwareDiscoveryService()._detail_candidate(candidate(), "PROCESSADOR", False, True)
    assert result["payloadHardware"]["modelo"] == "Ryzen 5 5600X"
    assert result["especificacoesEncontradas"]["nucleos"] != 99
    assert not result["payloadHardware"].get("descricao")


def test_reused_static_page_does_not_download_product_again():
    collector = GenericScraper()
    with patch.object(collector, "_http_get") as get:
        result = collector.collect(URL, no_browser=True, crawl=True, budget_seconds=1, initial_page={"html": HTML.replace('href="/us/product/cpu/5600X/specs"', 'href="#specs"'), "final_url": URL})
    get.assert_not_called()
    assert result["collection_attempts"][0]["modo"] == "HTML_REAPROVEITADO"


def test_page_failure_preserves_collected_hardware(monkeypatch):
    provider = provider_with_pages(monkeypatch)
    with patch.object(provider.generic, "collect", side_effect=RuntimeError("falha temporária")):
        result = HardwareDiscoveryService()._detail_candidate(candidate(), "PROCESSADOR", False, True)
    assert result["detalhesColetados"] and result["especificacoesEncontradas"]["socket"] == "AM4"
    assert result["coletaPagina"]["motivo"] == "RuntimeError"


def test_full_collection_does_not_reuse_partial_batch_cache():
    collector = GenericScraper()
    page = {"html": HTML.replace('href="/us/product/cpu/5600X/specs"', 'href="#specs"'), "final_url": URL}
    with patch.object(collector, "_parse_html", wraps=collector._parse_html) as parse:
        collector.collect(URL, no_browser=True, crawl=True, budget_seconds=12, initial_page=page)
        result = collector.collect(URL, no_browser=True, crawl=True, budget_seconds=30, initial_page=page)
        cached = collector.collect(URL, no_browser=True, crawl=True, budget_seconds=30, initial_page=page)
    assert parse.call_count == 2
    assert not result["cache_hit"]
    assert cached["cache_hit"]
