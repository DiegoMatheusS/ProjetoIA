from src.criabyte.client import CriaByteClient
from src.extension import amazon_fallback, router_v2
from src.extension.router_v2 import ImportAffiliateOfferV2Request, PageCapture


def _blocked_analysis():
    return {
        "categoriaDetectada": None,
        "tipoCadastro": None,
        "payloadParcialBackend": {"nome": None},
        "ofertaColetada": {"urlOriginal": "https://www.amazon.com.br/dp/B0ABC12345"},
    }


def test_amazon_browser_title_recovers_category_and_offer_without_server_scrape(monkeypatch):
    sent = {}
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda data: data)
    monkeypatch.setattr(router_v2, "_analyze_sync", lambda _request: _blocked_analysis())
    monkeypatch.setattr(
        CriaByteClient,
        "buscar_item_extensao",
        lambda _self, _identity, api_key=None: {"status": "NAO_ENCONTRADO"},
    )

    def import_offer(_self, payload, api_key=None):
        sent.update(payload)
        return {"status": "PRODUTO_E_OFERTA_CRIADOS", "publicado": True}

    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao", import_offer)

    result = router_v2._import_v2_sync(
        ImportAffiliateOfferV2Request(
            urlProduto="https://www.amazon.com.br/dp/B0ABC12345",
            urlAfiliada="https://amzn.to/exemplo",
            dadosPagina={
                "nome": "Smartphone MarcaTeste X2 256GB 5G",
                "marca": "MarcaTeste",
                "modelo": "X2",
                "asin": "B0ABC12345",
                "preco": 1599.90,
            },
        )
    )

    assert result["status"] == "PRODUTO_E_OFERTA_CRIADOS"
    assert result["previa"]["categoria"] == "CELULAR"
    assert result["previa"]["parceiro"] == "Amazon"
    assert sent["produtoPayload"]["nome"] == "Smartphone MarcaTeste X2 256GB 5G"
    assert sent["produtoPayload"]["asin"] == "B0ABC12345"
    assert sent["oferta"]["preco"] == 1599.90
    assert sent["oferta"]["codigoMarketplace"] == "B0ABC12345"


def test_amazon_cpu_incomplete_requests_review_instead_of_publishing(monkeypatch):
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda data: data)
    monkeypatch.setattr(router_v2, "_analyze_sync", lambda _request: _blocked_analysis())
    monkeypatch.setattr(
        CriaByteClient,
        "buscar_item_extensao",
        lambda _self, _identity, api_key=None: {"status": "NAO_ENCONTRADO"},
    )
    monkeypatch.setattr(
        CriaByteClient,
        "importar_oferta_extensao",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Não cadastrar CPU sem specs")),
    )
    result = router_v2._import_v2_sync(
        ImportAffiliateOfferV2Request(
            urlProduto="https://www.amazon.com.br/dp/B09VCJ171S",
            urlAfiliada="https://amzn.to/processador",
            dadosPagina={
                "nome": "Processador AMD Ryzen 5 5500 6 núcleos",
                "marca": "AMD",
                "modelo": "Ryzen 5 5500",
                "asin": "B09VCJ171S",
                "preco": 499,
            },
        )
    )
    assert result["status"] == "REVISAO_NECESSARIA"
    assert result["categoria"] == "PROCESSADOR"
    assert result["previa"]["nome"] == "Processador AMD Ryzen 5 5500 6 núcleos"


def test_non_amazon_capture_cannot_replace_failed_analysis(monkeypatch):
    monkeypatch.setattr(
        amazon_fallback,
        "auto_enrich_link_result",
        lambda _data: (_ for _ in ()).throw(AssertionError("Fallback incorreto")),
    )
    original = _blocked_analysis()
    result = amazon_fallback.hydrate_amazon_analysis(
        original,
        url="https://www.mercadolivre.com.br/produto/p/MLB123456",
        capture=PageCapture(nome="Smartphone Exemplo 256GB", marca="Exemplo"),
    )
    assert result is original


def test_amazon_complete_remote_analysis_remains_authoritative(monkeypatch):
    monkeypatch.setattr(
        amazon_fallback,
        "auto_enrich_link_result",
        lambda _data: (_ for _ in ()).throw(AssertionError("Fallback desnecessário")),
    )
    original = {
        "categoriaDetectada": "PROCESSADOR",
        "payloadParcialBackend": {
            "nome": "Processador AMD Ryzen 5500",
            "marca": "AMD",
            "especificacaoProcessador": {
                "socket": "AM4",
                "nucleos": 6,
            },
        },
    }
    assert amazon_fallback.hydrate_amazon_analysis(
        original,
        url="https://www.amazon.com.br/dp/B09VCJ171S",
        capture=PageCapture(nome="Processador AMD Ryzen 5500"),
    ) is original


