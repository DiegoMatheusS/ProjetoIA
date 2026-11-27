import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.offers.search_intent import matches_search
from src.offers.discovery_router import search_offers, OfferDiscoveryRequest


@pytest.mark.parametrize(
    "query,title,expected",
    json.loads(
        (Path(__file__).parent / "fixtures/offer-search-intent.json").read_text()
    ),
)
def test_search_returns_the_item_sold_not_accessories_or_another_variant(
    query, title, expected
):
    assert matches_search(query, title) is expected


class Source:
    def __init__(self, store, deadline):
        self.store = store

    def api_results(self, q, limit):
        if self.store != "MERCADO_LIVRE":
            return [], "NAO_CONFIGURADA"

        def row(title, index, price=1999):
            url = f"https://produto.mercadolivre.com.br/MLB-{123456+index}"
            return {
                "url": url,
                "raw": {
                    "ok": True,
                    "title": title,
                    "price": price,
                    "currency": "BRL",
                    "url_final": url,
                    "api_used": True,
                },
            }

        return [
            row("Suporte para RTX 4060", 0),
            row("RTX 4060 Ti 8GB", 1),
            row("ASUS RTX 4060 8GB", 2),
            row("MSI RTX 4060", 3, None),
        ], "ENCONTRADO"

    def listing_results(self, q, limit):
        return [
            {
                "url": (
                    "https://www.amazon.com.br/dp/B012345678"
                    if self.store == "AMAZON"
                    else "https://www.magazineluiza.com.br/placa-rtx-4060/p/abcd1234/in/pcvd/"
                )
            }
        ], "ENCONTRADO"

    def indexed_results(self, q, limit):
        return [], "NAO_ENCONTRADO"

    def collect(self, url):
        return {
            "ok": True,
            "title": "Placa de vídeo RTX 4060 8GB",
            "price": 1999.9,
            "currency": "BRL",
            "previous_price": 2299.9,
        }


@pytest.mark.parametrize("store", ["MERCADO_LIVRE", "MAGALU", "AMAZON"])
def test_shop_results_are_confirmed_and_never_invent_an_affiliate_url(store):
    result = search_offers(
        OfferDiscoveryRequest(loja=store, consulta="RTX 4060"), factory=Source
    )
    confirmed = [item for item in result["itens"] if item["precoConfirmado"]]
    assert len(confirmed) == 1
    assert all(item["urlAfiliada"] is None for item in result["itens"])
    assert result["itens"][0]["parceiroNome"] == (
        {"MERCADO_LIVRE": "Mercado Livre", "MAGALU": "Magazine Luiza", "AMAZON": "Amazon"}[store]
    )
    assert result["itens"][0]["preco"] > 0


@pytest.mark.parametrize("store,url", [
    ("MERCADO_LIVRE", "https://produto.mercadolivre.com.br/MLB-987654"),
    ("MAGALU", "https://www.magazineluiza.com.br/placa-rtx-4060/p/abcd1234/"),
    ("AMAZON", "https://www.amazon.com.br/dp/B012345678"),
])
def test_indexed_listing_survives_blocked_detail_without_inventing_price(store, url):
    class BlockedStore(Source):
        def api_results(self, q, limit):
            return [], "BLOQUEADO"

        def listing_results(self, q, limit):
            return [], "BLOQUEADO"

        def indexed_results(self, q, limit):
            return [{"url": url, "title": "ASUS GeForce RTX 4060 8GB", "fonteCandidato": "INDICE_WEB"}], "ENCONTRADO"

        def collect(self, url):
            return {"ok": False, "blocked": True, "price": 100}

    result = search_offers(OfferDiscoveryRequest(loja=store, consulta="RTX 4060"), factory=BlockedStore)
    assert result["statusBusca"] == "PARCIAL"
    assert len(result["itens"]) == 1
    item = result["itens"][0]
    assert item["nome"] == "ASUS GeForce RTX 4060 8GB"
    assert item["categoriaDetectada"] == "PLACA_VIDEO"
    assert item["preco"] is None and not item["precoConfirmado"]
    assert item["disponivel"] is None and not item["emPromocao"]
    assert item["urlOriginal"] == url


