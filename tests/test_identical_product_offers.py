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
