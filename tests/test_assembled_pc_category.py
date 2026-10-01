from src.extractors.category import assembled_computer_title, detect_category
from src.main import _category_hint_from_product_url, build_result


ML_DESKTOP_TITLE = "Computador Intel Core i5 3470 16GB RAM SSD 120GB Windows 10"
ML_DESKTOP_URL = (
    "https://www.mercadolivre.com.br/"
    "computador-intel-core-i5-3470-16gb-ram-ssd-120gb-windows-10/p/MLB43425664"
    "#polycard_client=search-desktop&wid=MLB5272775008"
)


def test_mercado_livre_computer_with_intel_cpu_is_a_build():
    assert assembled_computer_title(ML_DESKTOP_TITLE)
    assert detect_category(ML_DESKTOP_TITLE) == "PC_MONTADO"
    assert _category_hint_from_product_url(ML_DESKTOP_URL) == "PC_MONTADO"


def test_build_result_never_turns_computer_cpu_into_processor():
    raw = {
        "ok": True,
        "title": ML_DESKTOP_TITLE,
        "brand": None,
        "model": None,
        "url_original": ML_DESKTOP_URL,
        "attributes": [],
        "price": 950.0,
    }
    result = build_result(raw)
    assert result["categoriaDetectada"] == "PC_MONTADO"
    assert result["tipoCadastro"] == "BUILD"
    assert result["payloadParcialBackend"].get("categoria") != "PROCESSADOR"


def test_actual_processors_and_upgrade_kits_are_not_computers():
    assert detect_category("Processador Intel Core i5-3470 3.2GHz") == "PROCESSADOR"
    assert detect_category("Processador AMD Ryzen 5 5600G para PC Gamer") == "PROCESSADOR"
    assert not assembled_computer_title("Kit upgrade PC Intel Core i5 placa mãe")
    assert not assembled_computer_title("Gabinete para computador gamer")
    assert not assembled_computer_title("Notebook Intel Core i5")
    assert not assembled_computer_title("Mini PC Intel Core i5")
    assert detect_category("Mini PC Intel Core i5") == "MINI_COMPUTADOR"


def test_non_gamer_full_desktops_are_recognized():
    assert detect_category("PC AMD Ryzen 5 5600G 16GB SSD") == "PC_MONTADO"
    assert detect_category("Desktop Intel Core i7 16GB RAM") == "PC_MONTADO"
    assert detect_category("Computador de mesa completo 8GB") == "PC_MONTADO"


def test_marketplace_titles_with_brand_before_pc_stay_as_complete_computer():
    assert detect_category(
        "Pichau PC Gamer AMD Ryzen 5 5600G 16GB RAM SSD 480GB RTX 4060"
    ) == "PC_MONTADO"
    assert detect_category(
        "Skill Gaming Computador Ryzen 7 5700G 16GB DDR4 SSD 1TB"
    ) == "PC_MONTADO"
    assert detect_category(
        "Mancer PC Ryzen 5 5500 16GB RAM NVMe 500GB"
    ) == "PC_MONTADO"