def test_storefront_prefers_exact_listing_titles_and_groups_amazon_links():
    from src.offers.store_candidates import listing_candidates

    rows = listing_candidates('''
        <a href="/dp/B111111111?ref=first">Veja o produto</a>
        <a href="/dp/B222222222?ref=image"><img alt="" /></a>
        <a href="/ASUS/dp/B222222222?ref=title"><h2>ASUS RTX 4060 8GB</h2></a>
        <a href="/dp/B333333333"><h2>Suporte para RTX 4060</h2></a>
    ''', "https://www.amazon.com.br/s?k=RTX+4060", "AMAZON", 1, "RTX 4060")

    assert rows == [{
        "url": "https://www.amazon.com.br/dp/B222222222?ref=image",
        "title": "ASUS RTX 4060 8GB", "fonteCandidato": "LISTAGEM_LOJA",
    }]


def test_promotions_filter_requires_a_real_previous_price():
    assert (
        search_offers(
            OfferDiscoveryRequest(
                loja="MERCADO_LIVRE", consulta="RTX 4060", somentePromocoes=True
            ),
            factory=Source,
        )["itens"]
        == []
    )
    assert (
        len(
            search_offers(
                OfferDiscoveryRequest(
                    loja="MAGALU", consulta="RTX 4060", somentePromocoes=True
                ),
                factory=Source,
            )["itens"]
        )
        == 1
    )


def test_search_is_authenticated_and_does_not_accept_arbitrary_stores(monkeypatch):
    monkeypatch.setenv("PRODUTO_IA_API_KEY", "test-service-key")
    client = TestClient(app)
    assert (
        client.post(
            "/ofertas/descobrir", json={"loja": "MAGALU", "consulta": "RTX4060"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/ofertas/descobrir",
            headers={"X-API-Key": "test-service-key"},
            json={"loja": "http://localhost", "consulta": "RTX4060"},
        ).status_code
        == 422
    )
    monkeypatch.delenv("PRODUTO_IA_API_KEY")
    assert (
        client.post(
            "/ofertas/descobrir", json={"loja": "MAGALU", "consulta": "RTX4060"}
        ).status_code
        == 503
    )


def test_identical_offers_do_not_accept_an_accessory_that_quotes_the_target_model():
    from src.offers.identical_product_router import (
        IdenticalProductOffersRequest,
        _identity_match_raw,
        _identity_match_marketplace_name,
    )

    target = IdenticalProductOffersRequest(
        nome="Placa de vídeo ASUS RTX 4060 8GB",
        marca="ASUS",
        modelo="RTX 4060",
        gtin="7891234567895",
    )
    assert _identity_match_raw(
        target, {"title": "Suporte para ASUS RTX 4060 8GB", "gtin": "7891234567895"}
    ) == (False, None)
    assert (
        _identity_match_marketplace_name(target, "Adaptador ASUS RTX 4060 8GB")[0]
        is False
    )
    assert _identity_match_raw(
        target, {"title": "ASUS RTX 4060 8GB", "gtin": "7891234567895"}
    ) == (True, "GTIN")


def test_mercado_livre_uses_listing_when_api_finds_only_accessories():
    class FallbackSource(Source):
        def api_results(self, query, limit):
            rows, status = super().api_results(query, limit)
            return rows[:1], status

        def listing_results(self, query, limit):
            return [{"url": "https://produto.mercadolivre.com.br/MLB-987654"}], "ENCONTRADO"

    result = search_offers(
        OfferDiscoveryRequest(loja="MERCADO_LIVRE", consulta="RTX 4060"),
        factory=FallbackSource,
    )

    assert len(result["itens"]) == 1
    assert result["itens"][0]["urlOriginal"].endswith("MLB-987654")


def test_ram_capacity_and_speed_are_matched_as_number_unit_pairs():
    from src.shopee.relevance import relevant_item

    query = "DDR4 16GB 3200MHz"
    wrong = "Memória RAM DDR4 8 GB 3200 MHz CL 16"
    correct = "Memória RAM DDR4 16 GB 3200 MHz"
    for title, expected in [(wrong, False), (correct, True)]:
        assert matches_search(query, title) is expected
        assert relevant_item({"nome": title}, query) is expected
