from src.extension.router import (
    _offer_payload,
    _partner_from_analysis,
    _same_offer,
)


def test_partner_marketplace_shopee():
    analysis = {
        "origemColeta": {
            "plataforma": "SHOPEE",
            "host": "shopee.com.br",
        }
    }
    partner = _partner_from_analysis(
        analysis,
        "https://shopee.com.br/produto",
    )
    assert partner["nome"] == "Shopee"
    assert partner["dominio"] == "shopee.com.br"


def test_same_hardware_different_partner_is_new_offer():
    existing = {
        "id": 7,
        "hardwareId": 42,
        "parceiroId": 1,
        "urlOriginal": "https://mercadolivre.com.br/item/123",
        "codigoMarketplace": "MLB123",
    }
    assert not _same_offer(
        existing,
        hardware_id=42,
        partner_id=2,
        original_url="https://shopee.com.br/item/999",
        marketplace_code="999",
    )


def test_same_ad_is_updated_instead_of_duplicated():
    existing = {
        "id": 8,
        "hardware": {"id": 42},
        "parceiro": {"id": 2},
        "urlOriginal": "https://shopee.com.br/item/999#share",
        "codigoMarketplace": "SHOPEE-999",
    }
    assert _same_offer(
        existing,
        hardware_id=42,
        partner_id=2,
        original_url="https://shopee.com.br/item/999",
        marketplace_code="SHOPEE-999",
    )


def test_offer_payload_preserves_affiliate_link():
    analysis = {
        "ofertaColetada": {
            "preco": 4299.90,
            "precoAnterior": 4599.90,
            "urlOriginal": "https://shopee.com.br/item/999",
            "urlProduto": "https://shopee.com.br/item/999",
            "codigoMarketplace": "SHOPEE-999",
        }
    }
    payload = _offer_payload(
        analysis,
        hardware_id=42,
        partner_id=2,
        affiliate_url="https://s.shopee.com.br/abc",
    )
    assert payload["hardwareId"] == 42
    assert payload["parceiroId"] == 2
    assert payload["urlAfiliada"] == "https://s.shopee.com.br/abc"
    assert payload["preco"] == 4299.90
