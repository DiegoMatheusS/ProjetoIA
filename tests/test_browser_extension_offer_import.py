import pytest

from src.criabyte.client import CriaByteClient
from src.extension import router_v2
from src.extension.router import (
    _analysis_product_url,
    _apply_manual_fields,
    _missing_product_paths,
    _offer_payload,
    _partner_from_analysis,
    _preview_payload,
    _product_payload_for_backend,
)
from src.extension.router_v2 import ImportAffiliateOfferV2Request


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


def test_monitor_is_built_as_generic_product_payload():
    analysis = {
        "categoriaSlugSugerida": "monitores",
    }
    raw = {
        "nome": "Monitor LG UltraGear 24",
        "marca": "LG",
        "modelo": "24GN60R-B",
        "imagemUrl": "https://cdn.example/monitor.jpg",
        "especificacaoMonitor": {
            "tamanhoPolegadas": 24,
            "resolucao": "1920x1080",
            "taxaAtualizacaoHz": 144,
            "tipoPainel": "IPS",
            "campoInexistente": "nao-enviar",
        },
    }

    payload = _product_payload_for_backend("MONITOR", analysis, raw)

    assert payload["categoriaSlug"] == "monitores"
    assert payload["nome"] == "Monitor LG UltraGear 24"
    assert payload["marca"] == "LG"
    assert payload["modelo"] == "24GN60R-B"
    assert payload["especificacaoMonitor"]["taxaAtualizacaoHz"] == 144
    assert "campoInexistente" not in payload["especificacaoMonitor"]
    assert "categoria" not in payload


def test_generic_product_without_structured_table_keeps_common_fields_only():
    analysis = {
        "categoriaSlugSugerida": "celulares",
    }
    raw = {
        "nome": "Smartphone Teste",
        "marca": "Marca",
        "modelo": "X1",
        "processadorNome": "Chip X",
    }

    payload = _product_payload_for_backend("CELULAR", analysis, raw)

    assert payload == {
        "categoriaSlug": "celulares",
        "nome": "Smartphone Teste",
        "marca": "Marca",
        "modelo": "X1",
    }


def test_product_missing_fields_include_root_and_core_specs():
    raw = {
        "nome": "Monitor Teste",
        "especificacaoMonitor": {
            "resolucao": "1920x1080",
        },
    }

    missing = _missing_product_paths("MONITOR", raw)

    assert "marca" in missing
    assert "modelo" in missing
    assert "especificacaoMonitor.tamanhoPolegadas" in missing
    assert "especificacaoMonitor.taxaAtualizacaoHz" in missing
    assert "especificacaoMonitor.tipoPainel" in missing
    assert "especificacaoMonitor.resolucao" not in missing


def test_manual_fields_fill_only_allowed_paths():
    raw = {
        "nome": "Fonte Teste",
        "marca": "Marca",
        "modelo": "X",
        "especificacaoFonte": {},
    }
    completed = _apply_manual_fields(
        "FONTE",
        raw,
        {
            "especificacaoFonte.formato": "ATX",
            "especificacaoFonte.potenciaWatts": 700,
            "campoInexistente": "ignorar",
        },
    )

    assert completed["especificacaoFonte"]["formato"] == "ATX"
    assert completed["especificacaoFonte"]["potenciaWatts"] == 700
    assert "campoInexistente" not in completed


def test_preview_contains_product_and_offer_data():
    preview = _preview_payload(
        "MONITOR",
        "PRODUTO",
        {
            "nome": "Monitor Teste",
            "marca": "LG",
            "modelo": "X1",
            "especificacaoMonitor": {
                "tamanhoPolegadas": 24,
                "resolucao": "1920x1080",
            },
        },
        {},
        partner={"nome": "Mercado Livre"},
        offer={"preco": 999.9},
        published=True,
    )

    assert preview["categoria"] == "MONITOR"
    assert preview["preco"] == 999.9
    assert preview["parceiro"] == "Mercado Livre"
    assert preview["publicado"] is True
    assert preview["especificacoes"]["resolucao"] == "1920x1080"


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


@pytest.mark.parametrize("selector", [
    "?wid=MLB5953835688", "#wid=MLB5953835688",
    "?item_id=MLB5953835688", "?pdp_filters=item_id%3AMLB5953835688",
])
def test_offer_keeps_specific_ml_listing_even_after_catalog_redirect(selector):
    catalog = "https://www.mercadolivre.com.br/fonte/p/MLB37817321"
    payload = _offer_payload({"ofertaColetada": {
        "preco": 199.9, "urlProduto": catalog,
        "codigoMarketplace": "MLB37817321",
        "vendedorNome": "Loja A", "vendedorIdentificador": 123,
    }}, affiliate_url="https://meli.la/loja-a", product_url=catalog + selector)
    assert payload["codigoMarketplace"] == "MLB5953835688"
    assert "item_id=MLB5953835688" in payload["urlOriginal"]
    assert payload["urlAfiliada"] == "https://meli.la/loja-a"
    assert payload["vendedorNome"] == "Loja A"
    assert payload["vendedorIdentificador"] == "123"


def test_offer_recovers_listing_from_original_when_final_url_is_shared_catalog():
    catalog = "https://www.mercadolivre.com.br/fonte/p/MLB37817321"
    payload = _offer_payload({"ofertaColetada": {
        "preco": 199.9, "urlProduto": catalog,
        "urlOriginal": catalog + "#wid=MLB5953835688",
        "codigoMarketplace": "MLB37817321",
    }}, affiliate_url="https://meli.la/loja-a")
    assert payload["codigoMarketplace"] == "MLB5953835688"
    assert "item_id=MLB5953835688" in payload["urlOriginal"]


