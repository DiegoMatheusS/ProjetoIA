from src.extension.router import _offer_payload, _partner_from_analysis


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
        affiliate_url="https://s.shopee.com.br/abc",
    )
    assert payload["urlAfiliada"] == "https://s.shopee.com.br/abc"
    assert payload["urlOriginal"] == "https://shopee.com.br/item/999"
    assert payload["codigoMarketplace"] == "SHOPEE-999"
    assert payload["preco"] == 4299.90


def test_offer_payload_drops_invalid_previous_price():
    analysis = {
        "ofertaColetada": {
            "preco": 100.0,
            "precoAnterior": 90.0,
            "urlOriginal": "https://loja.example/produto",
        }
    }
    payload = _offer_payload(
        analysis,
        affiliate_url="https://afiliado.example/x",
    )
    assert "precoAnterior" not in payload
