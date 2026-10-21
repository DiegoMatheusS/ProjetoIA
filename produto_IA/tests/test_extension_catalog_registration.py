from copy import deepcopy

import pytest

from src.criabyte.client import CriaByteClient
from src.extension import amazon_fallback, router, router_v2
from src.extension.payload_guard import extension_registration_issues
from src.extension.router_v2 import ImportAffiliateOfferV2Request, PageCapture
from src.extractors.category import detect_category
from src.extractors.dto_normalizer import normalize_specs_for_backend
from src.extractors.ml_specs import extract_specs
from src.main import build_result


@pytest.mark.parametrize("title,category", [
    ("Mouse Pad Gamer RGB 900x400", "MOUSEPAD"),
    ("Mouse-Pad XXL", "MOUSEPAD"),
    ("Mouse Gaming Pad XL", "MOUSEPAD"),
    ("Logitech Mousepad G440", "MOUSEPAD"),
    ("Desk Mat para teclado e mouse", "MOUSEPAD"),
    ("Tapete para mouse gamer", "MOUSEPAD"),
    ("Mouse Logitech G203 com mousepad", "MOUSE"),
    ("Fones de ouvido Bluetooth", "FONE"),
    ("Headphones Sony WH-1000XM5", "FONE"),
    ("Earphones KZ EDX", "FONE"),
    ("Earbuds TWS QCY T13", "FONE"),
    ("Apple AirPods Pro 2", "FONE"),
    ("Samsung Galaxy Buds3 Pro", "FONE"),
    ("JBL Wave Buds Bluetooth", "FONE"),
    ("Headset gamer HyperX Cloud", "HEADSET"),
    ("Fone de ouvido gamer Headset HyperX", "HEADSET"),
])
def test_category_identifies_item_sold(title, category):
    assert detect_category(title) == category


def test_mousepad_title_wins_over_generic_mouse_attribute():
    result = build_result({
        "title": "Mouse Pad Gamer RGB XXL",
        "attributes": [{"name": "Tipo de produto", "value_name": "Mouse"}],
    })
    assert result["categoriaDetectada"] == "MOUSEPAD"
    assert result["categoriaSlugSugerida"] == "mousepads"
    assert "especificacaoMouse" not in result["payloadParcialBackend"]


def test_fone_title_is_not_changed_to_generic_headset_attribute():
    result = build_result({"title": "Fones de ouvido Bluetooth QCY T13", "attributes": [
        {"name": "Tipo de produto", "value_name": "Headset"},
    ]})
    assert result["categoriaDetectada"] == "FONE"
    assert result["categoriaSlugSugerida"] == "fones"


@pytest.mark.parametrize("title,remote_category,expected", [
    ("Mouse Pad Gamer RGB XXL", "MOUSE", "MOUSEPAD"),
    ("Fones de ouvido Bluetooth QCY T13", "HEADSET", "FONE"),
    ("Apple AirPods Pro 2", "CELULAR", "FONE"),
])
def test_capture_corrects_ambiguous_remote_category(monkeypatch, title, remote_category, expected):
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda result: result)
    remote = {"categoriaDetectada": remote_category, "payloadParcialBackend": {
        "nome": title, "especificacaoMouse": {"dpiMaximo": 16000},
        "especificacaoHeadset": {"microfone": True},
    }}
    result = amazon_fallback.hydrate_marketplace_analysis(
        remote, url="https://www.amazon.com.br/dp/B0ABC12345",
        capture=PageCapture(nome=title, marca="Teste", modelo="X1"),
    )
    assert result["categoriaDetectada"] == expected
    assert "especificacaoMouse" not in result["payloadParcialBackend"]
    assert "especificacaoHeadset" not in result["payloadParcialBackend"]
    forced = amazon_fallback.hydrate_marketplace_analysis(
        remote, url="https://www.amazon.com.br/dp/B0ABC12345",
        capture=PageCapture(nome=title), forced_category=remote_category,
    )
    assert forced["categoriaDetectada"] == remote_category