def test_amazon_capture_attributes_fill_hardware_specs_when_remote_page_has_no_specs(monkeypatch):
    observed = {}
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda data: data)

    def fake_build(raw, category):
        observed.update(raw)
        assert category == "PROCESSADOR"
        return {
            "categoriaDetectada": "PROCESSADOR",
            "payloadParcialBackend": {
                "nome": raw["title"],
                "marca": raw["brand"],
                "modelo": raw["model"],
                "especificacaoProcessador": {
                    "socket": "AM4",
                    "nucleos": 6,
                },
            },
            "ofertaColetada": {"preco": raw["price"]},
            "origemColeta": {},
        }

    monkeypatch.setattr(amazon_fallback, "build_result", fake_build)
    remote = {
        "categoriaDetectada": "PROCESSADOR",
        "payloadParcialBackend": {
            "nome": "Processador AMD Ryzen 5 5500",
            "marca": "AMD",
            "modelo": "Ryzen 5 5500",
            "especificacaoProcessador": {},
        },
        "ofertaColetada": {"preco": 499.90},
    }

    result = amazon_fallback.hydrate_amazon_analysis(
        remote,
        url="https://www.amazon.com.br/dp/B09VCJ171S",
        capture=PageCapture(
            nome="Processador AMD Ryzen 5 5500 6-Core",
            marca="AMD",
            modelo="Ryzen 5 5500",
            asin="B09VCJ171S",
            preco=499.90,
            descricao="Processador desktop AM4",
            imagemUrl="https://images.example/ryzen.jpg",
            atributos=[
                {"name": "Socket", "value": "AM4"},
                {"name": "Número de núcleos", "value": "6"},
            ],
        ),
        forced_category="PROCESSADOR",
    )

    assert observed["attributes"] == [
        {"name": "Socket", "value_name": "AM4"},
        {"name": "Número de núcleos", "value_name": "6"},
    ]
    assert observed["description"] == "Processador desktop AM4"
    assert observed["image_url"] == "https://images.example/ryzen.jpg"
    specs = result["payloadParcialBackend"]["especificacaoProcessador"]
    assert specs["socket"] == "AM4"
    assert specs["nucleos"] == 6


def test_kabum_capture_attributes_fill_hardware_specs(monkeypatch):
    observed = {}
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda data: data)

    def fake_build(raw, category):
        observed.update(raw)
        assert category == "ARMAZENAMENTO"
        return {
            "categoriaDetectada": "ARMAZENAMENTO",
            "payloadParcialBackend": {
                "nome": raw["title"],
                "marca": raw["brand"],
                "modelo": raw["model"],
                "especificacaoArmazenamento": {
                    "tipo": "SSD",
                    "capacidadeGb": 1000,
                    "interface": "NVMe",
                    "formato": "M.2",
                },
            },
            "ofertaColetada": {"preco": raw["price"]},
            "origemColeta": {},
        }

    monkeypatch.setattr(amazon_fallback, "build_result", fake_build)
    remote = {
        "categoriaDetectada": "ARMAZENAMENTO",
        "payloadParcialBackend": {
            "nome": "SSD Kingston NV3 1TB",
            "marca": "Kingston",
            "modelo": "SNV3S/1000G",
            "especificacaoArmazenamento": {},
        },
        "ofertaColetada": {"preco": 399.90},
    }

    result = amazon_fallback.hydrate_marketplace_analysis(
        remote,
        url="https://www.kabum.com.br/produto/123456/ssd-kingston",
        capture=PageCapture(
            nome="SSD Kingston NV3 1TB NVMe M.2",
            marca="Kingston",
            modelo="SNV3S/1000G",
            preco=399.90,
            atributos=[
                {"name": "Tipo", "value": "SSD"},
                {"name": "Capacidade", "value": "1 TB"},
                {"name": "Interface", "value": "NVMe"},
                {"name": "Formato", "value": "M.2"},
            ],
        ),
        forced_category="ARMAZENAMENTO",
    )

    assert result["fallbackCapturaLocal"] is True
    assert result["fallbackCapturaAmazon"] is False
    assert result["origemColeta"]["plataformaCaptura"] == "KABUM"
    assert observed["attributes"][0] == {"name": "Tipo", "value_name": "SSD"}
    specs = result["payloadParcialBackend"]["especificacaoArmazenamento"]
    assert specs["capacidadeGb"] == 1000
