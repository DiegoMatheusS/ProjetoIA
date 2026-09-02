import requests

from src.main import build_result
from src.scrapers.magazine_scraper import MagazineScraper


PRODUCT_URL = "https://www.magazineluiza.com.br/produto-teste/p/abc123/in/prod/"


def _html_product(name="Produto Teste", body="", extra_head=""):
    return f'''<html><head>
      <meta property="og:title" content="{name}">
      {extra_head}
    </head><body><h1>{name}</h1>{body}</body></html>'''


def _raw_base(**overrides):
    raw = {
        "ok": True,
        "source": "MAGALU_PAGINA",
        "url_original": PRODUCT_URL,
        "url_final": PRODUCT_URL,
        "title": "SSD Kingston NV3 1TB NVMe",
        "brand": "Kingston",
        "model": "NV3 1TB",
        "mpn": "SNV3S/1000G",
        "gtin": None,
        "description": None,
        "image_url": None,
        "price": 399.90,
        "previous_price": None,
        "price_source": "MAGALU_PIX",
        "currency": "BRL",
        "available": True,
        "attributes": [],
        "attributes_text": "",
        "product_attributes": [],
        "marketplace_product_code": "abc123",
        "error": None,
    }
    raw.update(overrides)
    return raw


def test_v12_produto_esgotado_sem_inventar_preco():
    html = _html_product(
        "SSD Kingston NV3 1TB NVMe",
        body="<div>Produto indisponível</div><button>Avise-me quando chegar</button>",
    )
    raw = MagazineScraper()._parse_magazine_html(PRODUCT_URL, PRODUCT_URL, html)
    assert raw["available"] is False
    assert raw["price"] is None
    assert raw["previous_price"] is None


def test_v12_produto_sem_promocao_nao_cria_preco_anterior():
    html = _html_product(
        "SSD Kingston NV3 1TB NVMe",
        body="<div>Preço R$ 399,90</div><button>Adicionar à sacola</button>",
    )
    raw = MagazineScraper()._parse_magazine_html(PRODUCT_URL, PRODUCT_URL, html)
    assert raw["price"] == 399.90
    assert raw["previous_price"] is None


def test_v12_preco_pix_anterior_e_parcelado_nao_se_confundem():
    html = _html_product(
        "Monitor Gamer 27",
        body=(
            '<div data-testid="price-original">R$ 1.999,90</div>'
            '<div>R$ 1.599,90 no Pix</div>'
            '<div>ou R$ 1.799,90 em 10x de R$ 179,99 sem juros</div>'
            '<button>Comprar agora</button>'
        ),
    )
    raw = MagazineScraper()._parse_magazine_html(PRODUCT_URL, PRODUCT_URL, html)
    assert raw["price"] == 1599.90
    assert raw["previous_price"] == 1999.90
    assert raw["price_source"] == "MAGALU_PIX"


def test_v12_sem_mpn_nao_usa_sku_ou_codigo_magalu():
    generic = {
        "title": "Mouse Gamer Redragon Cobra M711",
        "brand": "Redragon",
        "model": "M711",
        "mpn": None,
    }
    attrs = [
        {"id": None, "name": "SKU", "value_name": "MAGALU-998877"},
        {"id": None, "name": "Código do produto", "value_name": "abc123"},
    ]
    _, model, mpn = MagazineScraper._refine_identity(generic, attrs)
    assert model == "M711"
    assert mpn is None


def test_v12_gtin_ean_valido_e_invalido():
    # 7894900011517 possui dígito verificador GS1 válido.
    attrs = [{"id": None, "name": "EAN", "value_name": "7894900011517"}]
    assert MagazineScraper._gtin_from_attributes(attrs) == "7894900011517"
    invalid = [{"id": None, "name": "EAN", "value_name": "7894900011518"}]
    assert MagazineScraper._gtin_from_attributes(invalid) is None


def test_v12_variante_aberta_explicitamente_selecionada():
    html = _html_product(
        "SSD Exemplo",
        body='''
          <select name="Capacidade"><option>1 TB</option><option selected>2 TB</option></select>
          <div role="radio" aria-checked="true" aria-label="Preto" data-testid="cor"></div>
          <button>Adicionar à sacola</button>
        ''',
    )
    raw = MagazineScraper()._parse_magazine_html(PRODUCT_URL, PRODUCT_URL, html)
    variants = raw["selected_variants"]
    assert {"nome": "Capacidade", "valor": "2 TB"} in variants
    assert any(v["valor"] == "Preto" for v in variants)