def _build_analysis(description="Ryzen 5, RAM 16 GB, SSD 1 TB; garantia de 12 meses."):
    return {
        "categoriaDetectada": "PC_MONTADO", "tipoCadastro": "BUILD",
        "payloadParcialBackend": {"nome": "PC Gamer Teste", "descricao": description,
                                  "componentes": [{"hardwareId": 999}]},
        "ofertaColetada": {"preco": 3999.9, "precoAnterior": 4299.9,
                          "urlOriginal": "https://loja.example/pc", "codigoMarketplace": "PC123"},
    }


@pytest.mark.parametrize("v2", [False, True])
def test_build_registration_uses_commercial_payload_once(monkeypatch, v2):
    calls = []
    sent = []
    module = router_v2 if v2 else router
    def analyze(request):
        calls.append(request)
        return _build_analysis()
    monkeypatch.setattr(module, "_analyze_sync", analyze)
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao",
                        lambda self, payload, api_key=None: sent.append(payload) or
                        {"status": "BUILD_E_OFERTA_CRIADOS", "publicado": True})
    if v2:
        monkeypatch.setattr(CriaByteClient, "buscar_item_extensao",
                            lambda *args, **kwargs: {"status": "NAO_ENCONTRADO"})
        result = router_v2._import_v2_sync(ImportAffiliateOfferV2Request(
            urlProduto="https://loja.example/pc", urlAfiliada="https://afiliado.example/pc"))
    else:
        result = router._import_sync(router.ImportAffiliateOfferRequest(
            urlProduto="https://loja.example/pc", urlAfiliada="https://afiliado.example/pc"))
    assert len(calls) == len(sent) == 1
    assert result["status"] == "BUILD_E_OFERTA_CRIADOS"
    assert result["previa"]["tipoCadastro"] == "BUILD"
    assert sent[0]["buildPayload"]["categoria"] == "PC_MONTADO"
    assert sent[0]["buildPayload"]["descricao"] == _build_analysis()["payloadParcialBackend"]["descricao"]
    assert "componentes" not in sent[0]["buildPayload"]
    assert "hardwarePayload" not in sent[0]
    assert sent[0]["oferta"]["precoAnterior"] == 4299.9
    assert sent[0]["oferta"]["urlAfiliada"] == "https://afiliado.example/pc"


def test_build_missing_description_can_be_completed_in_extension(monkeypatch):
    monkeypatch.setattr(router, "_analyze_sync", lambda request: _build_analysis(None))
    sent = []
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao",
                        lambda self, payload, api_key=None: sent.append(payload) or {"publicado": True})
    request = router.ImportAffiliateOfferRequest(
        urlProduto="https://loja.example/pc", urlAfiliada="https://afiliado.example/pc")
    result = router._import_sync(request)
    assert result["status"] == "REVISAO_NECESSARIA"
    assert result["camposFaltantes"] == [router._field_descriptor("descricao")]
    assert result["camposFaltantes"][0]["tipo"] == "textarea"
    assert sent == []
    description = "Configuração, acessórios e garantia.\n" * 200
    request.dadosManuais = {"descricao": description}
    router._import_sync(request)
    assert sent[0]["buildPayload"]["descricao"] == description.strip()


@pytest.mark.parametrize("raw,length", [(2280, 80), (22110, 110), (80.0, 80),
    ("M.2 2230", 30), ("22 x 42 mm", 42), ("80 mm", 80), ("2280/22110", None)])
def test_m2_length_is_mm_instead_of_form_factor_code(raw, length):
    result = normalize_specs_for_backend("ARMAZENAMENTO", {"tamanhoM2Mm": raw})
    assert result.get("tamanhoM2Mm") == length


