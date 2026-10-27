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
        if self.store == "MAGALU":
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
                "url": "https://www.magazineluiza.com.br/placa-rtx-4060/p/abcd1234/in/pcvd/"
            }
        ], "ENCONTRADO"

    def collect(self, url):
        return {
            "ok": True,
            "title": "Placa de vídeo RTX 4060 8GB",
            "price": 1999.9,
            "currency": "BRL",
            "previous_price": 2299.9,
        }


@pytest.mark.parametrize("store", ["MERCADO_LIVRE", "MAGALU"])
def test_shop_results_are_confirmed_and_never_invent_an_affiliate_url(store):
    result = search_offers(
        OfferDiscoveryRequest(loja=store, consulta="RTX 4060"), factory=Source
    )
    assert len(result["itens"]) == 1
    assert result["itens"][0]["urlAfiliada"] is None
    assert result["itens"][0]["parceiroNome"] == (
        "Mercado Livre" if store == "MERCADO_LIVRE" else "Magazine Luiza"
    )
    assert result["itens"][0]["preco"] > 0


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
