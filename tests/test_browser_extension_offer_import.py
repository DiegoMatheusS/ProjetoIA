from src.criabyte.client import CriaByteClient
from src.extension.router import (
    _analysis_product_url,
    _offer_payload,
    _partner_from_analysis,
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


def test_criabyte_client_adds_api_prefix_by_default():
    client = CriaByteClient(base_url="https://api.criabyte.com.br")
    assert client.base_url == "https://api.criabyte.com.br/api/"
    assert (
        client._url("/interno/produto-ia/extensao/importar-oferta")
        == "https://api.criabyte.com.br/api/interno/produto-ia/extensao/importar-oferta"
    )


def test_criabyte_client_does_not_duplicate_api_prefix():
    client = CriaByteClient(base_url="https://api.criabyte.com.br/api")
    assert client.base_url == "https://api.criabyte.com.br/api/"


def test_offer_payload_uses_manual_price_when_scraper_has_no_price():
    analysis = {
        "ofertaColetada": {
            "preco": None,
            "urlOriginal": "https://loja.example/produto",
        }
    }
    payload = _offer_payload(
        analysis,
        affiliate_url="https://afiliado.example/x",
        manual_price=1999.90,
    )
    assert payload["preco"] == 1999.90


def test_offer_payload_manual_price_overrides_collected_price():
    analysis = {
        "ofertaColetada": {
            "preco": 2099.90,
            "urlOriginal": "https://loja.example/produto",
        }
    }
    payload = _offer_payload(
        analysis,
        affiliate_url="https://afiliado.example/x",
        manual_price=1899.90,
    )
    assert payload["preco"] == 1899.90


def test_ml_catalog_url_promotes_fragment_wid_to_item_id_for_analysis():
    url = (
        "https://www.mercadolivre.com.br/"
        "fonte-atx-700w-real-pfc-ativo-80-plus-bronze-dm-700-dex-cor-preto/"
        "p/MLB37817321"
        "#polycard_client=search-desktop&wid=MLB5953835688&sid=search"
    )
    normalized = _analysis_product_url(url)
    assert "item_id=MLB5953835688" in normalized
    assert "/p/MLB37817321" in normalized


def test_ml_user_product_url_promotes_fragment_wid_to_exact_item():
    url = (
        "https://www.mercadolivre.com.br/"
        "fonte-atx-pc-cooler-automatica-silenciosa-bivolt-500600700/"
        "up/MLBU5131595889"
        "#polycard_client=search-desktop&be_origin=backend&overlay_label=not_apply"
        "&search_layout=grid&position=5&type=product"
        "&tracking_id=62e8d335-ed1f-4fe7-bacc-bb58cfd6195b"
        "&wid=MLB5215649399&sid=search"
    )
    normalized = _analysis_product_url(url)
    assert "item_id=MLB5215649399" in normalized
    assert "/up/MLBU5131595889" in normalized


def test_ml_query_wid_is_also_promoted_to_item_id():
    url = (
        "https://www.mercadolivre.com.br/fonte/p/MLB37817321"
        "?wid=MLB5953835688"
    )
    normalized = _analysis_product_url(url)
    assert "item_id=MLB5953835688" in normalized


def test_non_ml_url_is_not_rewritten():
    url = "https://www.example.com/produto#wid=MLB5953835688"
    assert _analysis_product_url(url) == url
