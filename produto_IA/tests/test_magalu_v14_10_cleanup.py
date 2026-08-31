from bs4 import BeautifulSoup

from src.main import build_result
from src.scrapers.magazine_scraper import MagazineScraper


URL = "https://www.magazinevoce.com.br/magazinecriabyte/produto/p/ea444h39dd/in/pcvd/"


def test_v14_10_gpu_exata_supera_familia_generica_da_ficha():
    raw = {
        "ok": True,
        "source": "MAGALU_SURFSKY_CLOUD",
        "url_original": URL,
        "url_final": URL,
        "title": "Placa de Vídeo XFX Swift AMD Radeon RX 9070 XT 16GB GDDR6",
        "brand": "XFX",
        "model": "Swift RX 9070 XT",
        "mpn": "RX-97TSWF3W9",
        "gtin": None,
        "description": "Arquitetura RDNA 4",
        "image_url": None,
        "price": 5694.10,
        "previous_price": 6832.82,
        "price_source": "MAGALU_PIX",
        "currency": "BRL",
        "available": True,
        "attributes": [
            {"name": "GPU", "value_name": "AMD Radeon RX série 9000"},
            {"name": "Memória de Vídeo", "value_name": "16 GB"},
            {"name": "Tipo de Memória", "value_name": "GDDR6"},
        ],
        "attributes_text": "GPU: AMD Radeon RX série 9000\nMemória de Vídeo: 16 GB\nTipo de Memória: GDDR6",
        "product_attributes": [],
        "selected_variants": [],
        "kit_combo": {"ehKitCombo": False, "quantidadeDetectada": None, "componentesDetectados": []},
        "marketplace_product_code": "ea444h39dd",
        "error": None,
    }
    result = build_result(raw, "PLACA_VIDEO")
    assert result["especificacoesEncontradas"]["gpu"] == "AMD Radeon RX 9070 XT"


def test_v14_10_remove_controle_galeria_das_variantes():
    html = (
        '<html><body>'
        '<button data-testid="base-button" aria-selected="true" aria-label="Selecionar imagem"></button>'
        '<div data-testid="cor" aria-selected="true" aria-label="Branco"></div>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "html.parser")
    variants = MagazineScraper._selected_variants(soup)
    assert {"nome": "cor", "valor": "Branco"} in variants
    assert not any(v["valor"].casefold() == "selecionar imagem" for v in variants)
    assert not any(v["nome"].casefold() == "base-button" for v in variants)


def test_v14_10_gpu_com_fans_nao_vira_kit_de_ventoinha():
    info = MagazineScraper._kit_combo_info(
        "Placa de Vídeo XFX Swift RX 9070 XT White Triple Fan Gaming Edition"
    )
    assert info == {
        "ehKitCombo": False,
        "quantidadeDetectada": None,
        "componentesDetectados": [],
    }


def test_v14_10_kit_real_de_ventoinhas_continua_valido():
    info = MagazineScraper._kit_combo_info("Kit com 3 Ventoinhas ARGB 120mm")
    assert info["ehKitCombo"] is True
    assert info["quantidadeDetectada"] == 3
    assert info["componentesDetectados"] == ["VENTOINHA"]
