import pytest

from src.offers import identical_product_router as offers
from src.offers.identical_product_router import (
    IdenticalProductOffersRequest,
    _identity_match_marketplace_name,
    _identity_match_raw,
)


def test_identical_offer_prefers_gtin():
    payload = IdenticalProductOffersRequest(
        nome="Produto X",
        marca="Kingston",
        modelo="SNV3S/1000G",
        gtin="740617344844",
    )
    matched, criterion = _identity_match_raw(
        payload,
        {
            "title": "SSD Kingston NV3 1TB",
            "brand": "Kingston",
            "model": "outro",
            "gtin": "740617344844",
        },
    )
    assert matched is True
    assert criterion == "GTIN"


def test_identical_offer_rejects_different_model():
    payload = IdenticalProductOffersRequest(
        nome="GeForce RTX",
        marca="ASUS",
        modelo="DUAL-RTX5060TI-O8G",
    )
    matched, criterion = _identity_match_raw(
        payload,
        {
            "title": "ASUS Dual RTX 5060 Ti 16GB",
            "brand": "ASUS",
            "model": "DUAL-RTX5060TI-O16G",
        },
    )
    assert matched is False
    assert criterion is None


def test_shopee_requires_brand_and_model_in_title():
    payload = IdenticalProductOffersRequest(
        nome="SSD Kingston NV3",
        marca="Kingston",
        modelo="SNV3S/1000G",
    )
    matched, criterion = _identity_match_marketplace_name(
        payload,
        "SSD Kingston NV3 1TB SNV3S/1000G NVMe",
    )
    assert matched is True
    assert criterion == "MARCA_MODELO_TITULO"
    rejected, _ = _identity_match_marketplace_name(
        payload,
        "SSD Kingston NV3 2TB SNV3S/2000G NVMe",
    )
    assert rejected is False


def test_mpns_in_marketplace_titles_are_accepted_when_structured_fields_are_missing():
    payload = IdenticalProductOffersRequest(
        nome="SSD Kingston NV3 1TB",
        marca="Kingston",
        mpn="SNV3S/1000G",
    )
    matched, criterion = _identity_match_raw(
        payload,
        {"title": "SSD Kingston NV3 1TB SNV3S/1000G", "brand": "Kingston"},
    )
    assert matched is True
    assert criterion == "MPN_MARCA_TITULO"


@pytest.mark.parametrize("conflict", [
    {"gtin": "740617344899"},
    {"mpn": "SNV3S/2000G"},
])
def test_titles_cannot_override_conflicting_identifiers(conflict):
    payload = IdenticalProductOffersRequest(
        nome="SSD Kingston NV3 1TB",
        marca="Kingston",
        mpn="SNV3S/1000G",
        gtin="740617344844",
    )
    matched, criterion = _identity_match_raw(
        payload,
        {"title": "SSD Kingston NV3 1TB SNV3S/1000G", "brand": "Kingston", **conflict},
    )
    assert matched is False
    assert criterion is None


def test_explicit_model_conflict_cannot_be_overridden_by_title():
    payload = IdenticalProductOffersRequest(
        nome="ASUS RTX",
        marca="ASUS",
        modelo="DUAL-RTX5060TI-O8G",
    )
    matched, criterion = _identity_match_raw(
        payload,
        {
            "title": "ASUS DUAL-RTX5060TI-O8G",
            "brand": "ASUS",
            "model": "DUAL-RTX5060TI-O16G",
        },
    )
    assert matched is False
    assert criterion is None


@pytest.mark.parametrize("store", ["MERCADO_LIVRE", "MAGALU"])
def test_search_accepts_verified_mpn_from_title_when_api_omits_fields(monkeypatch, store):
    class FakeResolver:
        last_status = "OK"

        def results(self, query, domains, limit):
            return [{"url": "https://www.mercadolivre.com.br/produto" if store == "MERCADO_LIVRE"
                     else "https://www.magazineluiza.com.br/produto/p/123456/"}]

    class FakeScraper:
        @staticmethod
        def is_mercadolivre(url):
            return True

        @staticmethod
        def is_product_url(url):
            return True

        def collect(self, url, no_browser):
            return {
                "ok": True,
                "title": "SSD Kingston NV3 1TB SNV3S/1000G",
                "brand": "Kingston",
                "price": 399.9,
                "url_final": url,
            }

    monkeypatch.setattr(offers, "WebSearchResolver", FakeResolver)
    monkeypatch.setattr(offers, "MercadoLivreScraper", FakeScraper)
    monkeypatch.setattr(offers, "MagazineScraper", FakeScraper)

    payload = IdenticalProductOffersRequest(
        nome="SSD Kingston NV3 1TB",
        marca="Kingston",
        mpn="SNV3S/1000G",
    )
    found, diagnostics = offers._search_web_store(payload, store, ["example.com"], 3)
    assert len(found) == 1
    assert found[0]["criterioIdentidade"] == "MPN_MARCA_TITULO"
    assert found[0]["preco"] == 399.9
    assert diagnostics["falhasColeta"] == 0
    assert diagnostics["rejeitadosPorIdentidade"] == 0


def test_search_reports_failed_collection_separately(monkeypatch):
    class FakeResolver:
        last_status = "OK"

        def results(self, query, domains, limit):
            return [{"url": "https://www.mercadolivre.com.br/produto"}]

    class FakeScraper:
        @staticmethod
        def is_mercadolivre(url):
            return True

        def collect(self, url, no_browser):
            return {"ok": False, "blocked": True}

    monkeypatch.setattr(offers, "WebSearchResolver", FakeResolver)
    monkeypatch.setattr(offers, "MercadoLivreScraper", FakeScraper)
    payload = IdenticalProductOffersRequest(nome="SSD Kingston NV3", marca="Kingston", mpn="SNV3S/1000G")
    found, diagnostics = offers._search_web_store(payload, "MERCADO_LIVRE", ["example.com"], 3)
    assert found == []
    assert diagnostics["falhasColeta"] == 1
    assert diagnostics["rejeitadosPorIdentidade"] == 0
