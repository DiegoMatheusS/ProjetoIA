import json
import time
from types import SimpleNamespace

import pytest
import requests

from src.offers import store_candidates
from src.offers.discovery_router import OfferDiscoveryRequest, search_offers


@pytest.fixture
def unavailable_store(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("ML_TOKEN_STORE_PATH", str(tmp_path / "ml_tokens.enc"))
    monkeypatch.delenv("ML_ACCESS_TOKEN", raising=False)
    for method in ("api_results", "listing_results"):
        monkeypatch.setattr(store_candidates.StoreCandidates, method, lambda *_: ([], "BLOQUEADO"))

    def public_search(resolver, *_args, **_kwargs):
        resolver.last_status = "BLOQUEADO"
        return []

    monkeypatch.setattr(store_candidates.WebSearchResolver, "results", public_search)


@pytest.mark.parametrize("store,url", [
    ("AMAZON", "https://www.amazon.com.br/dp/B012345678"),
    ("MAGALU", "https://www.magazineluiza.com.br/placa-rtx-4060/p/abcd1234/"),
    ("MERCADO_LIVRE", "https://produto.mercadolivre.com.br/MLB-987654"),
])
def test_brave_finds_the_actual_ad_without_openai(monkeypatch, unavailable_store, store, url):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def get(endpoint, **kwargs):
        assert endpoint == "https://api.search.brave.com/res/v1/web/search"
        assert kwargs["headers"]["X-Subscription-Token"] == "brave-test-key"
        assert kwargs["allow_redirects"] is False
        assert kwargs["params"]["q"].startswith("uma RTX 4060 site:")
        assert kwargs["params"]["country"] == "BR"
        return SimpleNamespace(status_code=200, json=lambda: {"web": {"results": [
            {"url": "https://example.com/dp/B012345678", "title": "RTX 4060"},
            {"url": url, "title": "Placa de vídeo RTX 4060 8GB", "price": 50},
        ]}})

    def factory(shop, deadline):
        source = store_candidates.StoreCandidates(shop, deadline)
        source.public.session.get = get
        source.collect = lambda found_url: {"ok": False, "blocked": True, "price": 90}
        return source

    result = search_offers(OfferDiscoveryRequest(loja=store, consulta="Onde comprar uma RTX 4060?"), factory)
    assert result["statusBusca"] == "PARCIAL"
    assert len(result["itens"]) == 1
    item = result["itens"][0]
    assert item["urlOriginal"] == url and item["fonte"] == "INDICE_BRAVE"
    assert item["preco"] is None and item["disponivel"] is None


@pytest.mark.parametrize("available", [True, False])
def test_verifies_openai_sources_without_a_title(monkeypatch, unavailable_store, available):
    url = "https://www.amazon.com.br/dp/B012345678"
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_WEB_SEARCH", "true")

    def post(session, endpoint, *, json, **kwargs):
        assert json["tool_choice"] == "required"
        assert json["tools"] == [{"type": "web_search", "filters": {"allowed_domains": ["amazon.com.br"]}}]
        return SimpleNamespace(status_code=200, json=lambda: {"output_text": "Resultado", "output": [
            {"type": "web_search_call", "action": {"sources": [
                {"url": "https://www.amazon.com/dp/B012345678"},
                {"url": "https://www.amazon.com.br/dp/B111111111", "title": "Suporte para RTX 4060"},
                {"url": url},
            ]}},
        ]})

    def collect(source, found_url):
        assert found_url == url
        return {"ok": True, "title": "ASUS RTX 4060 8GB", "price": 1999,
                "available": available, "url_final": url}

    monkeypatch.setattr(requests.Session, "post", post)
    monkeypatch.setattr(store_candidates.StoreCandidates, "collect", collect)
    result = search_offers(OfferDiscoveryRequest(loja="AMAZON", consulta="RTX 4060"))
    assert [item["preco"] for item in result["itens"]] == ([1999] if available else [])


def test_mercado_livre_reads_public_ad_when_item_api_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("HTTP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ML_TOKEN_STORE_PATH", str(tmp_path / "ml_tokens.enc"))
    source = store_candidates.StoreCandidates("MERCADO_LIVRE", time.monotonic() + 10)
    source.ml = SimpleNamespace(token="test", collect=lambda *_, **__: {"ok": False})
    url = "https://produto.mercadolivre.com.br/MLB-987654"
    product = {"@type": "Product", "name": "Placa de vídeo RTX 4060 8GB", "offers": {
        "@type": "Offer", "price": "2120", "priceCurrency": "BRL", "availability": "https://schema.org/InStock",
    }}
    source._page = lambda _: SimpleNamespace(
        url=url, text=f'<script type="application/ld+json">{json.dumps(product)}</script>',
    )
    result = source.collect(url)
    assert result["ok"] and result["available"] is True
    assert result["price"] == 2120 and result["source"] == "MERCADO_LIVRE_PAGINA"