def test_v12_kit_combo_identifica_componentes_e_quantidade():
    info = MagazineScraper._kit_combo_info("Kit Teclado + Mouse Gamer Sem Fio")
    assert info["ehKitCombo"] is True
    assert set(info["componentesDetectados"]) == {"TECLADO", "MOUSE"}

    fans = MagazineScraper._kit_combo_info("Kit com 3 Ventoinhas ARGB 120mm")
    assert fans["ehKitCombo"] is True
    assert fans["quantidadeDetectada"] == 3


def test_v12_categoria_magalu_errada_nao_supera_produto_real():
    raw = _raw_base(
        title='HD Seagate 2TB 3.5" SATA III Interno',
        brand="Seagate",
        model="ST2000DM008",
        mpn="ST2000DM008",
        attributes=[{"id": None, "name": "Categoria da loja", "value_name": "HD Externo"}],
        attributes_text="Categoria da loja: HD Externo",
    )
    result = build_result(raw)
    assert result["categoriaDetectada"] == "ARMAZENAMENTO"


def test_v12_ficha_tecnica_especifica_e_fallback_quando_titulo_ambiguo():
    raw = _raw_base(
        title="Cooler MSI MAG B850 Tomahawk Max WiFi",
        brand="MSI",
        model="MAG B850 Tomahawk Max WiFi",
        mpn=None,
        attributes=[
            {"id": None, "name": "Tipo de produto", "value_name": "Placa-mãe"},
            {"id": None, "name": "Socket", "value_name": "AM5"},
        ],
        attributes_text="Tipo de produto: Placa-mãe\nSocket: AM5",
    )
    result = build_result(raw)
    assert result["categoriaDetectada"] == "PLACA_MAE"


def test_v12_ficha_incompleta_mantem_campo_ausente_sem_inventar():
    raw = _raw_base(
        title="Processador AMD Ryzen 7 5700X AM4",
        brand="AMD",
        model="5700X",
        mpn="100-100000926WOF",
        attributes=[{"id": None, "name": "Socket", "value_name": "AM4"}],
        attributes_text="Socket: AM4",
    )
    result = build_result(raw)
    specs = result["especificacoesEncontradas"]
    assert specs["socket"] == "AM4"
    assert "tdpWatts" not in specs


def test_v12_pagina_de_busca_e_rejeitada_sem_fazer_requisicao():
    url = "https://www.magazineluiza.com.br/busca/ssd-nvme/"
    raw = MagazineScraper().collect(url, no_browser=True)
    assert raw["ok"] is False
    assert raw["error"] == "MAGALU_URL_NAO_E_PAGINA_DE_PRODUTO"


def test_v12_url_404_retorna_erro_controlado(monkeypatch):
    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError("404 Client Error", response=response)
    scraper = MagazineScraper()
    monkeypatch.setattr(scraper, "_http_get", lambda url: (None, error))
    raw = scraper.collect(PRODUCT_URL, no_browser=False)
    assert raw["ok"] is False
    assert raw["error"] == "MAGALU_URL_404"


def test_v12_captura_local_incompleta_e_detectada():
    capture = {
        "original_url": PRODUCT_URL,
        "final_url": PRODUCT_URL,
        "title": "SSD Kingston NV3",
        "html": "<html></html>",
        "text": "SSD Kingston NV3",
        "blocked": False,
        "error": None,
    }
    raw = MagazineScraper().collect_from_local_capture(PRODUCT_URL, capture)
    assert raw["ok"] is False
    assert raw["error"] == "MAGALU_CAPTURA_LOCAL_INCOMPLETA"


def test_v12_produto_fora_das_categorias_nao_vira_hardware():
    raw = _raw_base(
        title="Liquidificador Mondial 3 Velocidades",
        brand="Mondial",
        model="L-99",
        mpn=None,
        attributes=[],
        attributes_text="",
    )
    result = build_result(raw)
    assert result["categoriaDetectada"] is None
    assert result["tipoCadastro"] is None
    assert result["erro"] == "PRODUTO_FORA_DAS_CATEGORIAS_CRIABYTE"
    assert result["analiseProduto"]["categoriaSuportada"] is False


def test_v12_mesmo_produto_com_nomes_diferentes_gera_mesmas_chaves():
    raw_a = _raw_base(
        title="SSD Kingston NV3 1TB M.2 NVMe",
        brand="Kingston",
        model="NV3 1TB",
        mpn="SNV3S/1000G",
        gtin="740617344790",
    )
    raw_b = _raw_base(
        title="Kingston SSD NV3 NVMe PCIe 4.0 1000GB",
        brand="Kingston",
        model="NV3 1TB",
        mpn="SNV3S/1000G",
        gtin="740617344790",
    )
    a = build_result(raw_a)["analiseProduto"]["chavesComparacao"]
    b = build_result(raw_b)["analiseProduto"]["chavesComparacao"]
    assert a == b
    assert a["mpnMarca"] == "kingston|snv3s/1000g"


