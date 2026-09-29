from __future__ import annotations

from src.extension import preflight
from src.extension.preflight import (
    ConfirmAffiliateOfferRequest,
    PrepareAffiliateOfferRequest,
    _page_data,
    confirm_offer_sync,
    prepare_offer_sync,
    sign_preparation,
    verify_preparation,
)


def test_page_data_extracts_amazon_asin_from_url():
    data = _page_data(
        {
            "nome": "Echo Dot",
            "marca": "Amazon",
            "preco": 299.90,
        },
        "https://www.amazon.com.br/dp/B0ABC12345/ref=test",
    )

    assert data["asin"] == "B0ABC12345"
    assert data["nome"] == "Echo Dot"
    assert data["preco"] == 299.90


def test_signed_preparation_roundtrip(monkeypatch):
    monkeypatch.setenv("PRODUTO_IA_API_KEY", "test-secret")
    token = sign_preparation(
        {"produtoExistenteId": 10, "oferta": {"preco": 99.9}},
        {"nome": "Produto", "existente": True},
    )

    decoded = verify_preparation(token)

    assert decoded["payload"]["produtoExistenteId"] == 10
    assert decoded["previa"]["existente"] is True


def test_existing_product_prepares_offer_only(monkeypatch):
    monkeypatch.setenv("PRODUTO_IA_API_KEY", "test-secret")

    class FakeClient:
        def localizar_item_extensao(self, dados, api_key=None):
            assert dados["asin"] == "B0ABC12345"
            return {
                "encontrado": True,
                "tipo": "PRODUTO",
                "criterio": "ASIN",
                "produto": {
                    "id": 90,
                    "nome": "Echo Dot",
                    "marca": "Amazon",
                    "modelo": "Echo Dot 5",
                    "categoria": {"slug": "eletronicos"},
                    "publicado": True,
                },
            }

    monkeypatch.setattr(preflight, "CriaByteClient", FakeClient)

    result = prepare_offer_sync(
        PrepareAffiliateOfferRequest(
            urlProduto="https://www.amazon.com.br/dp/B0ABC12345",
            urlAfiliada="https://amzn.to/teste",
            dadosPagina={
                "nome": "Echo Dot",
                "marca": "Amazon",
                "modelo": "Echo Dot 5",
                "asin": "B0ABC12345",
                "preco": 299.90,
            },
        )
    )

    assert result["status"] == "PRONTO_PARA_CONFIRMAR"
    assert result["acao"] == "SOMENTE_OFERTA"
    assert result["previa"]["existente"] is True
    envelope = verify_preparation(result["token"])
    assert envelope["payload"]["produtoExistenteId"] == 90
    assert envelope["payload"]["oferta"]["codigoMarketplace"] == "B0ABC12345"


def test_missing_hardware_offers_openai_or_metaai(monkeypatch):
    monkeypatch.setenv("PRODUTO_IA_API_KEY", "test-secret")

    class FakeClient:
        def localizar_item_extensao(self, dados, api_key=None):
            return {"encontrado": False, "motivo": "ITEM_NAO_ENCONTRADO"}

    monkeypatch.setattr(preflight, "CriaByteClient", FakeClient)
    monkeypatch.setattr(
        preflight,
        "_analyze_sync",
        lambda _request: {
            "categoriaDetectada": "FONTE",
            "tipoCadastro": "HARDWARE",
            "origemColeta": {"plataforma": "AMAZON", "host": "amazon.com.br"},
            "ofertaColetada": {"preco": 399.9},
            "payloadParcialBackend": {
                "nome": "Fonte Teste 750W",
                "marca": "Marca",
                "modelo": "X750",
                "categoria": "FONTE",
                "especificacaoFonte": {"potenciaWatts": 750},
            },
        },
    )

    result = prepare_offer_sync(
        PrepareAffiliateOfferRequest(
            urlProduto="https://www.amazon.com.br/dp/B0ABC12345",
            urlAfiliada="https://amzn.to/teste",
            dadosPagina={
                "nome": "Fonte Teste 750W",
                "marca": "Marca",
                "modelo": "X750",
                "asin": "B0ABC12345",
                "preco": 399.9,
            },
        )
    )

    assert result["status"] == "COMPLETAR_COM_IA"
    assert result["provedoresDisponiveis"] == ["OPENAI", "META_AI"]


def test_confirmation_sends_signed_payload(monkeypatch):
    monkeypatch.setenv("PRODUTO_IA_API_KEY", "test-secret")
    sent = {}

    class FakeClient:
        def importar_oferta_extensao(self, dados, api_key=None):
            sent.update(dados)
            return {
                "status": "NOVA_OFERTA_CRIADA",
                "reutilizado": True,
                "produto": {"id": 90, "nome": "Echo Dot"},
            }

    monkeypatch.setattr(preflight, "CriaByteClient", FakeClient)
    token = sign_preparation(
        {
            "produtoExistenteId": 90,
            "parceiro": {"nome": "Amazon"},
            "oferta": {
                "urlOriginal": "https://www.amazon.com.br/dp/B0ABC12345",
                "urlAfiliada": "https://amzn.to/teste",
                "preco": 299.9,
                "asin": "B0ABC12345",
            },
        },
        {"nome": "Echo Dot", "existente": True},
    )

    result = confirm_offer_sync(ConfirmAffiliateOfferRequest(token=token))

    assert result["confirmado"] is True
    assert sent["produtoExistenteId"] == 90
    assert sent["oferta"]["asin"] == "B0ABC12345"