@pytest.mark.parametrize("text,length,key", [
    ("SSD M.2 2280 NVMe 1 TB M-Key", 80, "M"),
    ("SSD M.2 22110 NVMe 1 TB Key: M", 110, "M"),
    ("SSD M.2 2242 SATA 1 TB Chave M.2: B+M", 42, "B_M"),
    ("SSD M.2 2230 SATA 1 TB B-Key", 30, "B"),
    ("SSD M.2 NVMe 1 TB", None, None),
])
def test_storage_extractor_reads_only_confirmed_size_and_key(text, length, key):
    result = extract_specs("ARMAZENAMENTO", [], text)
    assert result.get("tamanhoM2Mm") == length
    assert result.get("chaveM2") == key


def test_storage_attributes_use_backend_length_unit():
    result = extract_specs("ARMAZENAMENTO", [
        {"name": "Formato", "value_name": "M.2"},
        {"name": "Tamanho M.2", "value_name": "2280"},
        {"name": "Chave", "value_name": "M"},
    ], "SSD NVMe 1 TB")
    assert result["tamanhoM2Mm"] == 80
    assert result["chaveM2"] == "M"


def test_missing_m2_fields_require_review_and_accept_manual_values(monkeypatch):
    payload = {"nome": "SSD Teste M.2 1TB", "marca": "Teste", "modelo": "X1",
               "categoria": "ARMAZENAMENTO", "especificacaoArmazenamento": {
                   "tipo": "SSD", "formato": "M2", "interface": "NVME_PCIE", "capacidadeGb": 1000}}
    analysis = {"categoriaDetectada": "ARMAZENAMENTO", "tipoCadastro": "HARDWARE",
                "payloadParcialBackend": payload, "ofertaColetada": {
                    "preco": 399.9, "urlOriginal": "https://loja.example/ssd"}}
    monkeypatch.setattr(router, "_analyze_sync", lambda request: deepcopy(analysis))
    sent = []
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao",
                        lambda self, body, api_key=None: sent.append(body) or {"publicado": True})
    request = router.ImportAffiliateOfferRequest(
        urlProduto="https://loja.example/ssd", urlAfiliada="https://afiliado.example/ssd")
    result = router._import_sync(request)
    fields = {field["campo"]: field for field in result["camposFaltantes"]}
    assert "especificacaoArmazenamento.tamanhoM2Mm" in fields
    assert fields["especificacaoArmazenamento.chaveM2"]["opcoes"] == ["M", "B", "B_M"]
    assert sent == []
    request.dadosManuais = {"especificacaoArmazenamento.tamanhoM2Mm": 80,
                           "especificacaoArmazenamento.chaveM2": "M"}
    router._import_sync(request)
    assert extension_registration_issues("ARMAZENAMENTO", sent[0]["hardwarePayload"]) == []


@pytest.mark.parametrize("title,slug", [("Mouse Pad Gamer XXL", "mousepads"),
    ("Fones de ouvido Bluetooth QCY T13", "fones")])
def test_local_capture_registers_mousepad_and_fone_as_generic_products(monkeypatch, title, slug):
    monkeypatch.setattr(amazon_fallback, "auto_enrich_link_result", lambda result: result)
    monkeypatch.setattr(router_v2, "_analyze_sync", lambda request: {"payloadParcialBackend": {}})
    monkeypatch.setattr(CriaByteClient, "buscar_item_extensao",
                        lambda *args, **kwargs: {"status": "NAO_ENCONTRADO"})
    sent = []
    monkeypatch.setattr(CriaByteClient, "importar_oferta_extensao",
                        lambda self, payload, api_key=None: sent.append(payload) or {"publicado": True})
    router_v2._import_v2_sync(ImportAffiliateOfferV2Request(
        urlProduto="https://www.amazon.com.br/dp/B0ABC12345", urlAfiliada="https://amzn.to/exemplo",
        dadosPagina={"nome": title, "marca": "Teste", "modelo": "X1", "preco": 99.9}))
    assert sent[0]["produtoPayload"]["categoriaSlug"] == slug
    assert "especificacaoMouse" not in sent[0]["produtoPayload"]
    assert "especificacaoHeadset" not in sent[0]["produtoPayload"]