def test_v2_existing_offer_preserves_listing_selector():
    payload = ImportAffiliateOfferV2Request(
        urlProduto="https://www.mercadolivre.com.br/fonte/p/MLB37817321#wid=MLB5953835688",
        urlAfiliada="https://meli.la/loja-a", precoManual=199.9,
        dadosPagina={"codigoMarketplace": "MLB37817321"},
    )
    offer = router_v2._page_offer(payload, payload.urlAfiliada)
    assert offer["codigoMarketplace"] == "MLB5953835688"
    assert "item_id=MLB5953835688" in offer["urlOriginal"]


def test_v2_existing_amazon_product_skips_ai(monkeypatch):
    captured = {}

    def fail_ai(_request):
        raise AssertionError("A IA não deveria ser chamada para item existente")

    def find_existing(_self, dados, api_key=None):
        assert dados["asin"] == "B0ABC12345"
        assert api_key is not None or api_key is None
        return {
            "status": "EXISTENTE",
            "tipo": "PRODUTO",
            "produtoId": 70,
            "criterio": "ASIN",
            "item": {
                "id": 70,
                "nome": "Echo Dot 5ª geração",
                "marca": "Amazon",
                "modelo": "Echo Dot 5",
                "asin": "B0ABC12345",
                "publicado": True,
            },
        }

    def import_offer(_self, dados, api_key=None):
        captured.update(dados)
        return {
            "status": "ITEM_EXISTENTE_OFERTA_CRIADA",
            "produto": {"id": 70, "nome": "Echo Dot 5ª geração"},
            "parceiro": {"id": 3, "nome": "Amazon"},
            "publicado": True,
            "oferta": {"id": 91},
        }

    monkeypatch.setattr(router_v2, "_analyze_sync", fail_ai)
    monkeypatch.setattr(CriaByteClient, "buscar_item_extensao", find_existing)
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao", import_offer)

    result = router_v2._import_v2_sync(
        ImportAffiliateOfferV2Request(
            urlProduto="https://www.amazon.com.br/dp/B0ABC12345",
            urlAfiliada="https://amzn.to/teste",
            dadosPagina={
                "nome": "Echo Dot 5ª geração",
                "marca": "Amazon",
                "modelo": "Echo Dot 5",
                "asin": "B0ABC12345",
                "preco": 349.90,
            },
        )
    )

    assert result["completouComIa"] is False
    assert result["buscaCriabyte"]["criterio"] == "ASIN"
    assert captured["produtoExistenteId"] == 70
    assert captured["oferta"]["asin"] == "B0ABC12345"
    assert captured["oferta"]["codigoMarketplace"] == "B0ABC12345"
    assert captured["oferta"]["preco"] == 349.90


def test_v2_not_found_uses_ai_and_keeps_page_identifiers(monkeypatch):
    captured = {}
    ai_calls = []

    def not_found(_self, dados, api_key=None):
        assert dados["asin"] == "B0NEW12345"
        return {"status": "NAO_ENCONTRADO"}

    def analyze(request):
        ai_calls.append(request)
        return {
            "categoriaDetectada": "CELULAR",
            "tipoCadastro": "PRODUTO",
            "categoriaSlugSugerida": "celulares",
            "origemColeta": {
                "plataforma": "AMAZON",
                "host": "amazon.com.br",
            },
            "ofertaColetada": {
                "preco": 2099.90,
                "urlOriginal": "https://www.amazon.com.br/dp/B0NEW12345",
            },
            "payloadParcialBackend": {
                "nome": "Smartphone X",
                "marca": "Marca X",
                "modelo": "X1",
            },
        }

    def import_offer(_self, dados, api_key=None):
        captured.update(dados)
        return {
            "status": "PRODUTO_E_OFERTA_CRIADOS",
            "produto": {"id": 88, "nome": "Smartphone X"},
            "parceiro": {"id": 3, "nome": "Amazon"},
            "publicado": True,
            "oferta": {"id": 92},
        }

    monkeypatch.setattr(CriaByteClient, "buscar_item_extensao", not_found)
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao", import_offer)
    monkeypatch.setattr(router_v2, "_analyze_sync", analyze)

    result = router_v2._import_v2_sync(
        ImportAffiliateOfferV2Request(
            urlProduto="https://www.amazon.com.br/dp/B0NEW12345",
            urlAfiliada="https://amzn.to/novo",
            dadosPagina={
                "nome": "Smartphone X",
                "marca": "Marca X",
                "modelo": "X1",
                "gtin": "7891234567890",
                "asin": "B0NEW12345",
                "preco": 1999.90,
            },
        )
    )

    assert len(ai_calls) == 1
    assert result["completouComIa"] is True
    assert result["buscaCriabyte"]["status"] == "NAO_ENCONTRADO"
    assert captured["produtoPayload"]["asin"] == "B0NEW12345"
    assert captured["produtoPayload"]["gtin"] == "7891234567890"
    assert captured["oferta"]["asin"] == "B0NEW12345"
    assert captured["oferta"]["preco"] == 1999.90


def test_v2_existing_item_requires_manual_price_when_page_has_none(monkeypatch):
    monkeypatch.setattr(
        CriaByteClient,
        "buscar_item_extensao",
        lambda _self, _dados, api_key=None: {
            "status": "EXISTENTE",
            "tipo": "PRODUTO",
            "produtoId": 70,
            "criterio": "ASIN",
            "item": {"id": 70, "nome": "Echo Dot"},
        },
    )

    with pytest.raises(router_v2.MissingPriceError):
        router_v2._import_v2_sync(
            ImportAffiliateOfferV2Request(
                urlProduto="https://www.amazon.com.br/dp/B0ABC12345",
                urlAfiliada="https://amzn.to/teste",
                dadosPagina={"asin": "B0ABC12345"},
            )
        )
