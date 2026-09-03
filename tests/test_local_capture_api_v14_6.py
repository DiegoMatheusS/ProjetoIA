from src.api import CaptureAnalyzeRequest, _analyze_capture_sync, _structured_capture_to_raw


def test_structured_local_capture_gpu_keeps_board_model_and_mpn():
    capture = {
        "finalUrl": "https://www.magazinevoce.com.br/x/p/hh56j1kd44/in/pcvd/?seller_id=kabum",
        "productName": "Placa de Vídeo ASUS RTX 5060 TI DUAL O8G NVIDIA GeForce, 8GB, GDDR7 - 90YV0MP2-M0NA00",
        "description": "Placa de vídeo Asus DUAL-RTX5060TI-O8G",
        "brand": "ASUS",
        "model": "",
        "mpn": "",
        "sku": "hh56j1kd44",
        "gtin": "",
        "image": "https://a-static.mlcdn.com.br/186x140/a.jpeg",
        "metaImage": "https://a-static.mlcdn.com.br/470x352/a.jpeg",
        "price": "3644.22",
        "priceCurrency": "BRL",
        "availability": "http://schema.org/InStock",
        "attributes": [
            {"name": "Marca", "value": "ASUS"},
            {"name": "Modelo", "value": "DUAL-RTX5060TI-O8G"},
            {"name": "Referência", "value": "90YV0MP2-M0NA00"},
            {"name": "GPU", "value": "NVIDIA GeForce RTX 5060 Ti"},
            {"name": "Memória de Vídeo", "value": "8 GB GDDR7"},
            {"name": "02x de R$ 2.070,58 sem juros", "value": "R$ 4.141,16"},
        ],
        "selectedVariants": ["Selecionar imagem"],
    }
    raw = _structured_capture_to_raw("https://www.magazinevoce.com.br/x/p/hh56j1kd44/in/pcvd/?seller_id=kabum", capture)
    assert raw["model"] == "DUAL-RTX5060TI-O8G"
    assert raw["mpn"] == "90YV0MP2-M0NA00"
    assert raw["price"] == 3644.22
    assert raw["available"] is True
    assert all("02x de" not in row["name"] for row in raw["attributes"])
    assert raw["selected_variants"] == []


def test_analyze_capture_returns_local_mode_and_normalized_result():
    capture = {
        "finalUrl": "https://www.magazinevoce.com.br/x/p/ea444h39dd/in/pcvd/?seller_id=kabum",
        "productName": "Placa de Vídeo XFX Swift RX 9070 XT, 16GB GDDR6 - RX-97TSWF3W9",
        "brand": "XFX",
        "model": "",
        "sku": "ea444h39dd",
        "price": "5694.10",
        "availability": "http://schema.org/InStock",
        "attributes": [
            {"name": "Linha", "value": "Swift"},
            {"name": "Modelo", "value": "RX-97TSWF3W9"},
            {"name": "Referência", "value": "RX-97TSWF3W9"},
            {"name": "Memória de Vídeo", "value": "16 GB"},
            {"name": "Tipo de Memória", "value": "GDDR6"},
        ],
    }
    result = _analyze_capture_sync(CaptureAnalyzeRequest(
        url="https://www.magazinevoce.com.br/x/p/ea444h39dd/in/pcvd/?seller_id=kabum",
        categoria="PLACA_VIDEO",
        captura=capture,
    ))
    assert result["categoriaDetectada"] == "PLACA_VIDEO"
    assert result["payloadParcialBackend"]["marca"] == "XFX"
    assert result["payloadParcialBackend"]["mpn"] == "RX-97TSWF3W9"
    assert result["ofertaColetada"]["preco"] == 5694.10
    assert result["origemColeta"]["capturaLocal"] is True
    assert result["servicoProdutoIa"]["versao"] == "14.20.1-railway"
    assert result["servicoProdutoIa"]["modo"] == "CAPTURA_LOCAL_HTTP_API"


def test_local_capture_does_not_treat_store_sku_as_mpn():
    capture = {
        "productName": "Placa-Mãe Gigabyte B550M Aorus Elite Rev. 1.3",
        "brand": "Gigabyte",
        "sku": "cb61h51kd3",
        "price": "778.55",
        "attributes": [
            {"name": "Marca", "value": "AMD"},
            {"name": "Modelo", "value": "B550M Aorus Elite"},
            {"name": "Referência", "value": "B550M AORUS ELITE"},
        ],
    }
    raw = _structured_capture_to_raw("https://www.magazinevoce.com.br/x/p/cb61h51kd3/in/pmae/", capture)
    assert raw["brand"] == "Gigabyte"
    assert raw["model"] == "B550M Aorus Elite"
    assert raw["mpn"] is None
    assert raw["marketplace_product_code"] == "cb61h51kd3"