def test_v14_2_pc_gamer_completo_tem_prioridade_sobre_cpu_interna():
    from src.extractors.category import detect_category
    title = "PC Gamer Skill Winner, AMD Ryzen 7 5700G, 16GB DDR4, SSD 1TB, Radeon Vega, Fonte 500W"
    assert detect_category(title) == "PC_MONTADO"


def test_v14_2_marca_do_titulo_nao_e_trocada_por_plataforma_da_ficha():
    generic = {
        "brand": "Gigabyte",
        "model": None,
        "mpn": None,
        "title": "Placa-Mãe Gigabyte B550M Aorus Elite Rev. 1.3, AMD AM4, Micro ATX, DDR4",
    }
    attrs = [
        {"id": None, "name": "Marca", "value_name": "AMD"},
        {"id": None, "name": "Modelo", "value_name": "B550M Aorus Elite"},
        {"id": None, "name": "Soquete do Processador", "value_name": "AM4"},
    ]
    brand, model, mpn = MagazineScraper._refine_identity(generic, attrs)
    assert brand == "Gigabyte"
    assert model == "B550M Aorus Elite"
    assert mpn is None


def test_v14_2_gpu_separa_modelo_comercial_do_part_number():
    generic = {
        "brand": "XFX",
        "model": None,
        "mpn": None,
        "title": "Placa de Vídeo XFX Swift RX 9070 XT WHITE, 16GB GDDR6 - RX-97TSWF3W9",
    }
    attrs = [
        {"id": None, "name": "Marca", "value_name": "XFX"},
        {"id": None, "name": "Modelo", "value_name": "RX-97TSWF3W9"},
        {"id": None, "name": "Referência", "value_name": "RX-97TSWF3W9"},
        {"id": None, "name": "Linha", "value_name": "Swift"},
    ]
    brand, model, mpn = MagazineScraper._refine_identity(generic, attrs)
    assert brand == "XFX"
    assert model == "Swift RX 9070 XT"
    assert mpn == "RX-97TSWF3W9"


def test_v14_3_gpu_preserva_modelo_especifico_do_fabricante():
    generic = {
        "brand": "ASUS",
        "model": None,
        "mpn": None,
        "title": "Placa de Vídeo ASUS RTX 5060 TI DUAL O8G NVIDIA GeForce, 8GB, GDDR7 - 90YV0MP2-M0NA00",
    }
    attrs = [
        {"id": None, "name": "Marca", "value_name": "ASUS"},
        {"id": None, "name": "Modelo", "value_name": "DUAL-RTX5060TI-O8G"},
        {"id": None, "name": "Referência", "value_name": "90YV0MP2-M0NA00"},
        {"id": None, "name": "GPU", "value_name": "NVIDIA GeForce RTX 5060 Ti"},
    ]
    brand, model, mpn = MagazineScraper._refine_identity(generic, attrs)
    assert brand == "ASUS"
    assert model == "DUAL-RTX5060TI-O8G"
    assert mpn == "90YV0MP2-M0NA00"


def test_v14_3_referencia_igual_modelo_comercial_nao_vira_mpn():
    generic = {
        "brand": "Gigabyte",
        "model": None,
        "mpn": None,
        "title": "Placa-Mãe Gigabyte B550M Aorus Elite Rev. 1.3, AMD AM4",
    }
    attrs = [
        {"id": None, "name": "Marca", "value_name": "AMD"},
        {"id": None, "name": "Modelo", "value_name": "B550M Aorus Elite"},
        {"id": None, "name": "Referência", "value_name": "B550M AORUS ELITE"},
    ]
    brand, model, mpn = MagazineScraper._refine_identity(generic, attrs)
    assert brand == "Gigabyte"
    assert model == "B550M Aorus Elite"
    assert mpn is None

    clean = MagazineScraper._product_attributes_only(attrs, brand=brand, model=model, mpn=mpn)
    assert not any(x["nome"] == "Marca" and x["valor"] == "AMD" for x in clean)


def test_v14_3_modelo_que_e_mpn_e_renomeado_na_ficha_limpa():
    attrs = [
        {"id": None, "name": "Marca", "value_name": "AMD"},
        {"id": None, "name": "Modelo", "value_name": "100-100000910WOF"},
        {"id": None, "name": "Número do Processador", "value_name": "7800X3D"},
    ]
    clean = MagazineScraper._product_attributes_only(
        attrs, brand="AMD", model="7800X3D", mpn="100-100000910WOF"
    )
    assert {"nome": "MPN", "valor": "100-100000910WOF"} in clean
    assert not any(x["nome"] == "Modelo" and x["valor"] == "100-100000910WOF" for x in clean)
